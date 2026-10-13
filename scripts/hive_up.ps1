# Seat the Hive floor: Mega Zword app + one Windows Terminal tab per main CLI.
# HTTP backends (Groq, etc.) have no window. Do not run two writers in one CLI.
# Each seat gets its own git worktree (%USERPROFILE%\mz-seats\<seat>), so seats never
# stash, checkout or edit each other's files in the shared folder.
#   powershell -ExecutionPolicy Bypass -File scripts\hive_up.ps1
#   ... -Skip grok          this Grok chat already counts as the Grok seat
#   ... -PrintOnly          show commands, launch nothing
param(
  [ValidateSet('claude', 'codex', 'grok', 'gemini')]
  [string[]]$Skip = @(),
  [switch]$PrintOnly,
  [switch]$NoApp,
  [switch]$NoIntroduce
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$mz = Join-Path $repo '.venv\Scripts\megazword.exe'
if (-not (Test-Path $mz)) { $mz = 'megazword' }
$workshop = Join-Path $env:USERPROFILE 'Desktop\workshop'
if (-not (Test-Path $workshop)) { $workshop = Join-Path $env:USERPROFILE 'workshop' }

$seats = Join-Path $env:USERPROFILE 'mz-seats'
$venvScripts = Join-Path $repo '.venv\Scripts'

function Get-SeatDir([string]$name) {
  $dir = Join-Path $seats $name
  if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $seats | Out-Null
    git -C $repo fetch -q origin main
    git -C $repo worktree add -q -B "seat/$name" $dir origin/main
    if ($LASTEXITCODE -ne 0) { throw "git worktree add failed for $name" }
  }
  return $dir
}

$prompt = @"
You are one Hive floor seat on Phil's PC (docs/FLOOR.md). This is your only window; use subagents for extra hands. Working copy: SEATDIR (your own git worktree; never edit, stash or checkout in $repo). Before work: git pull --rebase origin main. To publish: git push origin HEAD:main after tests pass. Check megazword usage before any job. Do not post a Q greeting. KEEP WORKING while Phil sleeps or watches Netflix. Do not stop at bye. Pull origin/main, take the next unclaimed file, push. Bulk -> megazword floor suggest bulk (Groq/HTTP). Edit -> Codex/Claude. Decide/review -> Claude/Grok. Gemini is out until 18 Oct.
"@

$lanes = [ordered]@{
  claude = @{ cmd = 'claude'; pre = @('--permission-mode', 'acceptEdits') }
  grok   = @{ cmd = 'grok';   pre = @('--permission-mode', 'acceptEdits', '--allow', 'Read', '--allow', 'Glob', '--allow', 'Grep') }
  codex  = @{ cmd = 'codex';  pre = @('--sandbox', 'workspace-write', '--ask-for-approval', 'on-request', '--add-dir', 'SEATDIR', '--add-dir', $workshop) }
}

if (-not $PrintOnly -and -not $NoIntroduce) {
  & $mz floor introduce
  if ($LASTEXITCODE -ne 0) { throw 'megazword floor introduce failed' }
  foreach ($kind in @('bulk','edit','decide','review')) {
    Write-Host -NoNewline "suggest $kind -> "
    & $mz floor suggest $kind
  }
}

if (-not $PrintOnly -and -not $NoApp) {
  Start-Process -FilePath $mz -WorkingDirectory $repo
  Write-Host 'opened Mega Zword'
}

foreach ($name in $lanes.Keys) {
  if ($Skip -contains $name) {
    Write-Host "skip $name (already seated)"
    continue
  }
  $lane = $lanes[$name]
  $dir = if ($PrintOnly) { Join-Path $seats $name } else { Get-SeatDir $name }
  $arguments = (@($lane.pre) + @($prompt)) | ForEach-Object { $_ -replace 'SEATDIR', $dir }
  $quoted = ($arguments | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ' '
  if ($PrintOnly) {
    Write-Output "$name | $dir | & $($lane.cmd) $quoted"
    continue
  }
  # The venv's megazword is an editable install of $repo; PYTHONPATH makes python and
  # tests in this tab use the seat's own src instead.
  $setup = "`$env:PYTHONPATH = '$dir\src'; `$env:PATH = '$venvScripts;' + `$env:PATH; "
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($setup + "& $($lane.cmd) $quoted"))
  Start-Process wt -ArgumentList "-w 0 new-tab --title `"Hive $name`" -d `"$dir`" pwsh -NoExit -EncodedCommand $encoded"
  Write-Host "started $name in $dir"
}

Write-Host 'Gemini has a chair when its week is back. Groq and the other HTTP seats have no tab.'
