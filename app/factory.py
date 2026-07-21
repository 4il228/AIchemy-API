from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.lifespan import lifespan
from app.routers import api_router
from app.scalar_docs import mount_scalar_docs


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_title,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    settings.images_dir.mkdir(exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(settings.images_dir)), name="images")
    app.include_router(api_router)
    mount_scalar_docs(app)
    return app
