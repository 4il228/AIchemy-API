import os
import re
import json
import hashlib
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

from db import Recipe, User, async_session, init_db

load_dotenv()

IMAGES_DIR = Path("generated_images")


@asynccontextmanager
async def lifespan(_: FastAPI):
    IMAGES_DIR.mkdir(exist_ok=True)
    await init_db()
    async with async_session() as session:
        existing = await session.scalar(select(User).where(User.id == 1))
        if existing is None:
            session.add(User(id=1, nickname="AIchemist"))
            await session.commit()
    yield


app = FastAPI(title="Алхимический Микросервис с Точной Визуализацией", lifespan=lifespan)

IMAGES_DIR.mkdir(exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

# Асинхронный клиент: не блокирует event loop, сервер держит параллельные запросы
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    timeout=45.0,
    max_retries=2,
)

class CraftRequest(BaseModel):
    element_1: str
    element_2: str

class CraftResponse(BaseModel):
    result: str
    description: str
    image_url: str
    creator_id: int
    creator_nickname: str

async def get_current_user() -> int:
    return 1

SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", "")

# Строгая схема ответа: провайдер сам гарантирует валидный JSON нужной структуры
RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "craft_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "description": {"type": "string"},
                "image_prompt_en": {"type": "string"},
            },
            "required": ["result", "description", "image_prompt_en"],
            "additionalProperties": False,
        },
    },
}

STYLE_MODIFIERS = os.environ.get("STYLE_MODIFIERS", "")

def extract_json(raw: str) -> dict:
    """Достаёт JSON-объект даже если модель обернула его в markdown или добавила текст."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise json.JSONDecodeError("No JSON object found", raw, 0)


# ГОСТ 7.79-2000 (система B) — для читаемых имён файлов без кириллицы в URL
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "shh",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    return "".join(_CYR_TO_LAT.get(ch, ch) for ch in text.lower())


def make_image_filename(result_name: str, element_a: str, element_b: str) -> str:
    """Слаг из транслита + короткий hash пары: без кириллицы в URL и без коллизий."""
    slug = re.sub(r"[^a-z0-9]+", "_", transliterate(result_name)).strip("_") or "element"
    pair_hash = hashlib.sha1(f"{element_a}+{element_b}".encode()).hexdigest()[:8]
    return f"{slug}_{pair_hash}.png"


async def download_image(image_prompt_en: str, filename: str) -> None:
    """Скачивает сгенерированную картинку с Pollinations на диск."""
    final_prompt = f"{image_prompt_en}, {STYLE_MODIFIERS}"
    encoded_prompt = urllib.parse.quote(final_prompt)
    url = (
        f"https://image.pollinations.ai/p/{encoded_prompt}"
        f"?width=1024&height=1024&model=flux&nologo=true"
    )
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        resp = await http.get(url)
        resp.raise_for_status()
    (IMAGES_DIR / filename).write_bytes(resp.content)


@app.post("/api/v1/craft", response_model=CraftResponse)
async def craft_elements(request: CraftRequest, current_user_id: int = Depends(get_current_user)):
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise HTTPException(status_code=500, detail="API key is missing")

    e1 = request.element_1.strip()
    e2 = request.element_2.strip()
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
            # Файл могли удалить с диска — тогда перескачиваем по сохранённому промпту
            image_file = Path(recipe.image_path)
            if not image_file.exists():
                try:
                    await download_image(recipe.image_prompt_en, image_file.name)
                except httpx.HTTPError as e:
                    raise HTTPException(status_code=502, detail=f"Ошибка загрузки изображения: {e}")
            return CraftResponse(
                result=recipe.result,
                description=recipe.description,
                image_url=f"/images/{image_file.name}",
                creator_id=recipe.creator_id,
                creator_nickname=recipe.creator.nickname if recipe.creator else "AIchemist",
            )

        user_prompt = f"Соедини эти два элемента: {e1} + {e2}"

        try:
            response = await client.chat.completions.create(
                model="tencent/hy3:free",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=1.2,
                # Лимит с запасом: это reasoning-модель, часть бюджета уходит на размышления
                max_tokens=2000,
                response_format=RESPONSE_SCHEMA,
                # Короткие размышления: заметно быстрее без потери качества ответа
                extra_body={"reasoning": {"effort": "low"}},
            )

            raw_content = response.choices[0].message.content
            result_json = extract_json(raw_content)
        except json.JSONDecodeError:
            raise HTTPException(status_code=502, detail="Модель вернула некорректный JSON")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ошибка API: {str(e)}")

        element_name = result_json.get("result", "Неизвестный элемент").strip()
        element_desc = result_json.get("description", "Трансмутация прошла нестабильно.").strip()
        image_prompt_en = result_json.get(
            "image_prompt_en",
            f"A magical hybrid of {e1} and {e2}"
        ).strip()

        filename = make_image_filename(element_name, element_a, element_b)
        try:
            await download_image(image_prompt_en, filename)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Ошибка загрузки изображения: {e}")

        recipe = Recipe(
            element_a=element_a,
            element_b=element_b,
            result=element_name,
            description=element_desc,
            image_path=str(IMAGES_DIR / filename),
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
            return CraftResponse(
                result=existing.result,
                description=existing.description,
                image_url=f"/images/{Path(existing.image_path).name}",
                creator_id=existing.creator_id,
                creator_nickname=existing.creator.nickname if existing.creator else "AIchemist",
            )

        return CraftResponse(
            result=element_name,
            description=element_desc,
            image_url=f"/images/{filename}",
            creator_id=current_user_id,
            creator_nickname="AIchemist",
        )

@app.get("/api/v1/recipes", response_model=list[CraftResponse])
async def list_recipes():
    async with async_session() as session:
        recipes = await session.scalars(
            select(Recipe).order_by(Recipe.id.desc())
        )
        return [
            CraftResponse(
                result=r.result,
                description=r.description,
                image_url=f"/images/{Path(r.image_path).name}",
                creator_id=r.creator_id,
                creator_nickname=r.creator.nickname if r.creator else "AIchemist",
            )
            for r in recipes
        ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
