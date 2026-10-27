import ctypes
import json
import os
import stat
import sys

import pytest

from megazword import credential_store as vault


class FakeAPI:
    """Exercise actual ctypes marshalling, never load advapi32."""
    def __init__(self):
        self.values = {}
        self.error = 1168
        self.freed = 0
        self.fail_write = False

    def CredWriteW(self, pointer, flags):
        cred = ctypes.cast(pointer, ctypes.POINTER(vault.CREDENTIALW)).contents
        assert flags == 0 and cred.Type == 1 and cred.Persist == 2
        assert cred.AttributeCount == 0
        self.write_pointer = cred.CredentialBlob
        self.write_size = cred.CredentialBlobSize
        # Keep the buffer alive so its cleanup can be checked after returning.
        self.write_buffer = pointer._obj._objects
        if self.fail_write:
            return False
        self.values[cred.TargetName] = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return True

    def CredReadW(self, target, kind, flags, out):
        assert kind == 1 and flags == 0
        if target not in self.values:
            return False
        value = self.values[target]
        self.blob = ctypes.create_string_buffer(value)
        self.cred = vault.CREDENTIALW()
        self.cred.CredentialBlob = ctypes.cast(self.blob, ctypes.c_void_p)
        self.cred.CredentialBlobSize = len(value)
        ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(vault.CREDENTIALW)))[0] = ctypes.pointer(self.cred)
        return True

    def CredFree(self, pointer):
        assert bytes(self.blob) == b"\0" * len(self.blob)
        self.freed += 1

    def CredDeleteW(self, target, kind, flags):
        assert kind == 1 and flags == 0
        if target not in self.values:
            return False
        del self.values[target]
        return True


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager")


@pytest.fixture
def api(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows Credential Manager")
    fake = FakeAPI()
    monkeypatch.setattr(vault, "_api", lambda: fake)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: fake.error, raising=False)
    return fake


def test_utf8_roundtrip_and_buffer_cleanup(api):
    value = "fake-密碼-☃\0tail"
    vault.write("GROQ_API_KEY", value)
    assert api.values["megazword:GROQ_API_KEY"] == value.encode("utf-8")
    assert ctypes.string_at(api.write_pointer, api.write_size) == b"\0" * api.write_size
    assert vault.read("GROQ_API_KEY") == value
    assert api.freed == 1
    vault.delete("GROQ_API_KEY")
    assert vault.read("GROQ_API_KEY") is None
    vault.delete("GROQ_API_KEY")


def test_failures_and_invalid_utf8_still_clean_up(api):
    api.values["megazword:GROQ_API_KEY"] = b"\xff-private"
    with pytest.raises(vault.VaultError, match="Invalid credential data"):
        vault.read("GROQ_API_KEY")
    assert api.freed == 1
    api.fail_write = True
    with pytest.raises(vault.VaultError, match="Credential write failed"):
        vault.write("GROQ_API_KEY", "fake-private")
    assert ctypes.string_at(api.write_pointer, api.write_size) == b"\0" * api.write_size
    api.error = 5
    with pytest.raises(vault.VaultError, match="Credential read failed"):
        vault.read("MISSING_KEY")
    with pytest.raises(vault.VaultError, match="Credential delete failed"):
        vault.delete("MISSING_KEY")


@pytest.mark.parametrize("name", ["BAD\n", "bad", "../private", "A" * 129, "", None])
def test_invalid_names_are_rejected(api, name):
    for fn, args in ((vault.read, (name,)), (vault.write, (name, "fake")), (vault.delete, (name,))):
        with pytest.raises(vault.VaultError):
            fn(*args)
    assert not api.values


@pytest.mark.parametrize("value", ["", "é" * 1281, "\ud800", None])
def test_invalid_values_are_rejected_without_echo(api, value):
    with pytest.raises(vault.VaultError) as exc:
        vault.write("GROQ_API_KEY", value)
    assert str(exc.value) in ("Value exceeds maximum size", "Invalid credential value", "Value must be a string")
    assert not api.values


def test_max_blob_size(api):
    vault.write("GROQ_API_KEY", "é" * 1280)
    assert len(api.values["megazword:GROQ_API_KEY"]) == 2560
    assert vault.read("GROQ_API_KEY") == "é" * 1280


@windows_only
def test_prototypes_use_pointer_to_pointer_and_free():
    class Fn:
        pass
    api = type("Prototypes", (), {name: Fn() for name in ("CredReadW", "CredWriteW", "CredDeleteW", "CredFree")})()
    vault._setup_prototypes(api)
    assert api.CredReadW.argtypes[-1] == ctypes.POINTER(ctypes.POINTER(vault.CREDENTIALW))
    assert api.CredWriteW.argtypes[0] == ctypes.POINTER(vault.CREDENTIALW)
    assert api.CredFree.argtypes == [ctypes.c_void_p]
    assert api.CredFree.restype is None


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX secret file")


@posix_only
def test_posix_file_roundtrip_is_0600_and_atomic():
    assert vault.available()
    assert vault.read("GROQ_API_KEY") is None
    vault.write("GROQ_API_KEY", "fake-é")
    vault.write("MISTRAL_API_KEY", "fake-m")
    path = vault._store_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert vault.read("GROQ_API_KEY") == "fake-é"
    assert json.loads(path.read_text(encoding="utf-8")) == {"GROQ_API_KEY": "fake-é", "MISTRAL_API_KEY": "fake-m"}
    assert [p.name for p in path.parent.iterdir()] == ["secrets.json"]  # no temp file left
    vault.delete("GROQ_API_KEY")
    vault.delete("GROQ_API_KEY")  # deleting a missing key is not an error
    assert vault.read("GROQ_API_KEY") is None
    assert vault.read("MISTRAL_API_KEY") == "fake-m"


@posix_only
def test_posix_file_open_to_others_is_refused_without_echo():
    vault.write("GROQ_API_KEY", "fake-secret")
    os.chmod(vault._store_path(), 0o644)
    for fn, args in ((vault.read, ("GROQ_API_KEY",)), (vault.write, ("GROQ_API_KEY", "x")),
                     (vault.delete, ("GROQ_API_KEY",))):
        with pytest.raises(vault.VaultError, match="chmod 600") as exc:
            fn(*args)
        assert "fake-secret" not in str(exc.value)


@posix_only
@pytest.mark.parametrize("body", ["not json", "[]", '{"GROQ_API_KEY": 5}'])
def test_posix_corrupt_file_raises(body):
    path = vault._store_path()
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(vault.VaultError):
        vault.read("GROQ_API_KEY")


@posix_only
@pytest.mark.parametrize("name", ["BAD\n", "bad", "../private", "A" * 129, "", None])
def test_posix_invalid_names_are_rejected(name):
    for fn, args in ((vault.read, (name,)), (vault.write, (name, "fake")), (vault.delete, (name,))):
        with pytest.raises(vault.VaultError):
            fn(*args)
    assert not vault._store_path().exists()


@posix_only
@pytest.mark.parametrize("value", ["", "é" * 1281, "\ud800", None])
def test_posix_invalid_values_are_rejected(value):
    with pytest.raises(vault.VaultError):
        vault.write("GROQ_API_KEY", value)
    assert not vault._store_path().exists()
