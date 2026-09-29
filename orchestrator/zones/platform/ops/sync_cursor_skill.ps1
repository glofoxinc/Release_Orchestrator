# Sync canonical skill into .cursor/skills for Cursor installs that read project skills.
# Usage: .\orchestrator\zones\platform\ops\sync_cursor_skill.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$Canonical = Join-Path $RepoRoot "orchestrator\zones\knowledge\skills\release-orchestrator-mcp\SKILL.md"
$TargetDir = Join-Path $RepoRoot ".cursor\skills\release-orchestrator-mcp"
$Target = Join-Path $TargetDir "SKILL.md"

if (-not (Test-Path $Canonical)) {
    Write-Error "Canonical skill not found: $Canonical"
}

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
$banner = @"
<!-- GENERATED — edit orchestrator/zones/knowledge/skills/release-orchestrator-mcp/SKILL.md then re-run orchestrator/zones/platform/ops/sync_cursor_skill.ps1 -->

"@
$content = Get-Content $Canonical -Raw -Encoding UTF8
Set-Content -Path $Target -Value ($banner + $content) -Encoding UTF8 -NoNewline
Write-Host "Synced -> $Target" -ForegroundColor Green
