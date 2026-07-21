import os
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, UniqueConstraint, Index, ForeignKey, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# SQLite сейчас; для Postgres достаточно сменить DATABASE_URL в .env
# на postgresql+asyncpg://user:pass@host/db — модели и запросы не меняются.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./alchemy.db")

engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    # Argon2id-хеш пароля. Nullable: у seed-пользователя (id=1) пароля нет,
    # вход для пользователей с NULL-хешем запрещён на уровне сервиса авторизации.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
    )


class Session(Base):
    """Серверная сессия: в БД хранится только SHA-256 от токена.

    Сам токен (secrets.token_urlsafe) уходит клиенту в HttpOnly-cookie и
    нигде на сервере не сохраняется — кража БД не даёт живых сессий.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("element_a", "element_b", name="uq_recipe_pair"),
        Index("ix_recipe_pair", "element_a", "element_b"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    creator = relationship("User", lazy="joined")
    # Нормализованная пара: sorted(lower), поэтому "Огонь+Вода" == "вода+ОГОНЬ"
    element_a: Mapped[str] = mapped_column(String(200))
    element_b: Mapped[str] = mapped_column(String(200))
    result: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    image_path: Mapped[str] = mapped_column(String(500))
    image_prompt_en: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# Колонки, добавленные в users после первого релиза. create_all не умеет
# ALTER TABLE, Alembic в проекте запрещён — поэтому добавляем идемпотентно.
_USERS_NEW_COLUMNS: dict[str, str] = {
    "password_hash": "VARCHAR(255)",
    "created_at": "DATETIME",
}


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Идемпотентная догонка схемы users: добавляем только недостающие колонки,
        # существующие данные и связи не трогаются.
        result = await conn.execute(text("PRAGMA table_info(users)"))
        existing_columns = {row[1] for row in result.fetchall()}
        for column, ddl_type in _USERS_NEW_COLUMNS.items():
            if column not in existing_columns:
                await conn.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column} {ddl_type}")
                )
