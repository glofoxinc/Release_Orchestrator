# Register Windows Task Scheduler job — Daily Review Agent at 6 PM local
# Usage: .\scripts\daily_review\register_scheduled_task.ps1
# Requires: pilot_signoff.ps1 steps complete, enabled: true in agent.yaml

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
$Script = Join-Path $RepoRoot "scripts\run_daily_review_agent.py"
$TaskName = "DailyReviewAgent-Glofox"
$OutlookMarker = Join-Path $RepoRoot "daily_review_agent\.state\playwright-outlook-profile\.outlook_session_ok"

if (-not (Test-Path $OutlookMarker)) {
    Write-Error "Outlook web session not ready — run: python -m daily_review_agent --outlook-login"
    exit 2
}

Set-Location $RepoRoot
& $Python -m daily_review_agent --preflight-live --force
if ($LASTEXITCODE -ne 0) {
    Write-Error "Live preflight failed — fix blockers before registering Task Scheduler"
    exit $LASTEXITCODE
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`" --live --force" -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "6:00PM"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force

Write-Host "Registered task: $TaskName — daily at 6:00 PM (set machine timezone to IST)" -ForegroundColor Green
Write-Host "Test now: python -m daily_review_agent --live --force"
