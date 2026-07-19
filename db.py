import os
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, UniqueConstraint, Index, ForeignKey
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


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
