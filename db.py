import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
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
    # Ценность элемента ($V$): базы = 1, крафт = V_a + V_b
    value: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class InventoryItem(Base):
    """Экземпляр предмета в инвентаре пользователя.

    Стак по (user_id, recipe_id, is_bound): одинаковые предметы с одним
    статусом привязки суммируются в quantity; bound и unbound — раздельно.
    """

    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "recipe_id",
            "is_bound",
            name="uq_inventory_user_recipe_bound",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    is_bound: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    recipe = relationship("Recipe", lazy="joined")


# Колонки, добавленные в users после первого релиза. create_all не умеет
# ALTER TABLE, Alembic в проекте запрещён — поэтому добавляем идемпотентно.
_USERS_NEW_COLUMNS: dict[str, str] = {
    "password_hash": "VARCHAR(255)",
    "created_at": "DATETIME",
}

# То же для recipes: колонка value появилась вместе с инвентарём.
_RECIPES_NEW_COLUMNS: dict[str, str] = {
    "value": "INTEGER NOT NULL DEFAULT 1",
}

_INVENTORY_NEW_COLUMNS: dict[str, str] = {
    "quantity": "INTEGER NOT NULL DEFAULT 1",
}


async def _add_missing_columns(
    conn,
    table: str,
    columns: dict[str, str],
) -> None:
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    existing_columns = {row[1] for row in result.fetchall()}
    if not existing_columns:
        return
    for column, ddl_type in columns.items():
        if column not in existing_columns:
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
            )


async def _ensure_inventory_unique_index(conn) -> None:
    """UniqueConstraint на уже существующей таблице: через UNIQUE INDEX."""
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_user_recipe_bound "
            "ON inventory_items (user_id, recipe_id, is_bound)"
        )
    )


async def _backfill_recipe_values() -> None:
    """Пересчёт Recipe.value для старых записей: базы=1, крафт=V_a+V_b.

    Нужен после добавления колонки value (DEFAULT 1): без пересчёта
    стартовый набор не найдёт тиры 2–4 и 50–100.
    """
    from sqlalchemy import select

    async with async_session() as session:
        recipes = list(await session.scalars(select(Recipe).order_by(Recipe.id)))
        if not recipes:
            return

        values_by_name: dict[str, int] = {}
        for recipe in recipes:
            if recipe.element_a.startswith("_base_"):
                values_by_name[recipe.result.strip().lower()] = 1

        # Итеративная пропагация: родители могут идти после детей по id
        changed = True
        while changed:
            changed = False
            for recipe in recipes:
                if recipe.element_a.startswith("_base_"):
                    continue
                va = values_by_name.get(recipe.element_a)
                vb = values_by_name.get(recipe.element_b)
                if va is None or vb is None:
                    continue
                expected = va + vb
                key = recipe.result.strip().lower()
                if values_by_name.get(key) != expected:
                    values_by_name[key] = expected
                    changed = True

        dirty = False
        for recipe in recipes:
            if recipe.element_a.startswith("_base_"):
                expected = 1
            else:
                expected = values_by_name.get(recipe.result.strip().lower())
                if expected is None:
                    continue
            if recipe.value != expected:
                recipe.value = expected
                dirty = True
        if dirty:
            await session.commit()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Идемпотентная догонка схемы: добавляем только недостающие колонки,
        # существующие данные и связи не трогаются.
        await _add_missing_columns(conn, "users", _USERS_NEW_COLUMNS)
        await _add_missing_columns(conn, "recipes", _RECIPES_NEW_COLUMNS)
        await _add_missing_columns(conn, "inventory_items", _INVENTORY_NEW_COLUMNS)
        await _ensure_inventory_unique_index(conn)
    await _backfill_recipe_values()
