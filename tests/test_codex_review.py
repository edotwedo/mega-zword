"""Fixes from Forge's review of Codex's code (F21). One test per bug."""

import io
import os
import subprocess
import sys
import time
import urllib.error
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from megazword import config, free_apis
from megazword.cli import main
from megazword.failures import classify
from megazword.limits import detect

REPO = Path(__file__).resolve().parent.parent


# --- free_apis: errors must be classifiable --------------------------------

def call_with(monkeypatch, exc):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(free_apis, "_use_curl", lambda *args: False)

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(free_apis.urllib.request, "urlopen", boom)
    b = free_apis.free_backends({"openrouter": "m", "groq": "m"})[1]
    r = b.run("hi")
    assert not r.ok and "test-key" not in r.error
    return r.error


def test_connection_failure_counts_as_network(monkeypatch):
    err = call_with(monkeypatch, urllib.error.URLError(OSError("getaddrinfo failed")))
    assert classify("groq", err).kind == "network"  # so a dead network stops the chain


def test_429_uses_retry_after_not_a_one_hour_guess(monkeypatch):
    exc = urllib.error.HTTPError("u", 429, "Too Many", {"Retry-After": "30"}, io.BytesIO(b"key"))
    err = call_with(monkeypatch, exc)
    hit = detect(err)
    assert hit and hit.exact and hit.until - datetime.now().astimezone() < timedelta(minutes=2)


def test_401_is_auth(monkeypatch):
    exc = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b""))
    assert classify("groq", call_with(monkeypatch, exc)).kind == "auth"


# --- config: BOM and broken files ------------------------------------------

def test_bom_config_loads_and_keeps_its_bom(tmp_path):
    p = tmp_path / "config.toml"
    p.write_bytes(b"\xef\xbb\xbf" + b'rater_model = "x"\n')
    assert config.load(p).rater_model == "x"
    config.set_flag("quality_check", True, p)
    data = p.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf") and data.count(b"\xef\xbb\xbf") == 1
    assert config.load(p).quality_check


def test_broken_config_gives_a_plain_message_not_a_traceback(capsys):
    config.HOME.mkdir(parents=True, exist_ok=True)
    (config.HOME / "config.toml").write_text('[route\neasy = ["grok"]\n')
    assert main(["backends"]) == 2
    err = capsys.readouterr().err
    assert "can't read" in err and "megazword doctor" in err and "Traceback" not in err


def test_default_backends_survive_a_broken_config():
    from megazword.backends import default_backends
    config.HOME.mkdir(parents=True, exist_ok=True)
    (config.HOME / "config.toml").write_text("not = [valid\n")
    assert "groq" in default_backends()


# --- doctor: version checks can't hang -------------------------------------

def test_run_quick_kills_the_tree_on_timeout():
    from megazword.backends import run_quick
    hang = ("import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)")
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_quick([sys.executable, "-c", hang], timeout=1)
    assert time.monotonic() - start < 20  # didn't wait for the grandchild's pipes


# --- install.ps1: PATH editing ---------------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="Windows registry")
def test_add_user_path_keeps_vars_duplicates_and_is_idempotent():
    key = rf"Software\MegaZwordTest-{uuid.uuid4().hex[:8]}"
    helper = REPO / "scripts" / "userpath.ps1"
    ps = rf"""
$ErrorActionPreference = 'Stop'
. '{helper}'
$k = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('{key}')
try {{
  $k.SetValue('Path', '%USERPROFILE%\bin;;C:\dup;C:\dup;', [Microsoft.Win32.RegistryValueKind]::ExpandString)
  Add-UserPath 'C:\New Dir' -KeyPath '{key}' -NoBroadcast
  Add-UserPath 'C:\New Dir\' -KeyPath '{key}' -NoBroadcast
  Add-UserPath ($env:USERPROFILE + '\bin') -KeyPath '{key}' -NoBroadcast
  $raw = $k.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
  "RAW=$raw"
  "KIND=" + $k.GetValueKind('Path')
  $k.DeleteValue('Path')
  Add-UserPath 'C:\Only' -KeyPath '{key}' -NoBroadcast
  "EMPTY=" + $k.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
}} finally {{
  $k.Close(); [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree('{key}')
}}
"""
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-Command", ps], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lines = dict(l.split("=", 1) for l in proc.stdout.splitlines() if "=" in l)
    assert lines["RAW"] == r"%USERPROFILE%\bin;C:\dup;C:\dup;C:\New Dir"
    assert lines["KIND"] == "ExpandString"
    assert lines["EMPTY"] == r"C:\Only"
