# Respawn the floor: one tab per SEAT, under its own name, with its conversation back.
#
# hive_up.ps1 brings the floor up as one tab per CLI, with a generic lane name and no
# history. That is right for a cold start and wrong for a reboot: it loses both the
# designation and the context. This reads the roster through `megazword resume --json`
# and relaunches every seat as itself, resuming the most recent session it finds.
#
#   powershell -ExecutionPolicy Bypass -File scripts\hive_resume.ps1
#   ... -PrintOnly              show the commands, open nothing
#   ... -Only Cinder-21,Beacon-17   respawn just these seats
#   ... -Fresh                  start new conversations instead of resuming
param(
  [switch]$PrintOnly,
  [string[]]$Only = @(),
  [switch]$Fresh
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$mz = Join-Path $repo '.venv\Scripts\megazword.exe'
if (-not (Test-Path $mz)) { $mz = 'megazword' }
$venvScripts = Join-Path $repo '.venv\Scripts'

$extra = @()
if ($Fresh) { $extra += '--fresh' }
$plan = @(& $mz resume --json @extra | ConvertFrom-Json)

if (-not $plan.Count) { Write-Host 'resume: no seats found on the roster'; exit 1 }

$missing = 0
foreach ($seat in $plan) {
  if ($Only.Count -gt 0 -and ($Only -notcontains $seat.designation)) { continue }
  $dir = $seat.dir
  if (-not (Test-Path $dir)) { Write-Host "skip $($seat.designation): $dir is missing"; $missing++; continue }
  $flags = @($seat.args)
  $quoted = ($flags | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ' '
  if ($PrintOnly) {
    $what = if ($seat.session) { "resumes $($seat.session)" } else { 'starts fresh (no session found)' }
    Write-Output "$($seat.designation) | $dir | $what | & $($seat.cli) $quoted"
    continue
  }
  # Same environment the bring-up path sets, so the MCP server posts as this seat.
  $setup = "`$env:PYTHONPATH = '$dir\src'; `$env:PATH = '$venvScripts;' + `$env:PATH; `$env:MEGAZWORD_SEAT = '$($seat.designation)'; "
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($setup + "& $($seat.cli) $quoted"))
  Start-Process wt -ArgumentList "-w 0 new-tab --title `"$($seat.designation)`" --suppressApplicationTitle -d `"$dir`" pwsh -NoExit -EncodedCommand $encoded"
  Write-Host "respawned $($seat.designation) ($($seat.cli)) in $dir"
}
if ($missing) { Write-Host "$missing seat(s) had no directory and were skipped" }
