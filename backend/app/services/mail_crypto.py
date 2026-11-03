"""Strict v3 AEAD for transport credentials and per-delivery content."""

import base64
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services.k3s_crypto import derive_encryption_subkey

_DOMAIN = b"afterglow.mail.v3"


def _aad(purpose: str) -> bytes:
    if purpose not in {"smtp", "imap"} and not re.fullmatch(
        r"delivery:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", purpose
    ):
        raise ValueError("mail_secret_purpose_invalid")
    return _DOMAIN + b"\0" + purpose.encode("ascii")


def encrypt_secret(plaintext: str, *, purpose: str) -> str:
    aad = _aad(purpose)
    try:
        nonce = os.urandom(12)
        sealed = AESGCM(derive_encryption_subkey(_DOMAIN)).encrypt(nonce, plaintext.encode("utf-8"), aad)
        return "v3:" + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")
    except Exception:
        raise ValueError("mail_secret_unavailable") from None


def decrypt_secret(ciphertext: str, *, purpose: str) -> str:
    aad = _aad(purpose)
    try:
        if not isinstance(ciphertext, str) or not ciphertext.startswith("v3:"):
            raise ValueError
        raw = base64.b64decode(ciphertext[3:], altchars=b"-_", validate=True)
        if len(raw) < 28:
            raise ValueError
        return AESGCM(derive_encryption_subkey(_DOMAIN)).decrypt(raw[:12], raw[12:], aad).decode("utf-8")
    except Exception:
        raise ValueError("mail_secret_unavailable") from None
