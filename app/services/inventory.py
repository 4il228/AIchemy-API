"""Инвентарь пользователя: стартовый набор, консьюм, выдача, список."""

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import InventoryItemResponse
from app.services import images as image_service
from db import InventoryItem, Recipe, async_session


async def get_stacks_by_name(
    session: AsyncSession,
    user_id: int,
    element_name: str,
) -> list[InventoryItem]:
    """Стеки инвентаря по имени элемента (Recipe.result), bound первыми.

    Сравнение имени в Python: SQLite lower()/LIKE некорректно обрабатывают
    кириллицу, а инвентарь пользователя невелик.
    """
    name = element_name.strip().lower()
    stmt = (
        select(InventoryItem)
        .join(Recipe, InventoryItem.recipe_id == Recipe.id)
        .where(
            InventoryItem.user_id == user_id,
            InventoryItem.quantity >= 1,
        )
        .order_by(InventoryItem.is_bound.desc(), InventoryItem.id)
    )
    items = list(await session.scalars(stmt))
    return [item for item in items if item.recipe.result.strip().lower() == name]


def total_quantity(stacks: list[InventoryItem]) -> int:
    return sum(item.quantity for item in stacks)


def peek_values(stacks: list[InventoryItem], count: int) -> list[int]:
    """Ценности единиц в порядке списания (bound → unbound), без мутации."""
    values: list[int] = []
    for item in stacks:
        for _ in range(item.quantity):
            if len(values) >= count:
                return values
            values.append(item.recipe.value)
    return values


async def consume_stacks(
    session: AsyncSession,
    stacks: list[InventoryItem],
    amount: int,
) -> None:
    """Списывает amount единиц; при quantity=0 удаляет строку."""
    remaining = amount
    for item in stacks:
        if remaining <= 0:
            break
        take = min(item.quantity, remaining)
        item.quantity -= take
        remaining -= take
        if item.quantity <= 0:
            await session.delete(item)
    if remaining > 0:
        raise HTTPException(
            status_code=400,
            detail="Недостаточно элементов в инвентаре",
        )


async def add_unbound_result(
    session: AsyncSession,
    user_id: int,
    recipe_id: int,
) -> None:
    """Добавляет результат крафта с is_bound=False (или +1 к стеку).

    Гонка параллельных запросов обрабатывается nested savepoint + IntegrityError.
    """
    existing = await session.scalar(
        select(InventoryItem).where(
            InventoryItem.user_id == user_id,
            InventoryItem.recipe_id == recipe_id,
            InventoryItem.is_bound.is_(False),
        )
    )
    if existing is not None:
        existing.quantity += 1
        return

    try:
        async with session.begin_nested():
            session.add(
                InventoryItem(
                    user_id=user_id,
                    recipe_id=recipe_id,
                    quantity=1,
                    is_bound=False,
                )
            )
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(InventoryItem).where(
                InventoryItem.user_id == user_id,
                InventoryItem.recipe_id == recipe_id,
                InventoryItem.is_bound.is_(False),
            )
        )
        if existing is None:
            raise
        existing.quantity += 1


async def _take_recipes(
    session: AsyncSession,
    *,
    condition,
    limit: int,
    exclude_ids: set[int],
) -> list[Recipe]:
    if limit <= 0:
        return []
    stmt = select(Recipe).where(condition).order_by(func.random())
    if exclude_ids:
        stmt = stmt.where(Recipe.id.notin_(exclude_ids))
    return list(await session.scalars(stmt.limit(limit)))


async def pick_starter_recipes(session: AsyncSession) -> list[Recipe]:
    """4 элемента: 2×V=1, 1×V∈[2,4], 1×V∈[50,100]; fallback — базовые V=1."""
    selected: list[Recipe] = []
    selected_ids: set[int] = set()

    async def take(condition, n: int) -> None:
        rows = await _take_recipes(
            session, condition=condition, limit=n, exclude_ids=selected_ids
        )
        for recipe in rows:
            selected.append(recipe)
            selected_ids.add(recipe.id)

    await take(Recipe.value == 1, 2)
    await take(Recipe.value.between(2, 4), 1)
    await take(Recipe.value.between(50, 100), 1)

    shortage = 4 - len(selected)
    if shortage > 0:
        await take(Recipe.value == 1, shortage)

    return selected


async def grant_starter_inventory(session: AsyncSession, user_id: int) -> None:
    """Выдаёт стартовый набор новому пользователю (все is_bound=True)."""
    recipes = await pick_starter_recipes(session)
    for recipe in recipes:
        session.add(
            InventoryItem(
                user_id=user_id,
                recipe_id=recipe.id,
                quantity=1,
                is_bound=True,
            )
        )
    await session.commit()


async def list_user_inventory(user_id: int) -> list[InventoryItemResponse]:
    """JOIN InventoryItem + Recipe → список предметов пользователя."""
    async with async_session() as session:
        stmt = (
            select(InventoryItem, Recipe)
            .join(Recipe, InventoryItem.recipe_id == Recipe.id)
            .where(InventoryItem.user_id == user_id)
            .order_by(InventoryItem.id)
        )
        rows = (await session.execute(stmt)).all()
        return [
            InventoryItemResponse(
                inventory_item_id=item.id,
                recipe_id=recipe.id,
                name=recipe.result,
                description=recipe.description,
                image_url=image_service.image_url_for(Path(recipe.image_path).name),
                value=recipe.value,
                quantity=item.quantity,
                is_bound=item.is_bound,
            )
            for item, recipe in rows
        ]
