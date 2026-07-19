from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.schemas import CraftRequest, CraftResponse
from app.services import craft as craft_service

router = APIRouter(tags=["craft"])


@router.post("/craft", response_model=CraftResponse)
async def craft_elements(
    request: CraftRequest,
    current_user_id: int = Depends(get_current_user),
):
    return await craft_service.craft_elements(
        request.element_1,
        request.element_2,
        current_user_id,
    )
