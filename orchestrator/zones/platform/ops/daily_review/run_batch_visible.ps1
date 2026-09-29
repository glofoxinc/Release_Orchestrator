# Schedule N calls — opens Edge once for abcfitness.com login, then creates all meetings.
param(
    [string]$Date = "",
    [string]$StartAt = "20:00",
    [int]$Count = 5,
    [int]$Duration = 10
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
$env:PYTHONPATH = $ProjectRoot
Set-Location $ProjectRoot

$dateArg = if ($Date) { "--date $Date" } else { "" }
& $Python -m daily_review_agent --schedule-batch --start-at $StartAt --count $Count --duration $Duration $dateArg.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
exit $LASTEXITCODE
