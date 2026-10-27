"""Windows Credential Manager wrapper; drafted by Groq GPT-OSS 120B via Mega Zword.

Off Windows the same API is backed by a 0600 JSON file, $MEGAZWORD_HOME/secrets.json:
no new dependency, and it works headless under cron or systemd --user."""
import ctypes
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

if sys.platform == "win32":  # importing wintypes raises ValueError off Windows
    from ctypes import wintypes

__all__ = ["read", "write", "delete", "available", "VaultError"]

# Exceptions
class VaultError(RuntimeError):
    """Raised for any credential manager error other than a missing entry."""
    pass

# Helper to obtain the advapi32 DLL (or None on non‑Windows)
@lru_cache(maxsize=1)
def _api():
    if sys.platform != "win32":
        return None
    try:
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        _setup_prototypes(api)
        return api
    except (OSError, AttributeError):
        return None

# Constants and structures
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
MAX_BLOB_SIZE = 2560

# CREDENTIALW structure (partial – only fields we use)
if sys.platform == "win32":
    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.c_void_p),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

# Function prototypes
def _setup_prototypes(api):
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR,  # TargetName
        wintypes.DWORD,    # Type
        wintypes.DWORD,    # Flags
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),  # Credential
    ]
    api.CredReadW.restype = wintypes.BOOL

    api.CredWriteW.argtypes = [
        ctypes.POINTER(CREDENTIALW),  # Credential
        wintypes.DWORD,               # Flags
    ]
    api.CredWriteW.restype = wintypes.BOOL

    api.CredDeleteW.argtypes = [
        wintypes.LPCWSTR,  # TargetName
        wintypes.DWORD,    # Type
        wintypes.DWORD,    # Flags
    ]
    api.CredDeleteW.restype = wintypes.BOOL

    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None


# Name validation
_name_re = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")

def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _name_re.fullmatch(name):
        raise VaultError("Invalid credential name")

def _target_name(name: str) -> str:
    return f"megazword:{name}"

def _check_value(value) -> bytes:
    if not isinstance(value, str):
        raise VaultError("Value must be a string")
    try:
        blob_bytes = value.encode("utf-8")
    except UnicodeError:
        raise VaultError("Invalid credential value") from None
    if not blob_bytes or len(blob_bytes) > MAX_BLOB_SIZE:
        raise VaultError("Value exceeds maximum size")
    return blob_bytes


# POSIX file store
def _file_store() -> bool:
    return sys.platform != "win32"

def _store_path() -> Path:
    from . import config  # read at call time so tests' temporary HOME applies
    return Path(config.HOME) / "secrets.json"

def _load() -> dict:
    path = _store_path()
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return {}
    except OSError:
        raise VaultError("Secret file unreadable") from None
    if mode & 0o077:  # like ssh: refuse a key file other users can read
        raise VaultError(f"Secret file is open to other users; run: chmod 600 {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise VaultError("Secret file unreadable") from None
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise VaultError("Invalid secret file")
    return data

def _save(data: dict) -> None:
    path = _store_path()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.unlink(missing_ok=True)
        # O_EXCL with 0600: the file is never readable by others, even for a moment
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise VaultError("Secret file write failed") from None


# Public API
def available() -> bool:
    """Return True if the store can be used: always off Windows (the file is
    created on first write), else when the Windows Credential Manager loads."""
    return _file_store() or _api() is not None

def read(name: str):
    """Return the stored value for *name* or None if not present."""
    if not available():
        return None
    _validate_name(name)
    if _file_store():
        return _load().get(name)
    api = _api()
    target = _target_name(name)
    cred_ptr = ctypes.POINTER(CREDENTIALW)()
    if not api.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr)):
        err = ctypes.get_last_error()
        if err == ERROR_NOT_FOUND:
            return None
        raise VaultError("Credential read failed")
    cred = cred_ptr.contents
    size = cred.CredentialBlobSize
    try:
        if not 0 < size <= MAX_BLOB_SIZE or not cred.CredentialBlob:
            raise VaultError("Invalid credential data")
        try:
            return ctypes.string_at(cred.CredentialBlob, size).decode("utf-8")
        except UnicodeError:
            raise VaultError("Invalid credential data") from None
    finally:
        if cred.CredentialBlob and 0 < size <= MAX_BLOB_SIZE:
            ctypes.memset(cred.CredentialBlob, 0, size)
        api.CredFree(cred_ptr)


def write(name: str, value: str) -> None:
    """Store *value* under *name*."""
    if not available():
        raise VaultError("Credential manager not available")
    _validate_name(name)
    blob_bytes = _check_value(value)
    if _file_store():
        data = _load()
        data[name] = value
        _save(data)
        return
    api = _api()
    target = _target_name(name)
    # Allocate mutable buffer for the blob
    blob_buf = ctypes.create_string_buffer(blob_bytes, len(blob_bytes))
    cred = CREDENTIALW()
    cred.Flags = 0
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.CredentialBlobSize = len(blob_bytes)
    cred.CredentialBlob = ctypes.cast(blob_buf, ctypes.c_void_p)
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.AttributeCount = 0
    cred.Attributes = None
    cred.Comment = None
    cred.TargetAlias = None
    cred.UserName = None
    try:
        if not api.CredWriteW(ctypes.byref(cred), 0):
            raise VaultError("Credential write failed")
    finally:
        ctypes.memset(blob_buf, 0, len(blob_buf))


def delete(name: str) -> None:
    """Remove the credential for *name*."""
    if not available():
        raise VaultError("Credential manager not available")
    _validate_name(name)
    if _file_store():
        data = _load()
        if data.pop(name, None) is not None:
            _save(data)
        return
    api = _api()
    target = _target_name(name)
    if not api.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        err = ctypes.get_last_error()
        if err != ERROR_NOT_FOUND:
            raise VaultError("Credential delete failed")
    # Success (including not‑found) – nothing else to do.
