# End-to-end smoke test against fake AI CLIs. No paid calls. See smoke.py.
$py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py (Join-Path $PSScriptRoot "smoke.py")
exit $LASTEXITCODE
