# Start the Beta 2 crew: one git worktree (own folder + branch) per AI, one Windows Terminal tab each,
# with the AI's handoff already typed in. Safe to run again: existing worktrees are reused.
#   powershell -ExecutionPolicy Bypass -File scripts\start_beta2.ps1
#   ... -Only grok,codex      start just some of them
param([string[]]$Only = @('grok', 'codex', 'gemini', 'antigravity'))

$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$date = '2026-10-11'
$lanes = [ordered]@{
  grok        = @{ cmd = 'grok';  pre = @();                                         branch = "grok/beta2-$date" }
  codex       = @{ cmd = 'codex'; pre = @();                                         branch = "codex/beta2-$date" }
  gemini      = @{ cmd = 'agy';   pre = @('--model', 'gemini-3.1-pro-high', '-i');   branch = "gemini/beta2-$date" }
  antigravity = @{ cmd = 'agy';   pre = @('--model', 'claude-opus-4-6-thinking', '-i'); branch = "agy/beta2-$date" }
}

git -C $repo fetch -q origin main
foreach ($name in $lanes.Keys) {
  if ($Only -notcontains $name) { continue }
  $lane = $lanes[$name]
  $dir = Join-Path (Split-Path -Parent $repo) "mz-b2-$name"
  if (-not (Test-Path $dir)) {
    git -C $repo worktree add -q -B $lane.branch $dir origin/main
  }
  $prompt = "You are on Phil's PC, in your own Mega Zword worktree ($dir, branch $($lane.branch)). " +
    "Read AGENTS.md, then docs/handoffs/$date-$name.md, and do its items in order. Pick a designation for " +
    "this session and use it in STATUS.md and Q. Check usage first with 'megazword usage'. Run tests with " +
    "'$python -m pytest -q' and '$python scripts\smoke.py' (both must pass, and tests never call a real AI). " +
    "Commit and push your branch often. Post one line in Q (edotwedo/workshop PR #33) when each item is done. " +
    "If another lane's work is needed, pull origin/main or ask in Q."
  # Encoded so the prompt's quotes and spaces survive wt and pwsh untouched (no ';' either: wt splits on it).
  $quoted = ($lane.pre + $prompt | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }) -join ' '
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes("& $($lane.cmd) $quoted"))
  Start-Process wt -ArgumentList "-w 0 new-tab --title `"MZ $name`" -d `"$dir`" pwsh -NoExit -EncodedCommand $encoded"
  Write-Host "started $name in $dir ($($lane.branch))"
}
Write-Host 'Claude stays the lead in your main window. Mistral joins once B14 plugs it in.'
