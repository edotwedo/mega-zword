# Save point: copy local Gitea main to the private GitHub copy of mega-zword.
# Phil runs this (or approves it); AIs don't push to GitHub on their own.
#
#   powershell -ExecutionPolicy Bypass -File C:\Users\mrmar\mz-seats\juniper-16\scripts\push-github.ps1
#
# Refuses unless GitHub main is behind local main (no force), and stops if the
# new commits look like they contain an API key or private key.

$repo = Split-Path -Parent $PSScriptRoot
function RunGit { & git.exe -C $repo @args 2>&1 | Out-String }

RunGit fetch -q origin | Out-Null
RunGit fetch -q github | Out-Null
$old = (RunGit rev-parse github/main).Trim()
$new = (RunGit rev-parse origin/main).Trim()
if ($old -eq $new) { Write-Host "GitHub is already up to date ($($new.Substring(0,7)))."; exit 0 }

& git -C $repo merge-base --is-ancestor github/main origin/main
if ($LASTEXITCODE -ne 0) { Write-Host "STOP: GitHub main has commits that local main doesn't. Not pushing."; exit 1 }

$added = (RunGit diff github/main origin/main) -split "`n" | Where-Object { $_ -like '+*' -and $_ -notlike '+++*' }
$keys = $added | Where-Object {
    $_ -match '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' -and
    $_ -notmatch "match|re\.compile|regex|pattern"
}
if ($keys) { Write-Host "STOP: possible secrets in the new commits:"; $keys | Select-Object -First 5; exit 1 }

$count = (RunGit rev-list --count "github/main..origin/main").Trim()
Write-Host "Pushing $count commits: $($old.Substring(0,7)) -> $($new.Substring(0,7))"
& git -C $repo push github origin/main:refs/heads/main
if ($LASTEXITCODE -eq 0) { Write-Host "Done. GitHub main is now $($new.Substring(0,7))." } else { exit 1 }
