$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
  Write-Host "Creating virtual environment..."
  py -3 -m venv .venv
}

Write-Host "Installing/updating dependencies..."
& ".venv\\Scripts\\python.exe" -m pip install -r requirements.txt

Write-Host "Starting GamingBoxd at http://127.0.0.1:8000"
Write-Host "Press Ctrl+C to stop."
& ".venv\\Scripts\\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
