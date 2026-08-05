param(
    [string]$RepoPath = "C:\Users\Administrator\Projects\cockpit-agent-radar",
    [string]$HarnessPath = "C:\Users\Administrator\Projects\StreamingModelHarness"
)

$ErrorActionPreference = "Stop"
$Git = "C:\Program Files\Git\cmd\git.exe"
$Python = "C:\Program Files\Cloudbase Solutions\Cloudbase-Init\Python\python.exe"
$Agent = Join-Path $env:LOCALAPPDATA "cursor-agent\cursor-agent.cmd"
$Log = Join-Path $RepoPath "daily-report-agent.log"
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
    Write-Log "SKIP: another daily report run owns the lock"
    exit 0
}
try {
    Write-Log "START"
    foreach ($required in ($Git, $Python, $Agent)) {
        if (-not (Test-Path $required)) { throw "required executable missing: $required" }
    }
    Run-Native { & $Git -C $RepoPath pull --ff-only origin main }
    Run-Native {
        & $Python (Join-Path $RepoPath "scripts\build_project_status.py") `
            --source $HarnessPath
    }
    $prompt = "Read DAILY_REPORT_AGENT.md in this workspace and execute every instruction now. Do not ask clarifying questions; infer the date and scope from the repository. Finish with REPORT_TASK_COMPLETE."
    $agentOutput = Run-Native {
        & $Agent --print --force --trust --workspace $RepoPath `
            --model "gpt-5.6-sol-xhigh" --output-format text $prompt
    }
    if (($agentOutput -join "`n") -notmatch "REPORT_TASK_COMPLETE") {
        throw "agent did not emit REPORT_TASK_COMPLETE"
    }
    $today = Get-Date -Format "yyyy-MM-dd"
    $todayReports = @(Get-ChildItem (Join-Path $RepoPath "reports") `
        -Filter "*-$today.md" -File)
    if ($todayReports.Count -lt 2) {
        throw "agent did not create both reports for $today"
    }
    Run-Native { & $Python (Join-Path $RepoPath "scripts\test_explanations.py") }
    Run-Native { & $Python (Join-Path $RepoPath "scripts\build_site.py") }
    Run-Native { & $Git -C $RepoPath diff --check }
    Run-Native { & $Git -C $RepoPath add reports project_status docs }
    $staged = & $Git -C $RepoPath diff --cached --name-only
    if ($LASTEXITCODE -ne 0) { throw "could not inspect staged files" }
    if ($staged) {
        $date = Get-Date -Format "yyyy-MM-dd"
        Run-Native {
            & $Git -C $RepoPath -c user.name="radar-report-agent" `
                -c user.email="radar-report-agent@users.noreply.github.com" `
                commit -m "reports: $date problem-driven research"
        }
        Run-Native { & $Git -C $RepoPath push origin main }
    }
    else {
        Write-Log "NO_CHANGES"
    }
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
