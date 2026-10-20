"""Windows Credential Manager wrapper; drafted by Groq GPT-OSS 120B via Mega Zword."""
import ctypes
from ctypes import wintypes
import re
import sys
from functools import lru_cache

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

# Public API
def available() -> bool:
    """Return True if the Windows Credential Manager can be used."""
    return _api() is not None

def read(name: str):
    """Return the stored value for *name* or None if not present."""
    if not available():
        return None
    _validate_name(name)
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
    if not isinstance(value, str):
        raise VaultError("Value must be a string")
    api = _api()
    target = _target_name(name)
    try:
        blob_bytes = value.encode("utf-8")
    except UnicodeError:
        raise VaultError("Invalid credential value") from None
    if not blob_bytes or len(blob_bytes) > MAX_BLOB_SIZE:
        raise VaultError("Value exceeds maximum size")
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
    api = _api()
    target = _target_name(name)
    if not api.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        err = ctypes.get_last_error()
        if err != ERROR_NOT_FOUND:
            raise VaultError("Credential delete failed")
    # Success (including not‑found) – nothing else to do.
