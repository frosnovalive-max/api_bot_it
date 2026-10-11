"""Безопасность: хэширование паролей (bcrypt + поддержка легаси MD5), JWT, проверка прав."""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------- Хэширование паролей ----------

def hash_password(password: str) -> str:
    """Хэш пароля через bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Проверка пароля. Поддерживает и bcrypt, и легаси MD5 (32 hex-символа)."""
    if is_md5_hash(hashed):
        return hashlib.md5(plain.encode("utf-8")).hexdigest() == hashed.lower()
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        return False


def is_md5_hash(hashed: str) -> bool:
    """MD5-хэш — ровно 32 hex-символа (легаси из SQL-скрипта БД)."""
    if len(hashed) != 32:
        return False
    try:
        int(hashed, 16)
        return True
    except ValueError:
        return False


# ---------- JWT ----------

def create_access_token(subject: str | dict[str, Any], expires_minutes: int | None = None) -> str:
    """Создание JWT access-токена для веб-панели."""
    payload: dict[str, Any] = (
        dict(subject) if isinstance(subject, dict) else {"sub": subject}
    )
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_access_token_expire_minutes
    )
    payload.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Декодирование и валидация JWT. Бросает jwt.PyJWTError при ошибке."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# ---------- Проверка прав ----------

#: Роли, которым разрешены административные действия
ADMIN_ROLES = {"admin"}
#: Роли-сотрудники (видят внутренние сообщения, могут брать задачи)
STAFF_ROLES = {"admin", "support"}


def has_role(user_roles: set[str], allowed: set[str]) -> bool:
    """Пересечение ролей пользователя с набором допустимых ролей."""
    return bool(user_roles & allowed)


def is_admin(user_roles: set[str]) -> bool:
    return has_role(user_roles, ADMIN_ROLES)


def is_staff(user_roles: set[str]) -> bool:
    return has_role(user_roles, STAFF_ROLES)
