"""Шифрование секретов at-rest (Fernet).

Используется для SMTP-пароля в таблице `smtp_settings`. Ключ берётся из
`SETTINGS_ENC_KEY` (env), а при его отсутствии детерминированно выводится из
`SECRET_KEY` — так dev-окружение работает без отдельного ключа, но в проде
`SETTINGS_ENC_KEY` обязателен (см. docs/ADMIN_FEATURE.md §12).
"""
import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    key = settings.SETTINGS_ENC_KEY
    if not key:
        # Производный ключ от SECRET_KEY: sha256 → 32 байта → urlsafe base64 (валидный Fernet-ключ).
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        ).decode()
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
