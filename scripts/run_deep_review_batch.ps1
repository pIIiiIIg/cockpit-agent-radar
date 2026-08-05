param(
    [string]$RepoPath = "",
    [string]$Since = ""
)

$ErrorActionPreference = "Stop"
if (-not $RepoPath) { $RepoPath = Split-Path -Parent $PSScriptRoot }
. (Join-Path $PSScriptRoot "automation_common.ps1")
$Git = "C:\Program Files\Git\cmd\git.exe"
$Python = "C:\Program Files\Cloudbase Solutions\Cloudbase-Init\Python\python.exe"
$Agent = Join-Path $env:LOCALAPPDATA "cursor-agent\cursor-agent.cmd"
$Log = Join-Path $RepoPath "deep-review-agent.log"
$Lock = Join-Path $RepoPath ".radar-agent.lock"

Acquire-RadarLock -Lock $Lock -Log $Log
try {
    Write-AutomationLog $Log "START"
    foreach ($required in ($Git, $Python, $Agent)) {
        if (-not (Test-Path $required)) { throw "required executable missing: $required" }
    }
    Update-FromMain -Git $Git -RepoPath $RepoPath -Log $Log
    $pendingScript = Join-Path $RepoPath "scripts\pending_explanations.py"
    $countArgs = @($pendingScript, "--count-only")
    if ($Since) { $countArgs += @("--since", $Since) }
    $before = [int]((& $Python @countArgs).Trim())
    Write-AutomationLog $Log "PENDING_BEFORE: $before"
    if ($before -eq 0) {
        Write-AutomationLog $Log "SUCCESS: no pending papers"
        exit 0
    }
    $scope = if ($Since) {
        "For this run, only process pending papers whose found date is on or after $Since."
    } else {
        "Use the normal priority order."
    }
    $prompt = "Read DEEP_REVIEW_AGENT.md in this workspace and execute every instruction now. $scope Do not ask clarifying questions. Finish with DEEP_REVIEW_COMPLETE."
    $agentOutput = Invoke-AgentRetry -Agent $Agent -RepoPath $RepoPath `
        -Prompt $prompt -Sentinel "DEEP_REVIEW_COMPLETE" -Log $Log
    $after = [int]((& $Python @countArgs).Trim())
    Write-AutomationLog $Log "PENDING_AFTER: $after"
    if ($after -ge $before) {
        throw "full-text backlog did not decrease"
    }
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\test_explanations.py") } $Log
    Invoke-NativeLogged { & $Python (Join-Path $RepoPath "scripts\build_site.py") } $Log
    Invoke-NativeLogged { & $Git -C $RepoPath diff --check } $Log
    Invoke-NativeLogged {
        & $Git -C $RepoPath add data/explanations.json data/items.json docs
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
    Publish-WithRetry -Git $Git -Python $Python -RepoPath $RepoPath -Log $Log
    Write-AutomationLog $Log "SUCCESS"
    exit 0
}
catch {
    Write-AutomationLog $Log "FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item $Lock -Force -ErrorAction SilentlyContinue
}
