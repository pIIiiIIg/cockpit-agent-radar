param(
    [string]$RepoPath = "",
    [string]$TargetDate = "",
    [string]$HarnessPath = "C:\Users\Administrator\Projects\StreamingModelHarness",
    [string]$HarnessSolutionsPath = "",
    [string]$HarnessSolutionsBranch = "automation/agent-h20-loop",
    [string]$Model = $(if ($env:RADAR_AGENT_MODEL) {
        $env:RADAR_AGENT_MODEL
    } else { "composer-2.5" })
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
$Packet = Join-Path ([IO.Path]::GetTempPath()) "radar-daily-packet-$PID.json"

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
    $harnessQueued = 0
    $harnessStatus = Join-Path $HarnessSolutionsPath `
        "evolution\state\agent-h20-loop\STATUS.json"
    if (Test-Path $harnessStatus) {
        try {
            $statusValue = Get-Content $harnessStatus -Raw -Encoding UTF8 | ConvertFrom-Json
            $harnessQueued = [int]($statusValue.queued_candidate_count)
        }
        catch {
            Write-AutomationLog $Log "Harness queue status unreadable; preserving zero"
        }
    }
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") report `
            --public-status (Join-Path $RepoPath "data\cost_status.json") `
            --queued-harness-candidates $harnessQueued
    } $Log
    $packetMeta = (
        & $Python (Join-Path $RepoPath "scripts\build_agent_packet.py") `
            --repo $RepoPath --kind daily-report --target-date $TargetDate `
            --output $Packet | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw "could not build deterministic daily-report skeleton" }
    $prompt = (
        "Read DAILY_REPORT_AGENT.md and the deterministic fact skeleton at $Packet. " +
        "Generate the two reports for catch-up date $TargetDate. Do not scan docs/ or the " +
        "full item archive, do not ask clarifying questions, and finish with REPORT_TASK_COMPLETE.")
    $reportArtifact = Join-Path $RepoPath "reports\*-$TargetDate.md"
    $agentRun = Invoke-AgentRetry -Agent $Agent -RepoPath $RepoPath `
        -Prompt $prompt -Sentinel "REPORT_TASK_COMPLETE" -Log $Log `
        -Python $Python -Pipeline "radar" -Stage "daily_report" -Model $Model `
        -InputHash $packetMeta.input_hash -PromptVersion "radar-daily-report-v2" `
        -CacheKind "daily_report" -CacheArtifact $reportArtifact `
        -ReservationUsd 7.5 -Attempts 2
    if ($agentRun.Decision -eq "cached") {
        Write-AutomationLog $Log "SUCCESS: unchanged daily-report input reused"
        exit 0
    }
    if ($agentRun.Decision -in @("queued", "blocked")) {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") report `
            --public-status (Join-Path $RepoPath "data\cost_status.json") | Out-Null
        Write-AutomationLog $Log "SUCCESS: daily report queued by cost policy"
        exit 0
    }
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
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") report `
            --public-status (Join-Path $RepoPath "data\cost_status.json")
    } $Log
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\build_site.py") } $Log
    Invoke-NativeLogged { & $Git -C $RepoPath diff --check } $Log
    Invoke-NativeLogged {
        & $Git -C $RepoPath add reports project_status data/harness_solutions.json `
            data/handoff data/cost_status.json docs
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
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") cache-put `
            --kind "daily_report" --input-hash $packetMeta.input_hash `
            --prompt-version "radar-daily-report-v2" --model $Model `
            --result-hash $agentRun.ResultHash --artifact $reportArtifact
    } $Log
    Write-AutomationLog $Log "SUCCESS date=$TargetDate"
    exit 0
}
catch {
    Write-AutomationLog $Log "FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item $Packet -Force -ErrorAction SilentlyContinue
    Remove-Item $Lock -Force -ErrorAction SilentlyContinue
}
