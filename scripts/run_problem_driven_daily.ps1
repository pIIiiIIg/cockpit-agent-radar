param(
    [string]$RepoPath = "C:\Users\Administrator\Projects\cockpit-agent-radar",
    [string]$HarnessPath = "C:\Users\Administrator\Projects\StreamingModelHarness"
)

$ErrorActionPreference = "Stop"
$Git = "C:\Program Files\Git\cmd\git.exe"
$Python = "C:\Program Files\Cloudbase Solutions\Cloudbase-Init\Python\python.exe"
$Agent = Join-Path $env:LOCALAPPDATA "cursor-agent\cursor-agent.cmd"
$Log = Join-Path $RepoPath "daily-report-agent.log"
$Lock = Join-Path $RepoPath ".daily-report-agent.lock"

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
}

if (Test-Path $Lock) {
    Write-Log "SKIP: another daily report run owns the lock"
    exit 0
}
New-Item -ItemType File -Path $Lock -Force | Out-Null
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
    $prompt = Get-Content (Join-Path $RepoPath "DAILY_REPORT_AGENT.md") `
        -Raw -Encoding UTF8
    Run-Native {
        & $Agent --print --force --trust --workspace $RepoPath `
            --model "gpt-5.6-sol-xhigh" --output-format text $prompt
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
