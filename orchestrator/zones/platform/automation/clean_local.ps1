# Remove local caches (safe — regenerated on next run)
# Usage: orchestrator\zones\platform\automation\clean_local.ps1

$ErrorActionPreference = "SilentlyContinue"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
Set-Location $RepoRoot

Write-Host "Cleaning local caches under $RepoRoot" -ForegroundColor Cyan

@(
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".coverage", "htmlcov",
    "orchestrator\zones\runtime\cache", "__pycache__"
) | ForEach-Object {
    if (Test-Path $_) { Remove-Item $_ -Recurse -Force; Write-Host "  removed $_" }
}

python orchestrator/zones/platform/ops/migrate_state.py --apply 2>$null

Write-Host "Done. Kept: orchestrator/zones/runtime/local/.env, orchestrator/.cursor, .github" -ForegroundColor Green
