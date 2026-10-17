"""Phone hashing and Fernet encryption utilities (spec/02 §2.4, spec/03 §3.2).

Guarantees:
- Never store raw phone numbers in the teacher table.
- Teachers are identified by salted SHA-256 phone hash (spec/03).
- Encrypted E.164 phone numbers live exclusively in teacher_contact (spec/03).
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

from backend.app.config import settings

logger = logging.getLogger("abhyas.privacy.hashing")

_NON_DIGITS: Final = re.compile(r"\D")


def normalize_phone_number(raw_phone: str) -> str:
    """Normalizes a phone string into standard E.164 format.

    - Removes spaces, dashes, parentheses.
    - If Indian 10-digit number (e.g. '9876543210'), prepends '+91'.
    - If 12-digit without '+' starting with '91' (e.g. '919876543210'), prepends '+'.
    - Preserves existing E.164 '+' prefix.
    """
    cleaned = raw_phone.strip()
    if cleaned.startswith("+"):
        digits_only = _NON_DIGITS.sub("", cleaned[1:])
        return f"+{digits_only}"

    digits_only = _NON_DIGITS.sub("", cleaned)
    if len(digits_only) == 10 and digits_only[0] in "6789":
        return f"+91{digits_only}"
    if len(digits_only) == 12 and digits_only.startswith("91"):
        return f"+{digits_only}"
    return f"+{digits_only}" if digits_only else ""


def hash_phone_number(phone: str) -> str:
    """Computes salted SHA-256 phone hash for teacher identification (spec/03).

    Formula: sha256(PHONE_HASH_SALT + E.164 number)
    """
    normalized = normalize_phone_number(phone)
    salt = settings.PHONE_HASH_SALT
    data = (salt + normalized).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _get_fernet() -> Fernet:
    key_bytes = settings.PHONE_ENC_KEY.strip().encode("utf-8")
    return Fernet(key_bytes)


def encrypt_phone_number(phone: str) -> bytes:
    """Encrypts E.164 phone number using Fernet key (spec/03)."""
    normalized = normalize_phone_number(phone)
    f = _get_fernet()
    return f.encrypt(normalized.encode("utf-8"))


def decrypt_phone_number(phone_enc: bytes) -> str:
    """Decrypts encrypted phone bytes into normalized E.164 string."""
    f = _get_fernet()
    try:
        return f.decrypt(phone_enc).decode("utf-8")
    except InvalidToken as exc:
        logger.error("Failed to decrypt phone_enc: token invalid")
        raise ValueError("Invalid phone encryption token") from exc
