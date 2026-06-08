param(
    [string]$OutputDir = "mac-codex-package",
    [ValidateSet("mac", "windows")]
    [string]$TargetPlatform = "mac",
    [switch]$IncludeEnv,
    [switch]$SkipSource,
    [switch]$SkipBackendImage,
    [switch]$SkipDatabase,
    [switch]$SkipWorkspaces,
    [switch]$SkipUploads,
    [switch]$SkipRuntimeState,
    [switch]$BuildBackendImage
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
    $envPath = Join-Path $ProjectRoot ".env"
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

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..")
$OutputPath = Join-Path $ProjectRoot $OutputDir
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

Require-Command docker
Require-Command tar

Set-Location $ProjectRoot

Log "Project: $ProjectRoot"
Log "Output:  $OutputPath"

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

$manifest = [ordered]@{
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    source_project = "$ProjectRoot"
    target_platform = $TargetPlatform
    backend_image_included = (-not $SkipBackendImage.IsPresent)
    database_included = (-not $SkipDatabase.IsPresent)
    workspaces_included = (-not $SkipWorkspaces.IsPresent)
    uploads_included = (-not $SkipUploads.IsPresent)
    runtime_state_included = (-not $SkipRuntimeState.IsPresent)
    env_included = $IncludeEnv.IsPresent
}

if (-not $SkipSource.IsPresent) {
    Log "Creating source archive..."
    $sourceTar = Join-Path $OutputDir "agenthub-source.tgz"
    $stageRoot = Join-Path $OutputDir "_source-stage"
    $stageProject = Join-Path $stageRoot "agenthub-github"
    if (Test-Path $sourceTar) {
        Remove-Item $sourceTar -Force
    }
    if (Test-Path $stageRoot) {
        Remove-Item $stageRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $stageProject | Out-Null
    $robocopyArgs = @(
        "$ProjectRoot",
        $stageProject,
        "/E",
        "/XD",
        ".git",
        ".ruff_cache",
        "data",
        "workspaces",
        $OutputDir,
        "mac-codex-package",
        "windows-codex-package",
        "*-codex-package",
        "node_modules",
        "dist",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "/XF",
        ".env",
        "*.log",
        "*-codex-package.zip",
        "*-codex-package.tgz",
        "*-codex-package.tar",
        ".agenthub-mac-frontend.log",
        ".agenthub-mac-frontend.pid",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP"
    )
    Log "Copying source into staging directory..."
    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }
    Run-Command tar @("-czf", $sourceTar, "-C", $stageRoot, "agenthub-github")
    Remove-Item (Join-Path $ProjectRoot $stageRoot) -Recurse -Force
    $manifest["source_archive"] = "agenthub-source.tgz"
}

if ($IncludeEnv.IsPresent) {
    if (Test-Path ".env") {
        Copy-Item ".env" (Join-Path $OutputPath ".env") -Force
        $manifest["env_file"] = ".env"
        Log "Included .env. Treat this package as secret material."
    } else {
        Log ".env not found; skipping."
    }
} else {
    "The .env file was not exported. Copy it manually if the $TargetPlatform test needs provider keys." |
        Set-Content -Path (Join-Path $OutputPath "ENV_NOT_INCLUDED.txt") -Encoding UTF8
}

if (-not $SkipBackendImage.IsPresent) {
    if ($BuildBackendImage.IsPresent) {
        Log "Building backend image before export..."
        Run-Command docker @("compose", "build", "backend")
    }

    $imageId = (& docker compose images -q backend).Trim()
    if (-not $imageId) {
        Log "Backend image not found; building it now..."
        Run-Command docker @("compose", "build", "backend")
        $imageId = (& docker compose images -q backend).Trim()
    }
    if (-not $imageId) {
        throw "Could not resolve backend image id."
    }

    $backendImageTag = "agenthub-backend:${TargetPlatform}-test"
    Log "Tagging backend image as $backendImageTag..."
    Run-Command docker @("tag", $imageId, $backendImageTag)

    $imageTar = Join-Path $OutputPath "agenthub-backend-linux-amd64.tar"
    if (Test-Path $imageTar) {
        Remove-Item $imageTar -Force
    }
    Log "Saving backend image tar. This can take a while..."
    Run-Command docker @("save", "-o", $imageTar, $backendImageTag)
    $manifest["backend_image_tar"] = "agenthub-backend-linux-amd64.tar"
    $manifest["backend_image_tag"] = $backendImageTag
    $manifest["backend_image_id"] = $imageId
}

if (-not $SkipDatabase.IsPresent) {
    $pgUser = Read-DotEnvValue "POSTGRES_USER" "agenthub"
    $pgDb = Read-DotEnvValue "POSTGRES_DB" "agenthub"
    Log "Ensuring Postgres is running for pg_dump..."
    Run-Command docker @("compose", "up", "-d", "postgres")
    Log "Waiting for Postgres to become ready..."
    $deadline = (Get-Date).AddMinutes(2)
    do {
        & docker compose exec -T postgres pg_isready -U $pgUser | Out-Null
        if ($LASTEXITCODE -eq 0) {
            break
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if ($LASTEXITCODE -ne 0) {
        throw "Postgres did not become ready in time."
    }
    $sqlPath = Join-Path $OutputPath "agenthub.sql"
    if (Test-Path $sqlPath) {
        Remove-Item $sqlPath -Force
    }
    Log "Exporting database dump..."
    docker compose exec -T postgres pg_dump -U $pgUser $pgDb | Set-Content -Path $sqlPath -Encoding UTF8
    if ($LASTEXITCODE -ne 0) {
        throw "Database export failed."
    }
    $manifest["database_dump"] = "agenthub.sql"
}

if (-not $SkipWorkspaces.IsPresent -and (Test-Path "workspaces")) {
    Log "Exporting workspaces..."
    $workspaceTar = Join-Path $OutputPath "workspaces.tgz"
    if (Test-Path $workspaceTar) {
        Remove-Item $workspaceTar -Force
    }
    Run-Command tar @("-czf", $workspaceTar, "workspaces")
    $manifest["workspaces_archive"] = "workspaces.tgz"
}

if (-not $SkipUploads.IsPresent) {
    Log "Exporting uploads-data volume..."
    Run-Command docker @(
        "compose", "run", "--rm", "-T",
        "-v", "${OutputPath}:/export",
        "backend",
        "sh", "-lc",
        "mkdir -p /app/data/uploads && tar czf /export/uploads-data.tgz -C /app/data/uploads ."
    )
    $manifest["uploads_archive"] = "uploads-data.tgz"
}

if (-not $SkipRuntimeState.IsPresent) {
    Log "Exporting Claude runtime state..."
    Run-Command docker @(
        "compose", "run", "--rm", "-T",
        "-v", "${OutputPath}:/export",
        "backend",
        "sh", "-lc",
        'mkdir -p "$AGENTHUB_CLAUDE_AUTH_DIR" && tar czf /export/claude-state.tgz -C "$AGENTHUB_CLAUDE_AUTH_DIR" .'
    )
    $manifest["claude_state_archive"] = "claude-state.tgz"

    Log "Exporting OpenCode runtime state..."
    Run-Command docker @(
        "compose", "run", "--rm", "-T",
        "-v", "${OutputPath}:/export",
        "backend",
        "sh", "-lc",
        'mkdir -p "$AGENTHUB_OPENCODE_AUTH_DIR" && tar czf /export/opencode-state.tgz -C "$AGENTHUB_OPENCODE_AUTH_DIR" .'
    )
    $manifest["opencode_state_archive"] = "opencode-state.tgz"
}

if ($TargetPlatform -eq "windows") {
    Copy-Item "docs/windows-codex-deploy-handoff.md" (Join-Path $OutputPath "WINDOWS_CODEX_READ_THIS.md") -Force
} else {
    Copy-Item "docs/mac-codex-deploy-handoff.md" (Join-Path $OutputPath "MAC_CODEX_READ_THIS.md") -Force
}

$manifest | ConvertTo-Json -Depth 5 |
    Set-Content -Path (Join-Path $OutputPath "package-manifest.json") -Encoding UTF8

Log "Package is ready: $OutputPath"
if ($TargetPlatform -eq "windows") {
    Log "Give this folder to the Windows Codex. It should read WINDOWS_CODEX_READ_THIS.md first."
} else {
    Log "Give this folder to the Mac Codex. It should read MAC_CODEX_READ_THIS.md first."
}
