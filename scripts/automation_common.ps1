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

function Invoke-AgentRetry {
    param(
        [string]$Agent, [string]$RepoPath, [string]$Prompt,
        [string]$Sentinel, [string]$Log, [int]$Attempts = 3)
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        Write-AutomationLog $Log "AGENT attempt $attempt/$Attempts"
        $old = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $output = & $Agent --print --force --trust --workspace $RepoPath `
            --model "gpt-5.6-sol-xhigh" --output-format text $Prompt 2>&1
        $code = $LASTEXITCODE
        $ErrorActionPreference = $old
        $output | ForEach-Object { Write-AutomationLog $Log "$_" }
        if ($code -eq 0 -and ($output -join "`n") -match [regex]::Escape($Sentinel)) {
            return $output
        }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds (30 * $attempt) }
    }
    throw "Agent failed to emit $Sentinel after $Attempts attempts"
}

function Update-FromMain {
    param([string]$Git, [string]$RepoPath, [string]$Log)
    Invoke-NativeLogged { & $Git -C $RepoPath fetch origin main } $Log
    $dirty = & $Git -C $RepoPath status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "git status failed" }
    if ($dirty) { throw "automation clone is dirty before run; refusing to overwrite recovery data" }
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
