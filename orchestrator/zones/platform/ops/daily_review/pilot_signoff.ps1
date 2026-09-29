# Pilot sign-off checklist — run manually after Outlook + Teams login
# Daily Review is on-demand only — no Task Scheduler registration.
#
# Usage:
#   .\orchestrator\zones\platform\ops\daily_review\pilot_signoff.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

$SessionMarker = Join-Path $RepoRoot "orchestrator\zones\product\agents\review\.state\playwright-outlook-profile\.outlook_session_ok"
$LastRun = Join-Path $RepoRoot "orchestrator\zones\product\agents\review\.state\last_run.json"
$Node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $Node) { $Node = "node" }
$Bridge = Join-Path $PSScriptRoot "teams_bridge.mjs"

Write-Host ""
Write-Host "=== Daily Review Agent - Pilot Sign-off ===" -ForegroundColor Cyan
Write-Host "Complete each step before your first on-demand live run."
Write-Host ""

$steps = @(
    @{
        Id = 1
        Name = "Outlook web sign-in (Playwright profile)"
        Command = 'python -m daily_review_agent --outlook-login'
        Check = { Test-Path $SessionMarker }
    },
    @{
        Id = 2
        Name = "Teams bridge messaging (summary chat)"
        Command = 'python -m daily_review_agent --teams-login OR teams_login in Cursor'
        Check = {
            if (-not (Test-Path $Bridge)) { return $false }
            Set-Location $PSScriptRoot
            $out = & $Node $Bridge status "{}" 2>$null
            return ($out -match '"authenticated":true')
        }
    },
    @{
        Id = 3
        Name = "Live preflight green"
        Command = 'python -m daily_review_agent --preflight-live --force'
        Check = {
            Set-Location $RepoRoot
            & $Python -m daily_review_agent --preflight-live --force | Out-Null
            return ($LASTEXITCODE -eq 0)
        }
    },
    @{
        Id = 4
        Name = "One live run scheduled meeting (production path)"
        Command = 'python -m daily_review_agent --live --force'
        Check = {
            if (-not (Test-Path $LastRun)) { return $false }
            $raw = Get-Content $LastRun -Raw | ConvertFrom-Json
            return ($null -ne $raw.join_url -or $null -ne $raw.last_run)
        }
    },
    @{
        Id = 5
        Name = "Playwright MCP fallback module present"
        Command = 'daily_review_calendar_playwright_handoff in Cursor'
        Check = {
            Test-Path (Join-Path $RepoRoot "orchestrator\zones\product\agents\review\calendar_playwright_handoff.py")
        }
    }
)

$passed = 0
foreach ($step in $steps) {
    $ok = & $step.Check
    if ($ok) { $passed++ }
    $icon = if ($ok) { "[OK]" } else { "[ ]" }
    $color = if ($ok) { "Green" } else { "Yellow" }
    Write-Host "$icon Step $($step.Id): $($step.Name)" -ForegroundColor $color
    Write-Host "      $($step.Command)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Passed: $passed / $($steps.Count)" -ForegroundColor $(if ($passed -eq $steps.Count) { "Green" } else { "Yellow" })
Write-Host ""
Write-Host "When all steps pass, set enabled: true in orchestrator/zones/product/agents/review/agent.yaml" -ForegroundColor Cyan
Write-Host "Daily Review is on-demand — say daily review welcome when you want the next run." -ForegroundColor Cyan

if ($passed -lt $steps.Count) { exit 1 }

Set-Location $RepoRoot
& $Python -c "import operator_signoff as o; o.record_signoff('daily_review_pilot', detail='pilot_signoff.ps1 all steps passed')"
Write-Host "Recorded operator sign-off: daily_review_pilot" -ForegroundColor Green
exit 0
