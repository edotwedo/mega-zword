"""live_check.py: refuses without --yes-spend; works end to end on fake CLIs.

Never runs against real AIs: the fake claude/codex/grok from scripts/fake_cli
are first on PATH and HOME/USERPROFILE point at an empty folder.
"""

import subprocess
import sys
import tempfile

import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import smoke  # noqa: E402  (reuses its fake-CLI environment)

SCRIPT = REPO / "scripts" / "live_check.py"


def run(env, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=300)


def fake_env():
    tmp = Path(tempfile.mkdtemp(prefix="mz-live-test-"))
    env = smoke.make_env(tmp)
    # This check targets claude/codex/grok. The dedicated smoke check covers
    # agy separately: its Windows .cmd shim truncates multiline prompt args.
    env["PATH"] = smoke._without_real_agy(env["PATH"])
    return tmp, env


def test_refuses_without_yes_spend():
    tmp, env = fake_env()
    r = run(env)
    assert r.returncode == 2 and "Not run" in r.stdout
    assert not (tmp / "mz" / "log.jsonl").exists()  # nothing was sent


def test_full_check_on_fakes():
    tmp, env = fake_env()
    subprocess.run([sys.executable, "-m", "megazword.cli", "out", "grok", "--until", "1d"],
                   env=env, capture_output=True, timeout=60)
    r = run(env, "--yes-spend")
    out = r.stdout
    assert "Skipping: grok (marked out)" in out
    assert "claude   yes" in out and "codex    yes" in out and "grok   " not in out.split("AI ")[-1]
    assert "auto-pick chose" in out and r.returncode == 0, out + r.stderr
    log = (tmp / "mz" / "log.jsonl").read_text(encoding="utf-8")
    assert log.count('"forced": true') >= 2  # went through the normal, logged path


def test_smoke_refuses_missing_fakes_before_any_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "FAKES", tmp_path / "missing-fakes")
    with pytest.raises(RuntimeError, match="Smoke fake CLI missing or not executable"):
        smoke.make_env(tmp_path)


def test_smoke_drops_inherited_hive_identity_and_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("MEGAZWORD_SEAT", "LiveSeat")
    monkeypatch.setenv("HIVE_ROOM_URL", "https://example.invalid")
    monkeypatch.setenv("HIVE_ROOM_KEY_LIVESEAT", "test-only-placeholder")
    env = smoke.make_env(tmp_path)
    assert "MEGAZWORD_SEAT" not in env
    assert not any(name.startswith("HIVE_") for name in env)


def test_smoke_path_skips_inaccessible_mounts_and_real_agy(tmp_path, monkeypatch):
    safe = tmp_path / "safe"
    blocked = tmp_path / "untrusted"
    real_agy = tmp_path / "real-agy"
    for folder in (safe, blocked, real_agy):
        folder.mkdir()
    (real_agy / "agy.cmd").write_text("not a smoke CLI")
    original = Path.is_file

    def is_file(path):
        if path.parent == blocked:
            raise OSError(448, "untrusted mount point")
        return original(path)

    monkeypatch.setattr(Path, "is_file", is_file)
    path = smoke.os.pathsep.join((str(safe), str(blocked), str(real_agy), ""))
    assert smoke._without_real_agy(path) == str(safe)
