import os
import pytest

from megazword.filelock import locked, write_atomic


def test_locked_acquires_and_releases(tmp_path):
    target = tmp_path / "sub" / "data.json"
    with locked(target) as got:
        assert got is True
        lock_file = tmp_path / "sub" / "data.json.lock"
        assert lock_file.is_file()

    with locked(target) as got_again:
        assert got_again is True


def test_locked_timeout_prints_warning_and_yields_false(tmp_path, capsys, monkeypatch):
    target = tmp_path / "data.json"
    monkeypatch.setattr("megazword.filelock._try_lock", lambda fd: False)
    monkeypatch.setattr("megazword.filelock.time.sleep", lambda _: None)

    with locked(target, timeout=0.0) as got:
        assert got is False

    err = capsys.readouterr().err
    assert f"couldn't lock {target.name}" in err
    assert "writing anyway" in err


def test_locked_handles_unlock_oserror(tmp_path, monkeypatch):
    target = tmp_path / "data.json"

    def fail_unlock(fd: int) -> None:
        raise OSError("unlock failed")

    monkeypatch.setattr("megazword.filelock._unlock", fail_unlock)
    with locked(target) as got:
        assert got is True


def test_write_atomic_writes_content_and_creates_parents(tmp_path):
    target = tmp_path / "nested" / "dir" / "file.txt"
    write_atomic(target, "first version\n")
    assert target.read_text(encoding="utf-8") == "first version\n"

    write_atomic(target, "second version\n")
    assert target.read_text(encoding="utf-8") == "second version\n"
    assert not list((tmp_path / "nested" / "dir").glob("*.tmp"))


def test_write_atomic_retries_on_transient_permission_error(tmp_path, monkeypatch):
    target = tmp_path / "atomic.txt"
    real_replace = os.replace
    attempts = 0

    def flaky_replace(src, dst):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("Access denied")
        real_replace(src, dst)

    monkeypatch.setattr("megazword.filelock.os.replace", flaky_replace)
    monkeypatch.setattr("megazword.filelock.time.sleep", lambda _: None)

    write_atomic(target, "success after retry")
    assert attempts == 3
    assert target.read_text(encoding="utf-8") == "success after retry"
    assert not list(tmp_path.glob("*.tmp"))


def test_write_atomic_cleans_up_tmp_on_persistent_permission_error(tmp_path, monkeypatch):
    target = tmp_path / "fail.txt"
    attempts = 0

    def fail_replace(src, dst):
        nonlocal attempts
        attempts += 1
        raise PermissionError("Access denied")

    monkeypatch.setattr("megazword.filelock.os.replace", fail_replace)
    monkeypatch.setattr("megazword.filelock.time.sleep", lambda _: None)

    with pytest.raises(PermissionError):
        write_atomic(target, "should fail")

    assert attempts == 100
    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))
