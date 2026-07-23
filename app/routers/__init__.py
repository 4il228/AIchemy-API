from fastapi import APIRouter

from app.routers import auth, craft, inventory, recipes

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(craft.router)
api_router.include_router(inventory.router)
api_router.include_router(recipes.router)
