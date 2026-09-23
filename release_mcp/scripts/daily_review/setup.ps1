# Daily Review + Release Orchestrator — unified setup
# Usage: .\release_mcp\scripts\daily_review\setup.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$ScriptsDir = $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

Write-Host "Release Orchestrator + Daily Review — Setup" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

Set-Location $RepoRoot

Write-Host "`n[1/5] npm install (Playwright + Teams bridge)..." -ForegroundColor Yellow
Set-Location $ScriptsDir
npm install
if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

Write-Host "`n[2/5] Playwright Edge browser..." -ForegroundColor Yellow
npx playwright install msedge
if ($LASTEXITCODE -ne 0) { throw "playwright install msedge failed" }

Set-Location $RepoRoot

if (-not (Test-Path $VenvPython)) {
    Write-Warning ".venv not found — create: python -m venv .venv ; .\.venv\Scripts\pip install -e '.[calendar,dev]'"
} else {
    Write-Host "`n[3/5] Python packages..." -ForegroundColor Yellow
    & $VenvPython -m pip install -e ".[calendar,daily_review,dev]" -q
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

$EnvExample = Join-Path $RepoRoot ".env.example"
$EnvFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Write-Host "`n[4/5] Copy .env.example -> .env" -ForegroundColor Yellow
    Copy-Item $EnvExample $EnvFile
} else {
    Write-Host "`n[4/5] .env already exists — skipped" -ForegroundColor Gray
}

Write-Host "`n[5/5] Pre-flight (dry)..." -ForegroundColor Yellow
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
& $Python -m daily_review_agent --preflight

Write-Host "`nNext steps:" -ForegroundColor Green
Write-Host "  1. Cursor: release_orchestrator(message='welcome onboard')  — release + daily review MCP on same server"
Write-Host "  2. Cursor: daily_review_setup(install=true)"
Write-Host "  3. Cursor: teams_login  — one-time Teams session"
Write-Host "  4. python -m daily_review_agent --outlook-login  — one-time Outlook web (abcfitness.com)"
Write-Host "  5. Cursor: daily_review_preflight(live=true, force=true)"
Write-Host "  6. Cursor: daily_review_run_live(force=true)"
