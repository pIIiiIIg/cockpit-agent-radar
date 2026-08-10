param(
    [string]$RepoPath = "",
    [string]$TargetDate = "",
    [string]$HarnessPath = "C:\Users\Administrator\Projects\StreamingModelHarness",
    [string]$HarnessSolutionsPath = "",
    [string]$HarnessSolutionsBranch = "automation/agent-h20-loop",
    [switch]$AllowAgentFallback,
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
    foreach ($required in ($Git, $Python)) {
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
    $harnessScheduleStatus = "unknown"
    $harnessNoAgentDay = $false
    $harnessStatus = Join-Path $HarnessSolutionsPath `
        "evolution\state\agent-h20-loop\STATUS.json"
    if (Test-Path $harnessStatus) {
        try {
            $statusValue = Get-Content $harnessStatus -Raw -Encoding UTF8 | ConvertFrom-Json
            $harnessQueued = [int]($statusValue.queued_candidate_count)
            $harnessScheduleStatus = [string]($statusValue.classification)
            $harnessNoAgentDay = [bool]($statusValue.no_agent_day)
        }
        catch {
            Write-AutomationLog $Log "Harness queue status unreadable; preserving zero"
        }
    }
    $harnessNoAgentDayText = $harnessNoAgentDay.ToString().ToLowerInvariant()
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") report `
            --public-status (Join-Path $RepoPath "data\cost_status.json") `
            --queued-harness-candidates $harnessQueued `
            --harness-schedule-status $harnessScheduleStatus `
            --harness-no-agent-day $harnessNoAgentDayText
    } $Log
    $packetMeta = (
        & $Python (Join-Path $RepoPath "scripts\build_agent_packet.py") `
            --repo $RepoPath --kind daily-report --target-date $TargetDate `
            --output $Packet | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw "could not build deterministic daily-report skeleton" }
    $reportArtifact = Join-Path $RepoPath "reports\*-$TargetDate.md"
    $deterministicOutput = @(
        & $Python (Join-Path $RepoPath "scripts\build_deterministic_daily.py") `
            --repo $RepoPath --packet $Packet --target-date $TargetDate 2>&1)
    $deterministicCode = $LASTEXITCODE
    $agentRun = $null
    if ($deterministicCode -eq 0) {
        $deterministic = (($deterministicOutput -join "`n") | ConvertFrom-Json)
        Write-AutomationLog $Log (
            "DETERMINISTIC_DAILY: changed=$($deterministic.reports_changed) " +
            "result=$($deterministic.result_hash)")
    }
    elseif ($deterministicCode -eq 2 -and $AllowAgentFallback) {
        if (-not (Test-Path $Agent)) { throw "fallback Agent executable missing: $Agent" }
        $prompt = (
            "Read DAILY_REPORT_AGENT.md and the deterministic fact skeleton at $Packet. " +
            "The local template reported schema_uncovered. Generate the two reports for " +
            "catch-up date $TargetDate without scanning docs/ or the full item archive. " +
            "Finish with REPORT_TASK_COMPLETE.")
        $agentRun = Invoke-AgentRetry -Agent $Agent -RepoPath $RepoPath `
            -Prompt $prompt -Sentinel "REPORT_TASK_COMPLETE" -Log $Log `
            -Python $Python -Pipeline "radar" -Stage "daily_report_fallback" -Model $Model `
            -InputHash $packetMeta.input_hash -PromptVersion "radar-daily-fallback-v1" `
            -CacheKind "daily_report_fallback" -CacheArtifact $reportArtifact `
            -ReservationUsd 4 -Attempts 1
        if ($agentRun.Decision -eq "cached") {
            Write-AutomationLog $Log "SUCCESS: unchanged fallback input reused"
            exit 0
        }
        if ($agentRun.Decision -in @("queued", "blocked")) {
            & $Python (Join-Path $RepoPath "scripts\cost_governance.py") report `
                --public-status (Join-Path $RepoPath "data\cost_status.json") | Out-Null
            Write-AutomationLog $Log "SUCCESS: schema fallback queued by cost policy"
            exit 0
        }
    }
    elseif ($deterministicCode -eq 2) {
        $deterministic = (($deterministicOutput -join "`n") | ConvertFrom-Json)
        Write-AutomationLog $Log (
            "SCHEMA_UNCOVERED: deterministic queue report published; Agent fallback disabled")
    }
    else {
        throw "deterministic daily generator failed: $($deterministicOutput -join ' ')"
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
    if ($null -ne $agentRun -and $agentRun.Decision -eq "completed") {
        Invoke-NativeLogged {
            & $Python (Join-Path $RepoPath "scripts\cost_governance.py") cache-put `
                --kind "daily_report_fallback" --input-hash $packetMeta.input_hash `
                --prompt-version "radar-daily-fallback-v1" --model $Model `
                --result-hash $agentRun.ResultHash --artifact $reportArtifact
        } $Log
    }
    Write-AutomationLog $Log "SUCCESS date=$TargetDate mode=$(if ($agentRun) {'agent_fallback'} else {'deterministic'})"
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
