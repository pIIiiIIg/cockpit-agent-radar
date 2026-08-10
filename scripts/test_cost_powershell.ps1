Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$files = @(
    "automation_common.ps1",
    "run_deep_review_batch.ps1",
    "run_problem_driven_daily.ps1"
)
$allErrors = @()
foreach ($name in $files) {
    $tokens = $null
    $parseErrors = $null
    $path = Join-Path $PSScriptRoot $name
    [System.Management.Automation.Language.Parser]::ParseFile(
        $path, [ref]$tokens, [ref]$parseErrors) | Out-Null
    $allErrors += @($parseErrors)
}
if ($allErrors.Count) {
    $allErrors | Format-List
    throw "PowerShell syntax validation failed"
}

$common = Get-Content (Join-Path $PSScriptRoot "automation_common.ps1") -Raw
if ($common -notmatch '--resume \$chatId') {
    throw "Agent retry must resume one chat"
}
if ($common -notmatch '\[int\]\$Attempts = 2') {
    throw "Agent retry default must be two attempts"
}
if ($common -match '--model "gpt-5\.6-sol-xhigh"') {
    throw "Radar must not hard-code the expensive model"
}
$deep = Get-Content (Join-Path $PSScriptRoot "run_deep_review_batch.ps1") -Raw
if ($deep -notmatch 'MaxCanonicalPapers = 3' -or
        $deep -notmatch 'ReservationUsd 6 -Attempts 1') {
    throw "Deep review must be one three-paper Composer batch"
}
$daily = Get-Content (Join-Path $PSScriptRoot "run_problem_driven_daily.ps1") -Raw
if ($daily -notmatch 'build_deterministic_daily\.py' -or
        $daily -notmatch 'ReservationUsd 4 -Attempts 1') {
    throw "Daily report must default deterministic with one optional fallback"
}
Write-Output "cost PowerShell tests passed"
