<#
.SYNOPSIS
  LineageLens setup for Windows without Docker.

.DESCRIPTION
  Creates .venv, installs the locked (hash-checked) dependencies and LineageLens itself,
  then optionally starts the app on http://127.0.0.1:8765. Nothing is sent anywhere.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File setup.ps1
  powershell -ExecutionPolicy Bypass -File setup.ps1 -Dev          # + pytest, run the tests
  powershell -ExecutionPolicy Bypass -File setup.ps1 -Run          # install, then start
  powershell -ExecutionPolicy Bypass -File setup.ps1 -Run -Config inputs\lineagelens.yml
#>
[CmdletBinding()]
param(
  [switch]$Dev,
  [switch]$Run,
  [string]$Config = "",
  [ValidateSet("standard", "large")][string]$Sample = "",
  [switch]$Recreate
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Find-Python {
  foreach ($cand in @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3"), @("python"))) {
    $exe = $cand[0]; $rest = @($cand | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    & $exe @rest -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { return , $cand }
  }
  throw "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH')."
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if ($Recreate -and (Test-Path ".venv")) { Remove-Item -Recurse -Force ".venv" }

if (-not (Test-Path $venvPy)) {
  $py = Find-Python
  Write-Host "Creating .venv with $($py -join ' ') ..."
  & $py[0] @($py | Select-Object -Skip 1) -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
}

Write-Host "Installing locked dependencies ..."
& $venvPy -m pip install --disable-pip-version-check -q --upgrade pip
& $venvPy -m pip install --disable-pip-version-check -q --require-hashes -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw "Dependency install failed. Behind a proxy? Set HTTPS_PROXY or PIP_INDEX_URL and retry." }
& $venvPy -m pip install --disable-pip-version-check -q --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw "LineageLens install failed." }
& $venvPy -m lineagelens --version

if ($Dev) {
  & $venvPy -m pip install --disable-pip-version-check -q "pytest==9.1.1" "httpx==0.28.1"
  & $venvPy -m pytest -q
  if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
}

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Write-Host "Tip: copy .env.example to .env to change settings (optional)."
}

if ($Run) {
  $serveArgs = @("serve")
  if ($Config) { $serveArgs += @("-c", $Config) }
  elseif ($Sample) { $serveArgs += @("--sample", $Sample) }
  & $venvPy -m lineagelens @serveArgs
} else {
  Write-Host ""
  Write-Host "Done. Start LineageLens with:"
  Write-Host "  .\.venv\Scripts\lineagelens.exe serve            (bundled sample)"
  Write-Host "  .\.venv\Scripts\lineagelens.exe serve -c inputs\lineagelens.yml"
  Write-Host "Then open http://127.0.0.1:8765"
}
