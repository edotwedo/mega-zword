import json
import subprocess
from types import SimpleNamespace

import pytest

from megazword import cli, config, dashboard, phone


@pytest.fixture
def status(monkeypatch):
    monkeypatch.setattr(phone, "tailscale_path", lambda: "tailscale")

    def set_status(data, code=0):
        def run(cmd, **kwargs):
            assert cmd == ["tailscale", "status", "--json"]
            assert kwargs["timeout"] == 10
            return SimpleNamespace(returncode=code, stdout=json.dumps(data))
        monkeypatch.setattr(phone.subprocess, "run", run)
    return set_status


def test_connected_selects_private_ipv4(status):
    status({"BackendState": "Running", "TailscaleIPs": ["fd7a:115c:a1e0::1", "100.80.1.2"]})
    assert phone.address() == "100.80.1.2"


@pytest.mark.parametrize("data", [
    {}, [], {"BackendState": "Stopped"}, {"BackendState": "NeedsLogin"},
    {"BackendState": "Running", "TailscaleIPs": ["0.0.0.0", "192.168.1.2", "invalid"]},
    {"BackendState": "Running", "TailscaleIPs": "100.80.1.2"},
])
def test_disconnected_or_bad_address_never_launches(data, status, monkeypatch, capsys):
    status(data)
    monkeypatch.setattr(dashboard, "serve", lambda *a, **k: pytest.fail("must not launch"))
    assert cli.main(["dashboard", "--phone"], cfg=config.Config()) == 2
    assert "Tailscale" in capsys.readouterr().err


def test_missing_installation(monkeypatch):
    monkeypatch.setattr(phone, "tailscale_path", lambda: None)
    with pytest.raises(ValueError, match="not installed"):
        phone.address()


@pytest.mark.parametrize("error", [OSError("private detail"), subprocess.TimeoutExpired("tailscale", 10)])
def test_unreachable_service(monkeypatch, status, error):
    def fail(*a, **k):
        raise error
    monkeypatch.setattr(phone.subprocess, "run", fail)
    with pytest.raises(ValueError, match="Cannot reach Tailscale"):
        phone.address()


def test_command_failure_does_not_echo_private_output(status):
    status({"AuthURL": "private-login-url"}, code=1)
    with pytest.raises(ValueError, match="not ready") as error:
        phone.address()
    assert "private-login-url" not in str(error.value)


def test_unreadable_output(monkeypatch, status):
    monkeypatch.setattr(phone.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout="not-json"))
    with pytest.raises(ValueError, match="unreadable"):
        phone.address()


def test_phone_launch_preserves_project_port_and_remote_auth(status, monkeypatch):
    status({"BackendState": "Running", "TailscaleIPs": ["100.80.1.2"]})
    seen = []
    monkeypatch.setattr(dashboard, "serve", lambda *a, **k: seen.append((a, k)) or 0)
    assert cli.main(["dashboard", "--phone", "--port", "8766", "-p", "mega-zword"],
                    cfg=config.Config()) == 0
    assert seen == [((8766, "mega-zword", False, "100.80.1.2"), {"app_window": False})]


def test_host_and_phone_are_exclusive():
    with pytest.raises(SystemExit) as error:
        cli.main(["dashboard", "--phone", "--host", "127.0.0.1"])
    assert error.value.code == 2


def test_windows_install_found_without_path(monkeypatch, tmp_path):
    monkeypatch.setattr(phone.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    exe = tmp_path / "Tailscale" / "tailscale.exe"
    exe.parent.mkdir()
    exe.touch()
    assert phone.tailscale_path() == str(exe)
