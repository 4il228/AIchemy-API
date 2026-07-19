from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.config import settings
from db import User, async_session, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.images_dir.mkdir(exist_ok=True)
    await init_db()
    async with async_session() as session:
        existing = await session.scalar(
            select(User).where(User.id == settings.seed_user_id)
        )
        if existing is None:
            session.add(
                User(id=settings.seed_user_id, nickname=settings.seed_user_nickname)
            )
            await session.commit()
    yield
