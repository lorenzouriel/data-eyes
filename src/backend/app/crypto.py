"""
Symmetric encryption for instance connection strings and notification configs.

Connection strings and notification configuration (webhooks, SMTP credentials,
and SMS provider tokens) are encrypted before being stored in the repository.
Encrypted with Fernet (AES-128-CBC + HMAC, from the `cryptography` package),
keyed by INSTANCE_SECRET_KEY.

Never log or return a decrypted connection string outside the one place
it's actually used to open a SQL Server connection (app/diagnostics.py, via
app/mssql_client.py) — every API response masks it instead
(see app/routers/instances.py).
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


class DecryptionError(Exception):
    """Raised when a stored secret can't be decrypted — usually
    means INSTANCE_SECRET_KEY changed since it was written."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(settings.INSTANCE_SECRET_KEY.encode())


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(bytes(ciphertext)).decode()
    except InvalidToken as e:
        raise DecryptionError(
            "Could not decrypt a stored secret — INSTANCE_SECRET_KEY may have changed"
        ) from e
