"""Exercise the POSIX SSH wrapper without contacting the real Windows node."""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name == "nt", reason="POSIX-side SSH wrapper")
@pytest.mark.parametrize("override", [False, True])
def test_windows_gate_quotes_arguments_and_preserves_ssh_failure(tmp_path, monkeypatch, override):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is unavailable")
    ssh = tmp_path / "ssh"
    ssh.write_text(
        f"#!{sys.executable}\nimport json, sys\n"
        "print(json.dumps(sys.argv[1:]))\nraise SystemExit(43)\n")
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.delenv("WINDOWS_GATE_HOST", raising=False)
    monkeypatch.delenv("WINDOWS_GATE_REPO", raising=False)
    monkeypatch.delenv("WINDOWS_GATE_EXPECTED_SHA", raising=False)
    host = "disci@192.168.1.171"
    repo = r"C:\Users\disci\mega-zword"
    if override:
        host = "test-user@windows-node"
        repo = r"C:\Users\Test User\workspace's & $(literal)"
        monkeypatch.setenv("WINDOWS_GATE_HOST", host)
        monkeypatch.setenv("WINDOWS_GATE_REPO", repo)
        monkeypatch.setenv("WINDOWS_GATE_EXPECTED_SHA", "a" * 40)
    wrapper = Path(__file__).resolve().parents[1] / "scripts" / "windows_gate.sh"
    args = ["tests/test_cli.py", "-k", "a 'quoted' name & $(literal); 中文"]
    proc = subprocess.run([bash, str(wrapper), "--install", "--", *args],
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == 43, proc.stdout + proc.stderr
    ssh_args = json.loads(proc.stdout)
    assert ssh_args[-2] == host
    command = ssh_args[-1]
    assert command.startswith("powershell.exe ")
    script = base64.b64decode(command.split()[-1]).decode("utf-16-le")
    encoded_options = re.search(r"FromBase64String\('([^']+)'\)", script).group(1)
    options = json.loads(base64.b64decode(encoded_options))
    expected = "a" * 40 if override else subprocess.check_output(
        ["git", "-C", str(wrapper.parent.parent), "rev-parse", "HEAD"], text=True).strip()
    assert options == {"repo": repo, "install": True, "expected_sha": expected, "args": args}


@pytest.mark.skipif(os.name == "nt", reason="POSIX-side SSH wrapper")
def test_windows_gate_rejects_malformed_expected_sha_before_ssh(tmp_path, monkeypatch):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is unavailable")
    monkeypatch.setenv("WINDOWS_GATE_EXPECTED_SHA", "HEAD; unintended command")
    wrapper = Path(__file__).resolve().parents[1] / "scripts" / "windows_gate.sh"
    proc = subprocess.run([bash, str(wrapper)], capture_output=True, text=True, timeout=10)
    assert proc.returncode != 0
    assert "expected SHA must be a full hexadecimal commit ID" in proc.stderr
