Set-StrictMode -Version Latest

$AutomationProfile = if ($env:RADAR_AUTOMATION_USER_PROFILE) {
    $env:RADAR_AUTOMATION_USER_PROFILE
} else {
    "C:\Users\Administrator"
}
$env:USERPROFILE = $AutomationProfile
$env:HOME = $AutomationProfile
$env:LOCALAPPDATA = Join-Path $AutomationProfile "AppData\Local"
$env:APPDATA = Join-Path $AutomationProfile "AppData\Roaming"

function Write-AutomationLog([string]$Path, [string]$Message) {
    Add-Content -Path $Path -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message" -Encoding UTF8
}

function Acquire-RadarLock {
    param([string]$Lock, [string]$Log, [int]$WaitMinutes = 360)
    $deadline = (Get-Date).AddMinutes($WaitMinutes)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $Lock) {
            $ownerText = @(Get-Content $Lock -Raw -ErrorAction SilentlyContinue) -join ""
            $ownerText = $ownerText.Trim()
            $owner = 0
            $alive = ([int]::TryParse($ownerText, [ref]$owner) -and
                (Get-Process -Id $owner -ErrorAction SilentlyContinue))
            $ageHours = ((Get-Date) - (Get-Item $Lock).LastWriteTime).TotalHours
            if (-not $alive -and ($ageHours -ge 6 -or -not $ownerText)) {
                Write-AutomationLog $Log "RECOVER stale lock pid=$ownerText age=$([int]$ageHours)h"
                Remove-Item $Lock -Force -ErrorAction SilentlyContinue
                continue
            }
            Write-AutomationLog $Log "QUEUE lock pid=$ownerText; waiting"
            Start-Sleep -Seconds 60
            continue
        }
        try {
            $stream = [IO.File]::Open(
                $Lock, [IO.FileMode]::CreateNew,
                [IO.FileAccess]::Write, [IO.FileShare]::None)
            $bytes = [Text.Encoding]::UTF8.GetBytes([string]$PID)
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Dispose()
            return
        }
        catch [IO.IOException] { Start-Sleep -Seconds 5 }
    }
    throw "timed out waiting for radar automation lock"
}

function Invoke-NativeLogged {
    param([scriptblock]$Command, [string]$Log)
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $Command 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    $output | ForEach-Object { Write-AutomationLog $Log "$_" }
    if ($code -ne 0) { throw "native command failed with exit code $code" }
    return $output
}

function Test-AgentModelAvailable {
    param([string]$Agent, [string]$Model, [string]$Python, [string]$Log)
    $models = & $Agent --list-models 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Cursor model discovery failed closed (exit $code)" }
    $available = @($models | ForEach-Object {
        if ($_ -match '^(\S+)\s+-\s+') { $Matches[1] }
    })
    if ($available -notcontains $Model) {
        throw "configured Cursor model is unavailable: $Model"
    }
    & $Python (Join-Path $PSScriptRoot "model_canary.py") verify --model $Model | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "configured model has no passing fixed Radar canary: $Model"
    }
    Write-AutomationLog $Log "MODEL_AVAILABLE: $Model"
}

function Invoke-AgentRetry {
    param(
        [string]$Agent, [string]$RepoPath, [string]$Prompt,
        [string]$Sentinel, [string]$Log, [string]$Python,
        [string]$Pipeline, [string]$Stage, [string]$Model,
        [string]$InputHash, [string]$PromptVersion,
        [string]$CacheKind, [string]$CacheArtifact,
        [double]$ReservationUsd, [int]$Attempts = 2)
    $CostScript = Join-Path $PSScriptRoot "cost_governance.py"
    $cache = & $Python $CostScript cache-get --kind $CacheKind `
        --input-hash $InputHash --prompt-version $PromptVersion --model $Model 2>$null
    if ($LASTEXITCODE -eq 0 -and (Test-Path $CacheArtifact)) {
        Write-AutomationLog $Log "CACHE_HIT: kind=$CacheKind input=$InputHash"
        return [pscustomobject]@{
            Decision = "cached"; Output = @(); ChatId = ""; Attempts = 0
        }
    }
    Test-AgentModelAvailable -Agent $Agent -Model $Model -Python $Python -Log $Log
    $chatOutput = @(& $Agent create-chat 2>&1)
    if ($LASTEXITCODE -ne 0 -or -not $chatOutput) {
        throw "Cursor Agent failed to create one resumable chat"
    }
    $chatId = ($chatOutput[-1] | Out-String).Trim()
    if (-not $chatId) { throw "Cursor Agent returned an empty chat id" }
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        Write-AutomationLog $Log "AGENT attempt $attempt/$Attempts chat=$chatId model=$Model"
        $reservationJson = @(& $Python $CostScript reserve `
            --pipeline $Pipeline --stage $Stage --pool "radar_review_report" `
            --model $Model --chat-session $chatId --attempt $attempt `
            --reservation-usd $ReservationUsd --input-hash $InputHash 2>&1)
        $reserveCode = $LASTEXITCODE
        if ($reserveCode -in @(3, 4)) {
            $decision = (($reservationJson -join "`n") | ConvertFrom-Json)
            Write-AutomationLog $Log (
                "BUDGET_$($decision.decision.ToUpper()): $($decision.reason)")
            return [pscustomobject]@{
                Decision = $decision.decision; Reason = $decision.reason
                Output = @(); ChatId = $chatId; Attempts = ($attempt - 1)
            }
        }
        if ($reserveCode -ne 0) { throw "cost reservation failed closed" }
        $reservation = (($reservationJson -join "`n") | ConvertFrom-Json)
        $old = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $output = @(& $Agent --resume $chatId --print --force --trust `
            --workspace $RepoPath --model $Model --output-format json $Prompt 2>&1)
        $code = $LASTEXITCODE
        $ErrorActionPreference = $old
        $outputPath = Join-Path ([IO.Path]::GetTempPath()) (
            "radar-agent-output-$PID-$attempt.json")
        Set-Content -Path $outputPath -Value ($output -join "`n") -Encoding UTF8
        $reconcileArgs = @(
            $CostScript, "reconcile", "--call-id", $reservation.call_id,
            "--output-file", $outputPath)
        if ($code -ne 0) {
            $reconcileArgs += @("--failed", "--error", "Cursor Agent exit code $code")
        }
        $reconciledJson = @(& $Python @reconcileArgs 2>&1)
        $reconcileCode = $LASTEXITCODE
        Remove-Item $outputPath -Force -ErrorAction SilentlyContinue
        if ($reconcileCode -ne 0) { throw "cost reconciliation failed closed" }
        $reconciled = (($reconciledJson -join "`n") | ConvertFrom-Json)
        Write-AutomationLog $Log (
            "AGENT_USAGE source=$($reconciled.usage_source) " +
            "actual_usd=$($reconciled.actual_usd) tools=$($reconciled.tool_calls)")
        $resultText = $output -join "`n"
        if ($code -eq 0 -and $resultText -match [regex]::Escape($Sentinel)) {
            return [pscustomobject]@{
                Decision = "completed"; Output = $output; ChatId = $chatId
                Attempts = $attempt; ResultHash = $reconciled.result_hash
            }
        }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds (30 * $attempt) }
    }
    throw "Agent failed to emit $Sentinel after $Attempts attempts"
}

function Save-DirtyRecovery {
    param(
        [string]$Git, [string]$RepoPath, [string]$Log,
        [string]$ReturnBranch = "main")
    $stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
    $recovery = "recovery/local-$stamp-$PID"
    Write-AutomationLog $Log "RECOVERY creating $recovery"
    Invoke-NativeLogged { & $Git -C $RepoPath switch -c $recovery } $Log
    Invoke-NativeLogged { & $Git -C $RepoPath add -A } $Log
    $staged = @(& $Git -C $RepoPath diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw "could not inspect recovery files" }
    if (-not $staged) {
        throw "dirty worktree had no safe files eligible for recovery"
    }
    $unsafe = @($staged | Where-Object {
        $_ -match '(^|/)(\.env[^/]*|[^/]+\.(log|lock|key|pem))$' -or
        $_ -eq ".radar-agent.lock"
    })
    if ($unsafe) {
        throw "refusing to commit sensitive runtime files: $($unsafe -join ', ')"
    }
    Invoke-NativeLogged {
        & $Git -C $RepoPath -c user.name="radar-recovery-agent" `
            -c user.email="radar-recovery-agent@users.noreply.github.com" `
            commit -m "recovery: preserve failed automation run $stamp"
    } $Log
    Invoke-NativeLogged { & $Git -C $RepoPath switch $ReturnBranch } $Log
    Write-AutomationLog $Log "RECOVERY saved $recovery"
    return $recovery
}

function Update-FromMain {
    param([string]$Git, [string]$RepoPath, [string]$Log)
    $dirty = & $Git -C $RepoPath status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "git status failed" }
    if ($dirty) {
        Save-DirtyRecovery -Git $Git -RepoPath $RepoPath -Log $Log `
            -ReturnBranch "main"
    }
    else {
        $branch = (& $Git -C $RepoPath branch --show-current).Trim()
        if ($LASTEXITCODE -ne 0) { throw "could not inspect automation branch" }
        if ($branch -ne "main") {
            Invoke-NativeLogged { & $Git -C $RepoPath switch main } $Log
        }
    }
    Invoke-NativeLogged { & $Git -C $RepoPath fetch origin main } $Log
    $env:GIT_COMMITTER_NAME = "radar-automation"
    $env:GIT_COMMITTER_EMAIL = "radar-automation@users.noreply.github.com"
    Invoke-NativeLogged { & $Git -C $RepoPath -c core.editor=true rebase origin/main } $Log
}

function Publish-WithRetry {
    param(
        [string]$Git, [string]$Python, [string]$RepoPath,
        [string]$Log, [int]$Attempts = 4)
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $old = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $push = & $Git -C $RepoPath push origin HEAD:main 2>&1
        $code = $LASTEXITCODE
        $ErrorActionPreference = $old
        $push | ForEach-Object { Write-AutomationLog $Log "push: $_" }
        if ($code -eq 0) { return }
        if ($attempt -eq $Attempts) { break }
        Invoke-NativeLogged { & $Git -C $RepoPath fetch origin main } $Log
        $env:GIT_COMMITTER_NAME = "radar-automation"
        $env:GIT_COMMITTER_EMAIL = "radar-automation@users.noreply.github.com"
        $old = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $rebase = & $Git -C $RepoPath -c core.editor=true rebase origin/main 2>&1
        $rebaseCode = $LASTEXITCODE
        $ErrorActionPreference = $old
        $rebase | ForEach-Object { Write-AutomationLog $Log "rebase: $_" }
        if ($rebaseCode -ne 0) {
            $unmerged = @(& $Git -C $RepoPath diff --name-only --diff-filter=U)
            if ($unmerged.Count -gt 0 -and
                    @($unmerged | Where-Object { $_ -notlike "docs/*" }).Count -eq 0) {
                Invoke-NativeLogged {
                    & $Python (Join-Path $RepoPath "scripts\build_site.py")
                } $Log
                Invoke-NativeLogged { & $Git -C $RepoPath add docs } $Log
                Invoke-NativeLogged {
                    & $Git -C $RepoPath -c core.editor=true rebase --continue
                } $Log
            }
            else { throw "rebase has non-generated conflicts: $($unmerged -join ', ')" }
        }
        Start-Sleep -Seconds (10 * $attempt)
    }
    throw "push failed after $Attempts attempts"
}
