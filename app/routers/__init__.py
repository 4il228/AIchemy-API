from fastapi import APIRouter

from app.routers import craft, recipes

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(craft.router)
api_router.include_router(recipes.router)
