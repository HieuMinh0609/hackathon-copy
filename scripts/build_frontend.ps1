param(
    [ValidateSet("windows", "linux", "macos", "web", "apk", "aab", "ipa")]
    [string]$Target = "windows",
    [string]$Version = "1.0.0",
    [string]$BuildNumber = "1",
    [switch]$ClearCache,
    [switch]$PrepareOnly
)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} else {
    throw "Khong tim thay Python 3.11."
}

$arguments = @(
    (Join-Path $PSScriptRoot "build_frontend.py"),
    "--target", $Target,
    "--version", $Version,
    "--build-number", $BuildNumber
)
if ($ClearCache) { $arguments += "--clear-cache" }
if ($PrepareOnly) { $arguments += "--prepare-only" }

& $python @arguments
exit $LASTEXITCODE
