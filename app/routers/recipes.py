from fastapi import APIRouter

from app.schemas import CraftResponse
from app.services import craft as craft_service

router = APIRouter(tags=["recipes"])


@router.get("/recipes", response_model=list[CraftResponse])
async def list_recipes():
    return await craft_service.list_recipes()
