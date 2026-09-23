# Smoke test — preflight + dry-run (no live calendar side effects)
# Usage: .\release_mcp\scripts\daily_review\smoke_live.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Set-Location $ProjectRoot
$env:PYTHONPATH = $ProjectRoot

Write-Host "Preflight (dry)..." -ForegroundColor Cyan
& $Python -m daily_review_agent --preflight
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Dry run..." -ForegroundColor Cyan
& $Python -m daily_review_agent --dry-run --force
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Demo call (dry)..." -ForegroundColor Cyan
& $Python -m daily_review_agent --demo-call --minutes 15
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Smoke complete." -ForegroundColor Green
