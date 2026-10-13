# Seat the Hive floor: Mega Zword app + one Windows Terminal tab per main CLI.
# HTTP backends (Groq, etc.) have no window. Do not run two writers in one CLI.
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

$prompt = @"
You are one Hive floor seat on Phil's PC (docs/FLOOR.md). This is your only window; use subagents for extra hands. Working copy: $repo. Check megazword usage before any job. Do not post a Q greeting. Do not edit until Phil assigns work in the Mega Zword Hive tab. Conserve Claude/Codex/Grok: send bulk to Groq and other HTTP seats. Gemini is out until 18 Oct.
"@

$lanes = [ordered]@{
  claude = @{ cmd = 'claude'; pre = @('--permission-mode', 'acceptEdits') }
  grok   = @{ cmd = 'grok';   pre = @('--permission-mode', 'acceptEdits', '--allow', 'Read', '--allow', 'Glob', '--allow', 'Grep') }
  codex  = @{ cmd = 'codex';  pre = @('--sandbox', 'workspace-write', '--ask-for-approval', 'on-request', '--add-dir', $repo, '--add-dir', $workshop) }
}

if (-not $PrintOnly -and -not $NoIntroduce) {
  & $mz floor introduce
  if ($LASTEXITCODE -ne 0) { throw 'megazword floor introduce failed' }
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
  $arguments = @($lane.pre) + @($prompt)
  $quoted = ($arguments | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ' '
  if ($PrintOnly) {
    Write-Output "$name | $repo | & $($lane.cmd) $quoted"
    continue
  }
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes("& $($lane.cmd) $quoted"))
  Start-Process wt -ArgumentList "-w 0 new-tab --title `"Hive $name`" -d `"$repo`" pwsh -NoExit -EncodedCommand $encoded"
  Write-Host "started $name"
}

Write-Host 'Gemini has a chair when its week is back. Groq and the other HTTP seats have no tab.'
