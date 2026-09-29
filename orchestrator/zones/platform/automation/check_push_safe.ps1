# Pre-push safety check — run from repo root before git push
# Usage: orchestrator\zones\platform\automation\check_push_safe.ps1

$ErrorActionPreference = "Continue"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
Set-Location $RepoRoot

$fail = $false
$envPath = "orchestrator\zones\runtime\local\.env"

Write-Host "=== Push safety check ===" -ForegroundColor Cyan

$envTracked = @(git ls-files $envPath ".env" 2>$null)
if ($envTracked.Count -gt 0) {
    Write-Host "[FAIL] .env is TRACKED by git — run: git rm --cached <path>" -ForegroundColor Red
    $fail = $true
} elseif (Test-Path $envPath) {
    Write-Host "[OK]   $envPath exists locally but is NOT tracked" -ForegroundColor Green
} else {
    Write-Host "[OK]   No local .env (copy from .env.example when setting up)" -ForegroundColor Green
}

$mcpTracked = @(git ls-files ".cursor/mcp.json" "orchestrator/.cursor/mcp.json" 2>$null)
if ($mcpTracked.Count -gt 0) {
    Write-Host "[FAIL] MCP config is TRACKED — may contain tokens" -ForegroundColor Red
    $fail = $true
} elseif (Test-Path ".cursor/mcp.json") {
    Write-Host "[OK]   .cursor/mcp.json exists locally and is gitignored" -ForegroundColor Green
} else {
    Write-Host "[OK]   No .cursor/mcp.json (optional)" -ForegroundColor Green
}

$staged = @(git diff --cached --name-only 2>$null)
$bad = $staged | Where-Object { $_ -match '(?i)(^|/)\.env$|secrets\.toml|credentials\.json$' }
if ($bad.Count -gt 0) {
    Write-Host "[FAIL] Staged secret-like files: $($bad -join ', ')" -ForegroundColor Red
    $fail = $true
} else {
    Write-Host "[OK]   No obvious secret files staged" -ForegroundColor Green
}

Write-Host ""
if ($fail) {
    Write-Host "Fix issues before pushing. See orchestrator/zones/knowledge/guides/PUSH_SAFETY.md" -ForegroundColor Red
    exit 1
}
Write-Host "Safe to push (still review 'git status' manually)." -ForegroundColor Green
exit 0
