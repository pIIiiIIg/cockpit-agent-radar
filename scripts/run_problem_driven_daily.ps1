param(
    [string]$RepoPath = "",
    [string]$TargetDate = "",
    [string]$HarnessPath = "C:\Users\Administrator\Projects\StreamingModelHarness",
    [string]$HarnessSolutionsPath = "",
    [string]$HarnessSolutionsBranch = "automation/agent-h20-loop"
)

$ErrorActionPreference = "Stop"
if (-not $RepoPath) { $RepoPath = Split-Path -Parent $PSScriptRoot }
if (-not $HarnessSolutionsPath) {
    $candidate = Join-Path (Split-Path -Parent $RepoPath) "StreamingModelHarness-autoloop"
    $HarnessSolutionsPath = if (Test-Path $candidate) { $candidate } else { $HarnessPath }
}
. (Join-Path $PSScriptRoot "automation_common.ps1")
$Git = "C:\Program Files\Git\cmd\git.exe"
$Python = "C:\Program Files\Cloudbase Solutions\Cloudbase-Init\Python\python.exe"
$Agent = Join-Path $env:LOCALAPPDATA "cursor-agent\cursor-agent.cmd"
$Log = Join-Path $RepoPath "daily-report-agent.log"
$Lock = Join-Path $RepoPath ".radar-agent.lock"

Acquire-RadarLock -Lock $Lock -Log $Log
try {
    Write-AutomationLog $Log "START"
    foreach ($required in ($Git, $Python, $Agent)) {
        if (-not (Test-Path $required)) { throw "required executable missing: $required" }
    }
    Update-FromMain -Git $Git -RepoPath $RepoPath -Log $Log
    if (-not $TargetDate) {
        $TargetDate = (& $Python (Join-Path $RepoPath "scripts\handoff_ledger.py") next).Trim()
        if ($LASTEXITCODE -ne 0) { throw "could not determine catch-up date" }
    }
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\sync_harness_solutions.py") `
            --source $HarnessSolutionsPath --branch $HarnessSolutionsBranch --git $Git
    } $Log
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\build_project_status.py") `
            --source $HarnessPath
    } $Log
    $prompt = "Read DAILY_REPORT_AGENT.md in this workspace and execute every instruction now. Generate the two reports for catch-up date $TargetDate using current evidence, and label any later evidence by its actual date. Do not ask clarifying questions. Finish with REPORT_TASK_COMPLETE."
    $agentOutput = Invoke-AgentRetry -Agent $Agent -RepoPath $RepoPath `
        -Prompt $prompt -Sentinel "REPORT_TASK_COMPLETE" -Log $Log
    $today = $TargetDate
    $todayReports = @(Get-ChildItem (Join-Path $RepoPath "reports") `
        -Filter "*-$today.md" -File)
    if ($todayReports.Count -lt 2) {
        throw "agent did not create both reports for $today"
    }
    foreach ($stage in ("problem_report", "duplex_report")) {
        Invoke-NativeLogged {
            & $Python (Join-Path $RepoPath "scripts\handoff_ledger.py") stage `
                --date $TargetDate --stage $stage --status complete `
                --artifact "reports/*-$TargetDate.md"
        } $Log
    }
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\test_explanations.py") } $Log
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\test_solutions.py") } $Log
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\build_site.py") } $Log
    Invoke-NativeLogged { & $Git -C $RepoPath diff --check } $Log
    Invoke-NativeLogged {
        & $Git -C $RepoPath add reports project_status data/harness_solutions.json `
            data/handoff docs
    } $Log
    $staged = & $Git -C $RepoPath diff --cached --name-only
    if ($LASTEXITCODE -ne 0) { throw "could not inspect staged files" }
    if ($staged) {
        $date = $TargetDate
        Invoke-NativeLogged {
            & $Git -C $RepoPath -c user.name="radar-report-agent" `
                -c user.email="radar-report-agent@users.noreply.github.com" `
                commit -m "reports: $date problem-driven research"
        } $Log
        Publish-WithRetry -Git $Git -Python $Python -RepoPath $RepoPath -Log $Log
    }
    else {
        Write-AutomationLog $Log "NO_CHANGES"
    }
    Write-AutomationLog $Log "SUCCESS date=$TargetDate"
    exit 0
}
catch {
    Write-AutomationLog $Log "FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item $Lock -Force -ErrorAction SilentlyContinue
}
