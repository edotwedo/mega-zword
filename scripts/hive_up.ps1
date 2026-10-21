# Seat the Hive floor: Mega Zword app + one Windows Terminal tab per main CLI.
# HTTP backends (Groq, etc.) have no window. Do not run two writers in one CLI.
# Each seat gets its own git worktree (%USERPROFILE%\mz-seats\<seat>), so seats never
# stash, checkout or edit each other's files in the shared folder.
#   powershell -ExecutionPolicy Bypass -File scripts\hive_up.ps1
#   ... -Skip grok          this Grok chat already counts as the Grok seat
#   ... -PrintOnly          show commands, launch nothing
#   ... -Seat cmdc=Cinder-21   name that lane's seat (worktree, MEGAZWORD_SEAT, tab)
param(
  [ValidateSet('claude', 'codex', 'grok', 'gemini', 'cmdc')]
  [string[]]$Skip = @(),
  [string[]]$Seat = @(),
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
You are one Hive floor seat on Phil's PC. This is your only window; use subagents for extra hands. Working copy: SEATDIR; never edit, stash or checkout in $repo. Keep MEGAZWORD_SEAT as your designation. hive_read / hive_say / hive_wait is the live room. Before work: git pull --rebase origin main, then megazword startup once for bounded usage/floor readings. Reuse readings already supplied in this turn; no repeat onboarding, full-suite run or browser for startup. Read only the top 30 STATUS lines and task-relevant SPEC/DECISIONS sections (AGENTS.md). Work on Phil's task or the verified conductor's assignment; keep working on authorized tasks while Phil is away. If no assignment exists, report once and wait in Hive. Publish tested changes through the conductor to local origin. No Q greeting.
"@

$lanes = [ordered]@{
  claude = @{ cmd = 'claude'; pre = @('--permission-mode', 'acceptEdits') }
  grok   = @{ cmd = 'grok';   pre = @('--permission-mode', 'acceptEdits', '--allow', 'Read', '--allow', 'Glob', '--allow', 'Grep') }
  codex  = @{ cmd = 'codex';  pre = @('--sandbox', 'workspace-write', '--ask-for-approval', 'on-request', '--add-dir', 'SEATDIR', '--add-dir', $workshop) }
  cmdc   = @{ cmd = 'cmdc';   pre = @() }
  # The Gemini seat's binary is agy (Antigravity); without this lane the cold start could
  # never seat Forge-22 at all (Harbor022's audit, 2026-10-21).
  gemini = @{ cmd = 'agy';    pre = @() }
}

# A lane is normally its own seat name (claude, codex, ...), but the roster uses Word-NN
# designations. `-Seat claude=Juniper-16` names that lane's worktree, MEGAZWORD_SEAT and
# tab after the designation. Without this a Command Code tab is born with no seat at all
# and the bot has to pass `author:` by hand forever (Phil, 2026-10-19).
$seatNames = @{}
foreach ($pair in $Seat) {
  $parts = $pair.Split('=', 2)
  if ($parts.Count -eq 2 -and $parts[1].Trim()) { $seatNames[$parts[0].Trim()] = $parts[1].Trim() }
}

if (-not $PrintOnly -and -not $NoIntroduce) {
  & $mz startup
}

if (-not $PrintOnly -and -not $NoApp) {
  Start-Process -FilePath $mz -WorkingDirectory $repo
  Write-Host 'opened Mega Zword'
}

$launched = @()
foreach ($name in $lanes.Keys) {
  if ($Skip -contains $name) {
    Write-Host "skip $name (already seated)"
    continue
  }
  $lane = $lanes[$name]
  $seatName = if ($seatNames.ContainsKey($name)) { $seatNames[$name] } else { $name }
  # Designations are mixed case (Cinder-21) but worktrees and branches are lowercase.
  $seatDir = $seatName.ToLower()
  $dir = if ($PrintOnly) { Join-Path $seats $seatDir } else { Get-SeatDir $seatDir }
  $arguments = (@($lane.pre) + @($prompt)) | ForEach-Object { $_ -replace 'SEATDIR', $dir }
  $quoted = ($arguments | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ' '
  if ($PrintOnly) {
    Write-Output "$name -> seat $seatName | $dir | & $($lane.cmd) $quoted"
    continue
  }
  # The venv's megazword is an editable install of $repo; PYTHONPATH makes python and
  # tests in this tab use the seat's own src instead.
  $setup = "`$env:PYTHONPATH = '$dir\src'; `$env:PATH = '$venvScripts;' + `$env:PATH; `$env:MEGAZWORD_SEAT = '$seatName'; "
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($setup + "& $($lane.cmd) $quoted"))
  Start-Process wt -ArgumentList "-w 0 new-tab --title `"$seatName`" --suppressApplicationTitle -d `"$dir`" pwsh -NoExit -EncodedCommand $encoded"
  Write-Host "started $name as $seatName in $dir"
  $launched += [pscustomobject]@{ designation = $seatName; cli = $lane.cmd; dir = $dir }
}

# Record what we launched, so a later respawn knows this seat's directory instead of
# guessing at it. Without this, two seats can fall out of one directory (2026-10-20).
if ($launched.Count) {
  $launched | ConvertTo-Json -Depth 3 | & $mz resume --record-stdin | Out-Null
  Write-Host "recorded $($launched.Count) seat(s) for respawn"
}

Write-Host 'Gemini has a chair when its week is back. Groq and the other HTTP seats have no tab.'
