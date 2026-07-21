from pathlib import Path

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.schemas import CraftResponse
from app.services import images as image_service
from app.services import llm as llm_service
from app.utils import make_image_filename
from db import Recipe, User, async_session


def _to_response(recipe: Recipe, *, nickname_fallback: str | None = None) -> CraftResponse:
    nickname = (
        recipe.creator.nickname
        if recipe.creator
        else (nickname_fallback or settings.default_creator_nickname)
    )
    return CraftResponse(
        result=recipe.result,
        description=recipe.description,
        image_url=image_service.image_url_for(Path(recipe.image_path).name),
        creator_id=recipe.creator_id,
        creator_nickname=nickname,
    )


async def _ensure_image(recipe: Recipe) -> None:
    image_file = Path(recipe.image_path)
    if image_file.exists():
        return
    try:
        await image_service.download_image(recipe.image_prompt_en, image_file.name)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ошибка загрузки изображения: {e}")


async def craft_elements(
    element_1: str,
    element_2: str,
    current_user_id: int,
) -> CraftResponse:
    if not settings.openrouter_api_key:
        raise HTTPException(status_code=500, detail="API key is missing")

    e1 = element_1.strip()
    e2 = element_2.strip()
    if not e1 or not e2:
        raise HTTPException(status_code=422, detail="Оба элемента должны быть непустыми")

    # Симметричный ключ: "Огонь + Вода" и "Вода + Огонь" — один рецепт
    element_a, element_b = sorted((e1.lower(), e2.lower()))

    async with async_session() as session:
        recipe = await session.scalar(
            select(Recipe).where(
                Recipe.element_a == element_a, Recipe.element_b == element_b
            )
        )

        if recipe is not None:
            await _ensure_image(recipe)
            return _to_response(recipe)

        try:
            result_json = await llm_service.synthesize_elements(e1, e2)
        except llm_service.JSONDecodeError:
            raise HTTPException(status_code=502, detail="Модель вернула некорректный JSON")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ошибка API: {str(e)}")

        element_name, element_desc, image_prompt_en = llm_service.parse_synthesis(
            result_json, e1, e2
        )

        filename = make_image_filename(element_name, element_a, element_b)
        try:
            await image_service.download_image(image_prompt_en, filename)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Ошибка загрузки изображения: {e}")

        recipe = Recipe(
            element_a=element_a,
            element_b=element_b,
            result=element_name,
            description=element_desc,
            image_path=str(settings.images_dir / filename),
            image_prompt_en=image_prompt_en,
            creator_id=current_user_id,
        )
        session.add(recipe)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(
                select(Recipe).where(
                    Recipe.element_a == element_a, Recipe.element_b == element_b
                )
            )
            return _to_response(existing)

        # Создатель — реальный автор реакции: подставляем его никнейм
        creator = await session.scalar(select(User).where(User.id == current_user_id))
        return CraftResponse(
            result=element_name,
            description=element_desc,
            image_url=image_service.image_url_for(filename),
            creator_id=current_user_id,
            creator_nickname=(
                creator.nickname if creator else settings.default_creator_nickname
            ),
        )


async def list_recipes() -> list[CraftResponse]:
    async with async_session() as session:
        recipes = await session.scalars(select(Recipe).order_by(Recipe.id.desc()))
        return [_to_response(r) for r in recipes]
