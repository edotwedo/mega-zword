#!/usr/bin/env bash
# Run the Windows suite over passwordless SSH; preserve pytest's exit status.
# Usage: scripts/windows_gate.sh [--install] [-- PYTEST_ARGS...]
# WINDOWS_GATE_HOST / WINDOWS_GATE_REPO override the dedicated node defaults.
# WINDOWS_GATE_EXPECTED_SHA defaults to this checkout's HEAD; stale/dirty nodes fail.
set -euo pipefail

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  sed -n '2,5p' "$0"
  exit 0
fi

install=0
if [[ ${1:-} == --install ]]; then
  install=1
  shift
fi
[[ ${1:-} != -- ]] || shift

host=${WINDOWS_GATE_HOST:-disci@192.168.1.171}
repo='C:\Users\disci\mega-zword'
repo=${WINDOWS_GATE_REPO:-$repo}
source_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
expected_sha=${WINDOWS_GATE_EXPECTED_SHA:-$(git -C "$source_root" rev-parse --verify HEAD)}

# Encode data and PowerShell separately: paths and pytest arguments never become
# cmd.exe syntax, even when they contain spaces, quotes, or shell characters.
encoded=$(python3 - "$repo" "$install" "$expected_sha" "$@" <<'PY'
import base64
import json
import re
import sys

expected = sys.argv[3].lower()
if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected):
    sys.exit("WINDOWS GATE: FAIL (expected SHA must be a full hexadecimal commit ID)")
options = base64.b64encode(json.dumps({
    "repo": sys.argv[1], "install": sys.argv[2] == "1", "expected_sha": expected,
    "args": sys.argv[4:]
}).encode()).decode()
script = r'''
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$env:PYTHONIOENCODING = 'utf-8'
$cfg = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__OPTIONS__')) | ConvertFrom-Json
function Assert-GateRevision {
    $actual = & git rev-parse --verify HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot determine Windows gate commit' }
    $actual = "$actual".Trim()
    if ($actual -ne $cfg.expected_sha) {
        throw "Windows gate commit mismatch: expected $($cfg.expected_sha), node has $actual"
    }
    $dirty = @(& git status --porcelain)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot verify Windows gate worktree' }
    if ($dirty.Count -ne 0) {
        throw "Windows gate requires a clean worktree and index: $($dirty -join '; ')"
    }
    [Console]::WriteLine("Windows gate revision: $actual (expected; worktree clean)")
}
try {
    Set-Location -LiteralPath $cfg.repo
    Assert-GateRevision
    $python = Join-Path $cfg.repo '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Missing Windows virtualenv interpreter: $python"
    }
    $fullPath = $env:Path
    $node = Join-Path $env:ProgramFiles 'nodejs'
    $env:Path = "$node;$fullPath"
    if ($cfg.install) {
        try {
            # pip probes PATH and fails on the OpenAI Codex untrusted mount
            # (WinError 448). Use absolute Python and a minimal PATH for pip only.
            $env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
            & $python -m pip install --disable-pip-version-check -e '.[dev]' 'psutil>=7' 'Pillow>=10.1' 'pywinpty>=3'
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } finally {
            $env:Path = "$node;$fullPath"
        }
    }
    [Console]::WriteLine("Windows gate node: $env:COMPUTERNAME; repo: $($cfg.repo)")
    & $python -c 'import sys; print(sys.version)'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $testArgs = @('-m', 'pytest', '-q') + @($cfg.args)
    & $python @testArgs
    $result = $LASTEXITCODE
    Assert-GateRevision
    if ($result -eq 0) { [Console]::WriteLine('WINDOWS GATE: PASS') }
    else { [Console]::WriteLine("WINDOWS GATE: FAIL (pytest exit $result)") }
    exit $result
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    [Console]::WriteLine('WINDOWS GATE: FAIL (setup)')
    exit 1
}
'''.replace('__OPTIONS__', options)
print(base64.b64encode(script.encode('utf-16-le')).decode())
PY
)

exec ssh -o BatchMode=yes -o ConnectTimeout=10 -- "$host" \
  "powershell.exe -NoProfile -NonInteractive -OutputFormat Text -ExecutionPolicy Bypass -EncodedCommand $encoded"
