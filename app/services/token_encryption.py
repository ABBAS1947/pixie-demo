"""Token encryption for storing OAuth tokens at rest.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Tokens are encrypted before DB write and decrypted on read.
"""

from cryptography.fernet import Fernet

from app.core.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.token_encryption_key
        if not key:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY must be set in .env for Google token storage. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string for storage."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a stored token string."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
