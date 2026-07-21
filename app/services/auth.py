"""Сервис авторизации: пароли (Argon2id) и серверные сессии.

Меры безопасности:
- Пароли хешируются Argon2id (рекомендация OWASP №1); параметры сложности
  заданы явно и соответствуют профилю RFC 9106 (low-memory).
- Сырой пароль не логируется и не сохраняется нигде, кроме локальной переменной.
- Токен сессии — криптографически стойкий secrets.token_urlsafe(32);
  в БД хранится только его SHA-256, поэтому дамп БД не даёт живых сессий.
- Защита от user enumeration / timing attack: при логине с неизвестным
  никнеймом всё равно выполняется верификация Argon2 над dummy-хешем,
  чтобы время ответа не выдавало существование пользователя.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from db import Session, User

# Явные параметры Argon2id: 3 итерации, 64 МиБ памяти, 4 потока (RFC 9106).
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # в КиБ => 64 МиБ
    parallelism=4,
)

# Dummy-хеш от случайного пароля: используется для выравнивания времени ответа,
# когда пользователь не найден (защита от timing-атак и перечисления пользователей).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    """Хеширует пароль Argon2id. Возвращает строку с параметрами и солью."""
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Проверяет пароль за постоянное (для наблюдателя) время.

    Если у пользователя нет хеша (seed-пользователь) или пользователь
    не существует — верифицируем dummy-хеш, чтобы время ответа совпадало.
    """
    target_hash = password_hash if password_hash else _DUMMY_HASH
    try:
        _hasher.verify(target_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    # Пароль совпал с dummy-хешем невозможен (случайный секрет), но на всякий
    # случай: если реального хеша не было, вход всегда запрещён.
    return password_hash is not None


def _token_hash(token: str) -> str:
    """SHA-256 от токена — единственное, что попадает в БД."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(db: AsyncSession, user_id: int) -> tuple[str, datetime]:
    """Создаёт сессию и возвращает (сырой токен для cookie, срок истечения)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.session_ttl_hours
    )
    db.add(Session(token_hash=_token_hash(token), user_id=user_id, expires_at=expires_at))
    await db.commit()
    return token, expires_at


async def resolve_session(db: AsyncSession, token: str) -> User | None:
    """Возвращает пользователя по токену сессии либо None (нет/истекла)."""
    session_row = await db.scalar(
        select(Session).where(Session.token_hash == _token_hash(token))
    )
    if session_row is None:
        return None
    expires_at = session_row.expires_at
    # SQLite возвращает naive datetime — приводим к UTC для сравнения
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        # Ленивая уборка: истёкшую сессию сразу удаляем
        await db.delete(session_row)
        await db.commit()
        return None
    return await db.scalar(select(User).where(User.id == session_row.user_id))


async def revoke_session(db: AsyncSession, token: str) -> None:
    """Инвалидация сессии на сервере (logout)."""
    await db.execute(delete(Session).where(Session.token_hash == _token_hash(token)))
    await db.commit()


async def register_user(db: AsyncSession, nickname: str, password: str) -> User | None:
    """Создаёт пользователя. Возвращает None, если никнейм занят.

    Гонка при одновременной регистрации одного никнейма обрабатывается
    через IntegrityError + rollback (unique-констрейнт на nickname).
    """
    user = User(nickname=nickname, password_hash=hash_password(password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None
    return user


async def authenticate(db: AsyncSession, nickname: str, password: str) -> User | None:
    """Проверяет логин/пароль. Единый None для всех причин отказа."""
    user = await db.scalar(select(User).where(User.nickname == nickname))
    # verify_password выполняет Argon2-верификацию всегда (dummy-хеш при
    # отсутствии пользователя) — время ответа не зависит от существования логина.
    if not verify_password(user.password_hash if user else None, password):
        return None
    return user
