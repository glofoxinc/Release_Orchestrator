# Release Orchestrator + Daily Review — full E2E setup
# Usage: .\scripts\setup_e2e.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

Write-Host "=== Release Orchestrator E2E Setup ===" -ForegroundColor Cyan

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating venv..." -ForegroundColor Yellow
    python -m venv .venv
}

Write-Host "`n[1/3] Python packages..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m pip install -e ".[calendar,daily_review,dev]" -q

Write-Host "`n[2/3] Daily Review (npm + Playwright Edge)..." -ForegroundColor Yellow
& "$RepoRoot\scripts\daily_review\setup.ps1"

Write-Host "`n[3/3] MCP config reminder..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m daily_review_agent --mcp-config | Out-Null

Write-Host "`n=== E2E ready checklist ===" -ForegroundColor Green
Write-Host "  Cursor MCP: release-orchestrator + teams (+ Slack + Playwright plugins)"
Write-Host "  Releases:   release_orchestrator(message='welcome onboard')"
Write-Host "  Daily:      daily_review_orchestrator(message='daily review welcome')"
