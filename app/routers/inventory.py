from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.schemas import InventoryItemResponse
from app.services import inventory as inventory_service

router = APIRouter(tags=["inventory"])


@router.get("/inventory", response_model=list[InventoryItemResponse])
async def get_inventory(
    current_user_id: int = Depends(get_current_user),
) -> list[InventoryItemResponse]:
    """Персональный инвентарь текущего пользователя (JOIN с Recipe)."""
    return await inventory_service.list_user_inventory(current_user_id)
