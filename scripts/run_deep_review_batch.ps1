param(
    [string]$RepoPath = "",
    [string]$Since = "",
    [string]$TargetDate = "",
    [string]$HarnessPath = "C:\Users\Administrator\Projects\StreamingModelHarness",
    [string]$HarnessSolutionsPath = "",
    [string]$HarnessSolutionsBranch = "automation/agent-h20-loop",
    [ValidateRange(1, 6)][int]$MaxCanonicalPapers = 6,
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
$Log = Join-Path $RepoPath "deep-review-agent.log"
$Lock = Join-Path $RepoPath ".radar-agent.lock"
$History = Join-Path $RepoPath "data\review_history.json"
$Snapshot = Join-Path ([IO.Path]::GetTempPath()) "radar-review-before-$PID.json"
$HistoryBackup = Join-Path ([IO.Path]::GetTempPath()) "radar-review-history-$PID.json"
$Packet = Join-Path ([IO.Path]::GetTempPath()) "radar-review-packet-$PID.json"
$HadHistory = $false
$Committed = $false

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
    $pendingScript = Join-Path $RepoPath "scripts\pending_explanations.py"
    $countArgs = @($pendingScript, "--count-only")
    if ($Since) { $countArgs += @("--since", $Since) }
    $before = [int]((& $Python @countArgs).Trim())
    Write-AutomationLog $Log "PENDING_BEFORE: $before"
    if ($before -eq 0) {
        Write-AutomationLog $Log "SUCCESS: no pending papers"
        exit 0
    }
    $packetMeta = (
        & $Python (Join-Path $RepoPath "scripts\build_agent_packet.py") `
            --repo $RepoPath --kind deep-review --limit $MaxCanonicalPapers `
            --output $Packet | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw "could not build deterministic review packet" }
    if ([int]$packetMeta.selected_canonical_papers -eq 0) {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") report `
            --public-status (Join-Path $RepoPath "data\cost_status.json") `
            --queued-fulltext-papers 0 | Out-Null
        Write-AutomationLog $Log "SUCCESS: no high-value canonical pending papers"
        exit 0
    }
    $HadHistory = Test-Path $History
    if ($HadHistory) { Copy-Item $History $HistoryBackup -Force }
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\review_history.py") snapshot `
            --output $Snapshot
    } $Log
    $scope = if ($Since) {
        "For this run, only process pending papers whose found date is on or after $Since."
    } else {
        "Use the normal priority order."
    }
    $prompt = (
        "Read DEEP_REVIEW_AGENT.md and the minimal evidence packet at $Packet. " +
        "Process only packet papers; do not scan docs/ or docs/items/. $scope " +
        "Do not ask clarifying questions. Finish with DEEP_REVIEW_COMPLETE.")
    $agentRun = Invoke-AgentRetry -Agent $Agent -RepoPath $RepoPath `
        -Prompt $prompt -Sentinel "DEEP_REVIEW_COMPLETE" -Log $Log `
        -Python $Python -Pipeline "radar" -Stage "deep_review" -Model $Model `
        -InputHash $packetMeta.input_hash -PromptVersion "radar-deep-review-v2" `
        -CacheKind "deep_review" -CacheArtifact $History -ReservationUsd 6 -Attempts 2
    if ($agentRun.Decision -eq "cached") {
        Write-AutomationLog $Log "SUCCESS: unchanged review input reused"
        exit 0
    }
    if ($agentRun.Decision -in @("queued", "blocked")) {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") report `
            --public-status (Join-Path $RepoPath "data\cost_status.json") `
            --queued-fulltext-papers (
                [int]$packetMeta.selected_canonical_papers +
                [int]$packetMeta.queued_canonical_papers) | Out-Null
        Write-AutomationLog $Log (
            "SUCCESS: $($packetMeta.selected_canonical_papers) canonical reviews queued by cost")
        exit 0
    }
    $after = [int]((& $Python @countArgs).Trim())
    Write-AutomationLog $Log "PENDING_AFTER: $after"
    if ($after -ge $before) {
        throw "full-text backlog did not decrease"
    }
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\test_explanations.py") } $Log
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\test_solutions.py") } $Log
    $reviewedAt = [DateTimeOffset]::Now.ToOffset([TimeSpan]::FromHours(8)).ToString("o")
    $runId = "deep-review-$([DateTimeOffset]::Now.ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))"
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\review_history.py") record `
            --before $Snapshot --reviewed-at $reviewedAt --run-id $runId `
            --batch "deep-review" --catchup-for $TargetDate
    } $Log
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\handoff_ledger.py") stage `
            --date $TargetDate --stage fulltext_review --status complete `
            --artifact "data/review_history.json"
    } $Log
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\test_explanations.py") } $Log
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") report `
            --public-status (Join-Path $RepoPath "data\cost_status.json") `
            --queued-fulltext-papers $packetMeta.queued_canonical_papers
    } $Log
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\build_site.py") } $Log
    Invoke-NativeLogged { & $Git -C $RepoPath diff --check } $Log
    Invoke-NativeLogged {
        & $Git -C $RepoPath add data/explanations.json data/items.json `
            data/review_history.json data/harness_solutions.json data/handoff `
            data/cost_status.json docs
    } $Log
    $staged = & $Git -C $RepoPath diff --cached --name-only
    if ($LASTEXITCODE -ne 0) { throw "could not inspect staged files" }
    if (-not $staged) { throw "agent produced no publishable changes" }
    $date = Get-Date -Format "yyyy-MM-dd"
    Invoke-NativeLogged {
        & $Git -C $RepoPath -c user.name="radar-review-agent" `
            -c user.email="radar-review-agent@users.noreply.github.com" `
            commit -m "enhance: $date full-text review batch"
    } $Log
    $Committed = $true
    Publish-WithRetry -Git $Git -Python $Python -RepoPath $RepoPath -Log $Log
    Invoke-NativeLogged {
        & $Python (Join-Path $RepoPath "scripts\cost_governance.py") cache-put `
            --kind "deep_review" --input-hash $packetMeta.input_hash `
            --prompt-version "radar-deep-review-v2" --model $Model `
            --result-hash $agentRun.ResultHash --artifact $History
    } $Log
    Write-AutomationLog $Log "SUCCESS date=$TargetDate"
    exit 0
}
catch {
    if ((Test-Path $Snapshot) -and -not $Committed) {
        if ($HadHistory -and (Test-Path $HistoryBackup)) {
            Copy-Item $HistoryBackup $History -Force
        }
        elseif (-not $HadHistory -and (Test-Path $History)) {
            Remove-Item $History -Force
        }
    }
    Write-AutomationLog $Log "FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item $Snapshot -Force -ErrorAction SilentlyContinue
    Remove-Item $HistoryBackup -Force -ErrorAction SilentlyContinue
    Remove-Item $Packet -Force -ErrorAction SilentlyContinue
    Remove-Item $Lock -Force -ErrorAction SilentlyContinue
}
