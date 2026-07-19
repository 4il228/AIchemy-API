from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.lifespan import lifespan
from app.routers import api_router


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_title, lifespan=lifespan)
    settings.images_dir.mkdir(exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(settings.images_dir)), name="images")
    app.include_router(api_router)
    return app
