import ctypes

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


@pytest.fixture
def api(monkeypatch):
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


def test_prototypes_use_pointer_to_pointer_and_free():
    class Fn:
        pass
    api = type("Prototypes", (), {name: Fn() for name in ("CredReadW", "CredWriteW", "CredDeleteW", "CredFree")})()
    vault._setup_prototypes(api)
    assert api.CredReadW.argtypes[-1] == ctypes.POINTER(ctypes.POINTER(vault.CREDENTIALW))
    assert api.CredWriteW.argtypes[0] == ctypes.POINTER(vault.CREDENTIALW)
    assert api.CredFree.argtypes == [ctypes.c_void_p]
    assert api.CredFree.restype is None
