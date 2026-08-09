Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "automation_common.ps1")

$Git = "C:\Program Files\Git\cmd\git.exe"
$Root = Join-Path ([IO.Path]::GetTempPath()) "radar-recovery-test-$PID"
$Remote = Join-Path $Root "remote.git"
$Seed = Join-Path $Root "seed"
$Clone = Join-Path $Root "automation"
$Log = Join-Path $Clone "test.log"

function Run-Git {
    param([string]$Path, [Parameter(ValueFromRemainingArguments)] [string[]]$Args)
    & $Git -C $Path @Args | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "git failed in $Path`: $($Args -join ' ')"
    }
}

try {
    New-Item -ItemType Directory -Path $Root | Out-Null
    & $Git init --bare $Remote | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "could not initialize test remote" }
    New-Item -ItemType Directory -Path $Seed | Out-Null
    Run-Git $Seed init
    New-Item -ItemType Directory -Path (Join-Path $Seed "data") | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Seed "docs") | Out-Null
    Set-Content (Join-Path $Seed "data\items.json") '{"version":"base"}'
    Set-Content (Join-Path $Seed "docs\index.html") "base"
    Set-Content (Join-Path $Seed ".gitignore") "*.log`n*.lock`n"
    Run-Git $Seed add .
    Run-Git $Seed -c user.name=test -c user.email=test@example.com commit -m seed
    Run-Git $Seed branch -M main
    Run-Git $Seed remote add origin $Remote
    Run-Git $Seed push -u origin main
    & $Git --git-dir=$Remote symbolic-ref HEAD refs/heads/main
    if ($LASTEXITCODE -ne 0) { throw "could not set test remote HEAD" }
    & $Git clone $Remote $Clone | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "could not clone test remote" }
    Run-Git $Clone switch -c automation/test

    Set-Content (Join-Path $Clone "data\items.json") '{"version":"recovered"}'
    Set-Content (Join-Path $Clone "docs\index.html") "generated recovery"
    Set-Content (Join-Path $Clone "agent.log") "must not be committed"
    Set-Content (Join-Path $Clone ".radar-agent.lock") "999999"

    Update-FromMain -Git $Git -RepoPath $Clone -Log $Log | Out-Null

    $branch = (& $Git -C $Clone branch --show-current).Trim()
    if ($branch -ne "main") { throw "publishing worktree is on $branch, not main" }
    if (& $Git -C $Clone status --porcelain) {
        throw "publishing worktree was not left clean"
    }
    $recovery = @(& $Git -C $Clone branch --format="%(refname:short)" `
        --list "recovery/local-*")
    if ($recovery.Count -ne 1) {
        throw "expected one recovery branch, found $($recovery.Count)"
    }
    $recovered = & $Git -C $Clone show "$($recovery[0]):data/items.json"
    if (($recovered -join "") -notmatch "recovered") {
        throw "recovery branch did not preserve source data"
    }
    $unsafe = @(& $Git -C $Clone ls-tree -r --name-only $recovery[0] |
        Where-Object { $_ -match '(^|/)(agent\.log|\.radar-agent\.lock)$' })
    if ($unsafe) { throw "recovery branch committed logs or locks: $unsafe" }
    $main = & $Git -C $Clone show "main:data/items.json"
    if (($main -join "") -notmatch "base") {
        throw "recovery data leaked into the publishing branch"
    }
    Write-Output "automation recovery test passed"
}
catch {
    if (Test-Path $Log) {
        Get-Content $Log | ForEach-Object { Write-Host $_ }
    }
    throw
}
finally {
    Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue
}
