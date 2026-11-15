$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.env')) { Copy-Item .env.example .env }
if (!(Test-Path '.venv/Scripts/python.exe')) { python -m venv .venv }
& ./.venv/Scripts/python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies failed' }
Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
& ./.venv/Scripts/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --env-file .env
