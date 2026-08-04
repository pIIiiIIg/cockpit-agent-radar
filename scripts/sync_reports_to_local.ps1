param(
    [string]$RepoPath = "C:\Users\Administrator\Projects\cockpit-agent-radar",
    [string]$SyncPath = "C:\Users\Administrator\sync",
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [int]$MaxAttempts = 10,
    [int]$RetrySeconds = 120
)

$ErrorActionPreference = "Stop"
$Git = "C:\Program Files\Git\cmd\git.exe"
$LogPath = Join-Path $SyncPath "cockpit-radar-report-sync.log"

function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

if (-not (Test-Path $SyncPath)) {
    New-Item -ItemType Directory -Path $SyncPath -Force | Out-Null
}
if (-not (Test-Path $Git)) {
    Write-Log "FAILED: Git not found: $Git"
    exit 2
}
if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    Write-Log "FAILED: local repository not found: $RepoPath"
    exit 3
}

$ReportsPath = Join-Path $RepoPath "reports"
for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    Write-Log "Checking daily reports: attempt $attempt/$MaxAttempts"
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $gitOutput = & $Git -C $RepoPath pull --ff-only origin main 2>&1
    $gitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    $gitOutput | ForEach-Object { Write-Log "git: $_" }
    if ($gitCode -ne 0) {
        Write-Log "FAILED: git pull failed; refusing to overwrite local changes"
        exit 4
    }

    $TodayReports = @(Get-ChildItem -Path $ReportsPath -Filter "*-$Date.md" `
        -File -ErrorAction SilentlyContinue)
    if ($TodayReports.Count -ge 2) {
        $TodayReports | Copy-Item -Destination $SyncPath -Force
        Write-Log "SUCCESS: synced $($TodayReports.Count) reports for $Date"
        exit 0
    }

    if ($attempt -lt $MaxAttempts) {
        Write-Log "Reports not ready; retrying in $RetrySeconds seconds"
        Start-Sleep -Seconds $RetrySeconds
    }
}

Write-Log "TIMEOUT: reports not found after $($MaxAttempts * $RetrySeconds / 60) minutes"
exit 5
