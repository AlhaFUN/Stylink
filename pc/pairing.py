"""Per-install pairing credentials and challenge-response helpers."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import os
import secrets
from ctypes import wintypes


def new_session_token() -> str:
    """Create a high-entropy key unique to one VirtualDT pairing."""
    return secrets.token_urlsafe(32)


def make_auth_proof(token: str, nonce_hex: str) -> str:
    """Prove knowledge of a paired key without sending the key itself."""
    if not token:
        raise ValueError("A paired session key is required.")
    try:
        nonce = bytes.fromhex(nonce_hex)
    except ValueError as error:
        raise ValueError("The phone sent an invalid authentication challenge.") from error
    if len(nonce) != 32:
        raise ValueError("The phone sent an invalid authentication challenge.")
    return hmac.new(token.encode("utf-8"), nonce, hashlib.sha256).hexdigest()


def verify_auth_proof(token: str, nonce_hex: str, proof: str) -> bool:
    try:
        expected = make_auth_proof(token, nonce_hex)
    except ValueError:
        return False
    return hmac.compare_digest(expected, proof)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise OSError("Windows user encryption is only available on Windows.")

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    blob_pointer = ctypes.POINTER(_DataBlob)
    crypt32.CryptProtectData.argtypes = [
        blob_pointer, wintypes.LPCWSTR, blob_pointer, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, blob_pointer,
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        blob_pointer, ctypes.POINTER(wintypes.LPWSTR), blob_pointer,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_pointer,
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    source = ctypes.create_string_buffer(data)
    source_blob = _DataBlob(
        len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte))
    )
    result_blob = _DataBlob()
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(source_blob), "VirtualDT session key", None, None,
            None, 0x1, ctypes.byref(result_blob),
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source_blob), None, None, None, None, 0x1,
            ctypes.byref(result_blob),
        )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result_blob.pbData, result_blob.cbData)
    finally:
        kernel32.LocalFree(result_blob.pbData)


def protect_session_token(token: str) -> str:
    """Protect a key for the current Windows user before saving it."""
    if os.name == "nt":
        encrypted = _dpapi(token.encode("utf-8"), protect=True)
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    # This development-only encoding keeps protocol tests portable. The built
    # Windows companion always uses DPAPI above.
    return "plain:" + base64.b64encode(token.encode("utf-8")).decode("ascii")


def unprotect_session_token(value: str) -> str | None:
    """Load a Windows-user-protected key; return None for missing/bad data."""
    try:
        prefix, encoded = value.split(":", 1)
        encrypted = base64.b64decode(encoded, validate=True)
        if prefix == "dpapi" and os.name == "nt":
            return _dpapi(encrypted, protect=False).decode("utf-8")
        if prefix == "plain" and os.name != "nt":
            return encrypted.decode("utf-8")
    except (ValueError, OSError, UnicodeDecodeError):
        return None
    return None
