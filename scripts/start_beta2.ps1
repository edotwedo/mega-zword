# Start the Beta 2 crew: one git worktree (own folder + branch) per AI, one Windows Terminal tab each,
# with the AI's handoff already typed in. Existing worktrees are reused.
# Stop an existing lane session before restarting it; do not run two writers in a lane.
#   ... -Only gemini -Resume   keep its latest conversation with corrected permissions
#   ... -Resume -PrintOnly     inspect commands without launching any AI
#   powershell -ExecutionPolicy Bypass -File scripts\start_beta2.ps1
#   ... -Only grok,codex      start just some of them
param(
  [ValidateSet('grok', 'codex', 'gemini', 'antigravity')]
  [string[]]$Only = @('grok', 'codex', 'gemini', 'antigravity'),
  [switch]$Resume,
  [switch]$PrintOnly
)

$ErrorActionPreference = 'Stop'
# Worktrees share main's environment. Never install into a lane worktree.
$checkout = Split-Path -Parent $PSScriptRoot
$common = git -C $checkout rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate the shared Mega Zword repository.' }
$repo = Split-Path -Parent $common
$python = Join-Path $repo '.venv\Scripts\python.exe'
$workshop = Join-Path $env:USERPROFILE 'Desktop\workshop'
$date = '2026-10-11'
$lanes = [ordered]@{
  grok        = @{ cmd = 'grok';  pre = @('--permission-mode', 'acceptEdits', '--allow', 'Read', '--allow', 'Glob', '--allow', 'Grep'); branch = "grok/beta2-$date" }
  codex       = @{ cmd = 'codex'; pre = @('--sandbox', 'workspace-write', '--ask-for-approval', 'on-request', '--add-dir', $repo, '--add-dir', $workshop); branch = "codex/beta2-$date" }
  gemini      = @{ cmd = 'agy';   pre = @('--mode', 'accept-edits', '--add-dir', $repo, '--add-dir', $workshop, '--model', 'gemini-3.1-pro-high'); branch = "gemini/beta2-$date" }
  antigravity = @{ cmd = 'agy';   pre = @('--mode', 'accept-edits', '--add-dir', $repo, '--add-dir', $workshop, '--model', 'claude-opus-4-6-thinking'); branch = "agy/beta2-$date" }
}

if (-not $PrintOnly) {
  git -C $repo fetch -q origin main
  if ($LASTEXITCODE -ne 0) { throw 'Fetch failed; no sessions started.' }
}
foreach ($name in $lanes.Keys) {
  if ($Only -notcontains $name) { continue }
  $lane = $lanes[$name]
  $dir = Join-Path (Split-Path -Parent $repo) "mz-b2-$name"
  if (-not (Test-Path $dir) -and -not $PrintOnly) {
    if ($Resume) { throw "Cannot resume missing worktree: $dir" }
    git -C $repo worktree add -q -b $lane.branch $dir origin/main
    if ($LASTEXITCODE -ne 0) { throw "Could not create worktree: $dir" }
  }
  $prompt = "You are on Phil's PC, in your own Mega Zword worktree ($dir, branch $($lane.branch)). " +
    "Read AGENTS.md, then docs/handoffs/$date-$name.md, and do its items in order. Pick a designation for " +
    "this session and use it in STATUS.md and Q. Check usage first with 'megazword usage'. Run tests with " +
    "'$python -m pytest -q' and '$python scripts\smoke.py' (both must pass, and tests never call a real AI). " +
    "Commit and push your branch often. Post one line in Q (edotwedo/workshop PR #33) when each item is done. " +
    "If another lane's work is needed, pull origin/main or ask in Q. " +
    "Phil has authorized routine project reads, edits, tests, commits, pushes and Q updates; do not ask him again for these. " +
    "Set PYTHONPATH to this worktree's src before testing, so the shared Python tests your branch."
  $arguments = @($lane.pre)
  if ($Resume) {
    # Stop the old session before using this; do not run two writers in a lane.
    $arguments += if ($name -eq 'codex') { @('resume', '--last') } else { @('--continue') }
  } else {
    if ($lane.cmd -eq 'agy') { $arguments += '-i' }
    $arguments += $prompt
  }
  # Encoded so the prompt's quotes and spaces survive wt and pwsh untouched (no ';' either: wt splits on it).
  $quoted = ($arguments | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ' '
  if ($PrintOnly) {
    Write-Output "$name | $dir | & $($lane.cmd) $quoted"
    continue
  }
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes("& $($lane.cmd) $quoted"))
  Start-Process wt -ArgumentList "-w 0 new-tab --title `"MZ $name`" --suppressApplicationTitle -d `"$dir`" pwsh -NoExit -EncodedCommand $encoded"
  Write-Host "started $name in $dir ($($lane.branch))"
}
Write-Host 'Claude stays the lead in your main window. Mistral is routed by Mega Zword (B14), not a terminal lane.'
