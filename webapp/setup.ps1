# One-time setup for the local NFL Predictions app.
# Creates a Python venv for the backend, installs its dependencies, and builds the frontend.
# Re-run any time after pulling changes to pick up new dependencies.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "==> Setting up backend (Python venv)" -ForegroundColor Cyan
Push-Location "$root\backend"
if (-not (Test-Path "venv")) {
    python -m venv venv
}
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip -q
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt
Pop-Location

Write-Host "==> Setting up frontend (npm)" -ForegroundColor Cyan
Push-Location "$root\frontend"
npm install
npm run build
Pop-Location

Write-Host "==> Setup complete. Run start_app.bat to launch the app." -ForegroundColor Green
