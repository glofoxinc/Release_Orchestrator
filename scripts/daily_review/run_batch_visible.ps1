# Schedule N calls — opens Edge once for abcfitness.com login, then creates all meetings.
param(
    [string]$Date = "",
    [string]$StartAt = "20:00",
    [int]$Count = 5,
    [int]$Duration = 10
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = "C:\Users\LYal01\ZABC\projects\done\small\jira-release-tool\.venv\Scripts\python.exe"
$env:PYTHONPATH = $ProjectRoot
Set-Location $ProjectRoot

$dateArg = if ($Date) { "--date $Date" } else { "" }
& $Python -m daily_review_agent --schedule-batch --start-at $StartAt --count $Count --duration $Duration $dateArg.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
exit $LASTEXITCODE
