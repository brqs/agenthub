param(
    [string]$OutputDir = "windows-codex-package",
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
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$exportScript = Join-Path $ScriptPath "export-agenthub-mac-codex-package.ps1"

$argsList = @(
    "-OutputDir", $OutputDir,
    "-TargetPlatform", "windows"
)

if ($IncludeEnv.IsPresent) { $argsList += "-IncludeEnv" }
if ($SkipSource.IsPresent) { $argsList += "-SkipSource" }
if ($SkipBackendImage.IsPresent) { $argsList += "-SkipBackendImage" }
if ($SkipDatabase.IsPresent) { $argsList += "-SkipDatabase" }
if ($SkipWorkspaces.IsPresent) { $argsList += "-SkipWorkspaces" }
if ($SkipUploads.IsPresent) { $argsList += "-SkipUploads" }
if ($SkipRuntimeState.IsPresent) { $argsList += "-SkipRuntimeState" }
if ($BuildBackendImage.IsPresent) { $argsList += "-BuildBackendImage" }

& powershell -NoProfile -ExecutionPolicy Bypass -File $exportScript @argsList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
