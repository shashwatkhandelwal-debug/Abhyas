"""Privacy, retention, and data purge utilities (spec/03 §3.3, spec/08 §8.1)."""

from backend.app.privacy.hashing import (
    decrypt_phone_number,
    encrypt_phone_number,
    hash_phone_number,
    normalize_phone_number,
)
from backend.app.privacy.purge import purge_teacher_data

__all__ = [
    "purge_teacher_data",
    "decrypt_phone_number",
    "encrypt_phone_number",
    "hash_phone_number",
    "normalize_phone_number",
]
