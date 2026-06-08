param(
    [string]$PackageDir = "windows-codex-package",
    [switch]$RestoreDb,
    [switch]$ResetVolumes,
    [switch]$SkipFrontend,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

function Log($Message) {
    Write-Host "[AgentHub] $Message"
}

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Read-DotEnvValue($Name, $Default) {
    $envPath = Join-Path (Get-Location) ".env"
    if (-not (Test-Path $envPath)) {
        return $Default
    }
    $line = Get-Content $envPath |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
        Select-Object -Last 1
    if (-not $line) {
        return $Default
    }
    $value = ($line -replace "^\s*$([regex]::Escape($Name))\s*=", "").Trim()
    if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Default
    }
    return $value
}

function Run-Command {
    param(
        [string]$File,
        [Parameter(ValueFromRemainingArguments = $true)]
        [object[]]$CommandArgs
    )
    $flatArgs = New-Object System.Collections.Generic.List[string]
    foreach ($arg in $CommandArgs) {
        if ($arg -is [System.Array]) {
            foreach ($item in $arg) {
                $flatArgs.Add([string]$item)
            }
        } else {
            $flatArgs.Add([string]$arg)
        }
    }
    $argv = $flatArgs.ToArray()
    Log ("Running: {0} {1}" -f $File, ($argv -join " "))
    & $File @argv
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $File"
    }
}

function Wait-ForUrl($Url, $Label, $MaxSeconds) {
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    do {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 | Out-Null
            Log "$Label is ready: $Url"
            return
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Label at $Url"
}

function Test-PortListener($Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$connections
}

function Ensure-Pnpm {
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        return
    }
    if (Get-Command corepack -ErrorAction SilentlyContinue) {
        Log "pnpm not found; enabling Corepack..."
        Run-Command corepack @("enable")
        Run-Command corepack @("prepare", "pnpm@latest", "--activate")
        return
    }
    throw "pnpm is missing and corepack is unavailable. Install Node.js 20+ with Corepack or install pnpm manually."
}

function Start-Frontend {
    if ($SkipFrontend.IsPresent) {
        Log "Skipping frontend startup."
        return
    }
    Require-Command node
    Ensure-Pnpm

    if (-not (Test-Path "frontend\node_modules")) {
        Log "Installing frontend dependencies..."
        Push-Location frontend
        try {
            Run-Command pnpm @("install")
        } finally {
            Pop-Location
        }
    }

    if (Test-PortListener 5173) {
        Log "Frontend port 5173 already has a listener; leaving it alone."
        return
    }

    Log "Starting frontend dev server..."
    $frontendLog = Join-Path (Get-Location) ".agenthub-windows-frontend.log"
    $frontendErrLog = Join-Path (Get-Location) ".agenthub-windows-frontend.err.log"
    $env:VITE_DEV_PROXY_TARGET = "http://localhost:8000"
    $process = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", "pnpm", "dev", "--host", "0.0.0.0") `
        -WorkingDirectory (Join-Path (Get-Location) "frontend") `
        -RedirectStandardOutput $frontendLog `
        -RedirectStandardError $frontendErrLog `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -Path ".agenthub-windows-frontend.pid" -Value $process.Id -Encoding ASCII
    Wait-ForUrl "http://localhost:5173" "Frontend" 90
    Start-Process "http://localhost:5173" | Out-Null
}

function Compose-Args([string[]]$Args, [bool]$UseImportedImage) {
    if ($UseImportedImage) {
        return @("compose", "-f", "docker-compose.yml", "-f", "docker-compose.windows-image.yml") + $Args
    }
    return @("compose") + $Args
}

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..")
$PackagePath = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $PackageDir))
if ([System.IO.Path]::IsPathRooted($PackageDir)) {
    $PackagePath = [System.IO.Path]::GetFullPath($PackageDir)
}

Set-Location $ProjectRoot

Require-Command docker
Require-Command tar

Log "Project: $ProjectRoot"
Log "Package: $PackagePath"

if (-not (Test-Path $PackagePath)) {
    throw "Package directory not found: $PackagePath"
}

try {
    docker info | Out-Null
} catch {
    throw "Docker is not running. Start Docker Desktop and run this script again."
}

if (-not (Test-Path ".env")) {
    $packagedEnv = Join-Path $PackagePath ".env"
    if (Test-Path $packagedEnv) {
        Log "Copying packaged .env into project root."
        Copy-Item $packagedEnv ".env" -Force
    } else {
        Log "No .env found; copying .env.example."
        Copy-Item ".env.example" ".env" -Force
    }
}

if ($ResetVolumes.IsPresent) {
    Log "Resetting Docker volumes. This deletes local Windows AgentHub data."
    Run-Command docker @("compose", "down", "-v")
}

$useImportedImage = $false
$imageTar = Join-Path $PackagePath "agenthub-backend-linux-amd64.tar"
if (-not $Rebuild.IsPresent -and (Test-Path $imageTar)) {
    Log "Loading packaged backend image..."
    Run-Command docker @("load", "-i", $imageTar)
    $useImportedImage = $true
}

$workspacesTar = Join-Path $PackagePath "workspaces.tgz"
if (Test-Path $workspacesTar) {
    Log "Restoring workspaces archive..."
    Remove-Item "workspaces" -Recurse -Force -ErrorAction SilentlyContinue
    Run-Command tar @("-xzf", $workspacesTar)
} else {
    New-Item -ItemType Directory -Force -Path "workspaces" | Out-Null
}

if ($useImportedImage) {
    Log "Starting Docker stack with imported backend image..."
    Run-Command docker (Compose-Args @("up", "-d", "--no-build", "postgres", "redis", "backend") $true)
} else {
    Log "Starting Docker stack with local backend build..."
    Run-Command docker (Compose-Args @("up", "-d", "--build", "postgres", "redis", "backend") $false)
}

$composeUseImported = $useImportedImage

$uploadsTar = Join-Path $PackagePath "uploads-data.tgz"
if (Test-Path $uploadsTar) {
    Log "Restoring uploads-data volume..."
    Run-Command docker (Compose-Args @(
        "run", "--rm", "-T",
        "-v", "${PackagePath}:/import",
        "backend",
        "sh", "-lc",
        "mkdir -p /app/data/uploads && tar xzf /import/uploads-data.tgz -C /app/data/uploads"
    ) $composeUseImported)
}

$claudeTar = Join-Path $PackagePath "claude-state.tgz"
if (Test-Path $claudeTar) {
    Log "Restoring Claude state volume..."
    Run-Command docker (Compose-Args @(
        "run", "--rm", "-T",
        "-v", "${PackagePath}:/import",
        "backend",
        "sh", "-lc",
        'mkdir -p "$AGENTHUB_CLAUDE_AUTH_DIR" && tar xzf /import/claude-state.tgz -C "$AGENTHUB_CLAUDE_AUTH_DIR"'
    ) $composeUseImported)
}

$opencodeTar = Join-Path $PackagePath "opencode-state.tgz"
if (Test-Path $opencodeTar) {
    Log "Restoring OpenCode state volume..."
    Run-Command docker (Compose-Args @(
        "run", "--rm", "-T",
        "-v", "${PackagePath}:/import",
        "backend",
        "sh", "-lc",
        'mkdir -p "$AGENTHUB_OPENCODE_AUTH_DIR" && tar xzf /import/opencode-state.tgz -C "$AGENTHUB_OPENCODE_AUTH_DIR"'
    ) $composeUseImported)
}

$sqlPath = Join-Path $PackagePath "agenthub.sql"
if ($RestoreDb.IsPresent -and (Test-Path $sqlPath)) {
    Log "Restoring database dump..."
    $pgUser = Read-DotEnvValue "POSTGRES_USER" "agenthub"
    $pgDb = Read-DotEnvValue "POSTGRES_DB" "agenthub"
    Run-Command docker @("cp", $sqlPath, "agenthub-postgres:/tmp/agenthub.sql")
    Run-Command docker (Compose-Args @("exec", "-T", "postgres", "psql", "-U", $pgUser, "-d", $pgDb, "-f", "/tmp/agenthub.sql") $composeUseImported)
} elseif (Test-Path $sqlPath) {
    Log "Database dump exists but -RestoreDb was not passed; skipping DB restore."
}

Log "Running migrations..."
Run-Command docker (Compose-Args @("exec", "-T", "backend", "alembic", "upgrade", "head") $composeUseImported)

Log "Seeding built-in agents..."
Run-Command docker (Compose-Args @("exec", "-T", "backend", "python", "-m", "app.seeds.seed_agents") $composeUseImported)

Wait-ForUrl "http://localhost:8000/health" "Backend health check" 120
Start-Frontend

Log "Import complete."
