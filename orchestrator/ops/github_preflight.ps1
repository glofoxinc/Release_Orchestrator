<#
.SYNOPSIS
    Local pre-push audit. Exits non-zero if any check fails.

.DESCRIPTION
    Run this before publishing/pushing to GitHub. Verifies:
      - .git exists
      - README.md exists
      - LICENSE exists
      - .gitignore exists
      - .github/workflows/ci.yml exists (at minimum one workflow)
      - No tracked files larger than 50 MB
      - No obvious committed secrets (gitleaks if present; otherwise regex fallback)

    Safe and read-only. Exits with 0 on success, non-zero on any failure.
#>
[CmdletBinding()]
param(
    [switch]$ShowDetails
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$script:failures = @()
$script:passes   = @()

function Pass($name, $detail='') { $script:passes += $name; Write-Host "  [PASS] $name $detail" -ForegroundColor Green }
function Fail($name, $detail='') { $script:failures += "$name $detail"; Write-Host "  [FAIL] $name $detail" -ForegroundColor Red }

Write-Host ""
Write-Host "Preflight audit for: $Root" -ForegroundColor Cyan
Write-Host ("-" * 60)

# 1. .git
if (Test-Path (Join-Path $Root '.git')) { Pass '.git directory' } else { Fail '.git directory' '(not a git repo)' }

# 2. Core docs
foreach ($f in @('README.md','LICENSE','.gitignore')) {
    if (Test-Path (Join-Path $Root $f)) { Pass $f } else { Fail $f '(missing)' }
}

# 3. At least one CI workflow
$workflows = Get-ChildItem -Path (Join-Path $Root '.github\workflows') -Filter '*.yml' -ErrorAction SilentlyContinue
if ($workflows.Count -gt 0) { Pass 'CI workflow' "($($workflows.Count) workflows)" }
else { Fail 'CI workflow' '(no .github/workflows/*.yml found)' }

# 4. Large file check (>50 MB). Use git ls-files to only consider tracked files.
try {
    $big = @()
    $tracked = git -C $Root ls-files 2>$null
    foreach ($rel in $tracked) {
        $p = Join-Path $Root $rel
        if (Test-Path $p) {
            $size = (Get-Item $p -ErrorAction SilentlyContinue).Length
            if ($size -gt 50MB) { $big += [PSCustomObject]@{ Path=$rel; MB=[math]::Round($size/1MB,2) } }
        }
    }
    if ($big.Count -eq 0) { Pass 'No files > 50MB' }
    else {
        Fail 'Large files detected' "($($big.Count))"
        $big | ForEach-Object { Write-Host "      $($_.Path) ($($_.MB) MB)" -ForegroundColor Yellow }
    }
} catch { Fail 'Large file scan' "(error: $($_.Exception.Message))" }

# 5. Secret scan
$gitleaks = Get-Command gitleaks -ErrorAction SilentlyContinue
if ($gitleaks) {
    $r = & gitleaks detect --source $Root --no-banner --redact --exit-code 1 2>&1
    if ($LASTEXITCODE -eq 0) { Pass 'gitleaks (clean)' }
    else {
        Fail 'gitleaks' '(findings reported)'
        if ($ShowDetails) { $r | ForEach-Object { Write-Host "      $_" -ForegroundColor Yellow } }
    }
} else {
    # Regex fallback: scan tracked source/config files for common secret shapes.
    # Rules mirror ../../projects/scan-secrets.py (word-boundary anchored; placeholder
    # values suppressed). The set is deliberately conservative to avoid false positives.
    $rules = @(
        @{ Name = 'AWS Access Key ID';        Pattern = '\bAKIA[0-9A-Z]{16}\b' },
        @{ Name = 'GitHub PAT (ghp_)';        Pattern = '\bghp_[A-Za-z0-9]{36,}\b' },
        @{ Name = 'GitHub fine-grained PAT';  Pattern = '\bgithub_pat_[A-Za-z0-9_]{82,}\b' },
        @{ Name = 'Google API key';           Pattern = '\bAIza[0-9A-Za-z_\-]{35}\b' },
        @{ Name = 'Slack bot token';          Pattern = '\bxox[aboprs]-[A-Za-z0-9\-]{10,}\b' },
        @{ Name = 'Slack webhook';            Pattern = 'https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+' },
        @{ Name = 'Private key header';       Pattern = '-----BEGIN (RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----' },
        @{ Name = 'Stripe live key';          Pattern = '\bsk_live_[0-9a-zA-Z]{24,}\b' },
        @{ Name = 'Generic API key / secret'; Pattern = '(?i)\b(api[_-]?key|secret|token|password|passwd|access[_-]?key)\b\s*[:=]\s*["\x27]([A-Za-z0-9_\-./+=]{24,})["\x27]' }
    )
    $placeholderMarkers = @('YOUR_','YOUR-','_HERE','EXAMPLE','XXXXX','CHANGEME','CHANGE_ME','INSERT_','REDACTED','PLACEHOLDER','FAKETOKEN','TESTTOKEN','DUMMY')
    function Test-IsPlaceholder([string]$rule, [string]$fileName, [string]$full, [string]$value) {
        $lname = $fileName.ToLower()
        if ($lname -match '\.example\.' -or $lname.EndsWith('.sample') -or $lname.EndsWith('.template')) { return $true }
        $upper = $full.ToUpper()
        if ($rule -eq 'Slack webhook' -and ($full -match '/T0+/B0+/[A-Za-z0]+$' -or $full.ToLower().Contains('xxx'))) { return $true }
        if ($rule -eq 'Slack bot token') {
            foreach ($m in $placeholderMarkers) { if ($upper.Contains($m)) { return $true } }
        }
        if ($rule -eq 'Generic API key / secret') {
            if ([string]::IsNullOrWhiteSpace($value)) { return $true }
            $vu = $value.ToUpper()
            foreach ($m in $placeholderMarkers) { if ($vu.Contains($m)) { return $true } }
            if ($value.StartsWith('$`{') -or $value.StartsWith('{{') -or $value.EndsWith('}}')) { return $true }
            if ($value -match '^[a-z]+(?:_[a-z]+){2,}$') { return $true }  # test sentinels
        }
        return $false
    }
    $tracked = git -C $Root ls-files 2>$null |
        Where-Object { $_ -match '\.(env|json|ya?ml|py|ts|tsx|js|jsx|mjs|cjs|ps1|psm1|sh|cfg|ini|toml|md|sql|dax|tmdl)$' } |
        Where-Object { $_ -notmatch '(^|/)(node_modules|\.venv|venv|dist|build|coverage|__pycache__|playwright-report|test-results)/' }
    $found = @()
    foreach ($rel in $tracked) {
        $p = Join-Path $Root $rel
        if (-not (Test-Path $p)) { continue }
        try {
            $txt = Get-Content $p -Raw -ErrorAction SilentlyContinue
            if (-not $txt) { continue }
            foreach ($rule in $rules) {
                foreach ($m in [regex]::Matches($txt, $rule.Pattern)) {
                    $value = if ($m.Groups.Count -ge 3) { $m.Groups[2].Value } else { '' }
                    if (-not (Test-IsPlaceholder $rule.Name (Split-Path -Leaf $rel) $m.Value $value)) {
                        $found += [PSCustomObject]@{ File=$rel; Rule=$rule.Name }
                    }
                }
            }
        } catch {}
    }
    if ($found.Count -eq 0) { Pass 'Secret scan (regex fallback, clean)' }
    else {
        Fail 'Secret scan' "(suspect matches: $($found.Count))"
        $found | ForEach-Object { Write-Host "      $($_.File) :: $($_.Rule)" -ForegroundColor Yellow }
    }
}

# -- summary ----------------------------------------------------------------
Write-Host ""
Write-Host ("-" * 60)
Write-Host ("Passed: {0}   Failed: {1}" -f $script:passes.Count, $script:failures.Count) -ForegroundColor Cyan

if ($script:failures.Count -gt 0) { exit 1 } else { exit 0 }