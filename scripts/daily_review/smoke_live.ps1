# Smoke test — preflight + dry-run (no live calendar side effects)
# Usage: .\scripts\smoke_live.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = (Resolve-Path "..\..\done\small\jira-release-tool\.venv\Scripts\python.exe" -ErrorAction SilentlyContinue)
if (-not $Python) { $Python = "python" } else { $Python = $Python.Path }

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
