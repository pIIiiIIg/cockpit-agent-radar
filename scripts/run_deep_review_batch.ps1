param(
    [string]$RepoPath = "C:\Users\Administrator\Projects\cockpit-agent-radar",
    [string]$Since = ""
)

$ErrorActionPreference = "Stop"
$Git = "C:\Program Files\Git\cmd\git.exe"
$Python = "C:\Program Files\Cloudbase Solutions\Cloudbase-Init\Python\python.exe"
$Agent = Join-Path $env:LOCALAPPDATA "cursor-agent\cursor-agent.cmd"
$Log = Join-Path $RepoPath "deep-review-agent.log"
$Lock = Join-Path $RepoPath ".radar-agent.lock"

function Write-Log([string]$Message) {
    Add-Content -Path $Log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message" -Encoding UTF8
}

function Run-Native([scriptblock]$Command) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $Command 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    $output | ForEach-Object { Write-Log "$_" }
    if ($code -ne 0) { throw "native command failed with exit code $code" }
    return $output
}

function Acquire-Lock {
    if (Test-Path $Lock) {
        $ownerText = @(Get-Content $Lock -Raw -ErrorAction SilentlyContinue) -join ""
        $ownerText = $ownerText.Trim()
        $owner = 0
        $alive = ([int]::TryParse($ownerText, [ref]$owner) -and
            (Get-Process -Id $owner -ErrorAction SilentlyContinue))
        $ageHours = ((Get-Date) - (Get-Item $Lock).LastWriteTime).TotalHours
        if ($alive -or ($ownerText -and $ageHours -lt 6)) { return $false }
        Write-Log "RECOVER: removing stale lock pid=$ownerText age=$([int]$ageHours)h"
        Remove-Item $Lock -Force
    }
    try {
        $stream = [System.IO.File]::Open(
            $Lock, [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        $bytes = [Text.Encoding]::UTF8.GetBytes([string]$PID)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Dispose()
        return $true
    }
    catch [System.IO.IOException] { return $false }
}

if (-not (Acquire-Lock)) {
    Write-Log "SKIP: another radar agent owns the lock"
    exit 0
}
try {
    Write-Log "START"
    foreach ($required in ($Git, $Python, $Agent)) {
        if (-not (Test-Path $required)) { throw "required executable missing: $required" }
    }
    Run-Native { & $Git -C $RepoPath pull --ff-only origin main }
    $pendingScript = Join-Path $RepoPath "scripts\pending_explanations.py"
    $countArgs = @($pendingScript, "--count-only")
    if ($Since) { $countArgs += @("--since", $Since) }
    $before = [int]((& $Python @countArgs).Trim())
    Write-Log "PENDING_BEFORE: $before"
    if ($before -eq 0) {
        Write-Log "SUCCESS: no pending papers"
        exit 0
    }
    $scope = if ($Since) {
        "For this run, only process pending papers whose found date is on or after $Since."
    } else {
        "Use the normal priority order."
    }
    $prompt = "Read DEEP_REVIEW_AGENT.md in this workspace and execute every instruction now. $scope Do not ask clarifying questions. Finish with DEEP_REVIEW_COMPLETE."
    $agentOutput = Run-Native {
        & $Agent --print --force --trust --workspace $RepoPath `
            --model "gpt-5.6-sol-xhigh" --output-format text $prompt
    }
    if (($agentOutput -join "`n") -notmatch "DEEP_REVIEW_COMPLETE") {
        throw "agent did not emit DEEP_REVIEW_COMPLETE"
    }
    $after = [int]((& $Python @countArgs).Trim())
    Write-Log "PENDING_AFTER: $after"
    if ($after -ge $before) {
        throw "full-text backlog did not decrease"
    }
    Run-Native { & $Python (Join-Path $RepoPath "scripts\test_explanations.py") }
    Run-Native { & $Python (Join-Path $RepoPath "scripts\build_site.py") }
    Run-Native { & $Git -C $RepoPath diff --check }
    Run-Native {
        & $Git -C $RepoPath add data/explanations.json data/items.json docs
    }
    $staged = & $Git -C $RepoPath diff --cached --name-only
    if ($LASTEXITCODE -ne 0) { throw "could not inspect staged files" }
    if (-not $staged) { throw "agent produced no publishable changes" }
    $date = Get-Date -Format "yyyy-MM-dd"
    Run-Native {
        & $Git -C $RepoPath -c user.name="radar-review-agent" `
            -c user.email="radar-review-agent@users.noreply.github.com" `
            commit -m "enhance: $date full-text review batch"
    }
    Run-Native { & $Git -C $RepoPath push origin main }
    Write-Log "SUCCESS"
    exit 0
}
catch {
    Write-Log "FAILED: $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item $Lock -Force -ErrorAction SilentlyContinue
}
