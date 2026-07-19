import json

from openai import AsyncOpenAI

from app.config import settings
from app.utils import extract_json

# Асинхронный клиент: не блокирует event loop, сервер держит параллельные запросы
client = AsyncOpenAI(
    base_url=settings.openrouter_base_url,
    api_key=settings.openrouter_api_key or None,
    timeout=settings.llm_timeout,
    max_retries=settings.llm_max_retries,
)

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


async def synthesize_elements(element_1: str, element_2: str) -> dict:
    """Вызывает LLM и возвращает распарсенный JSON с result/description/image_prompt_en."""
    user_prompt = f"Соедини эти два элемента: {element_1} + {element_2}"
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": settings.system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=settings.llm_temperature,
        # Лимит с запасом: это reasoning-модель, часть бюджета уходит на размышления
        max_tokens=settings.llm_max_tokens,
        response_format=RESPONSE_SCHEMA,
        # Короткие размышления: заметно быстрее без потери качества ответа
        extra_body={"reasoning": {"effort": "low"}},
    )
    raw_content = response.choices[0].message.content
    return extract_json(raw_content)


def parse_synthesis(
    result_json: dict,
    element_1: str,
    element_2: str,
) -> tuple[str, str, str]:
    element_name = result_json.get("result", "Неизвестный элемент").strip()
    element_desc = result_json.get(
        "description", "Трансмутация прошла нестабильно."
    ).strip()
    image_prompt_en = result_json.get(
        "image_prompt_en",
        f"A magical hybrid of {element_1} and {element_2}",
    ).strip()
    return element_name, element_desc, image_prompt_en


# Re-export for callers that need to catch JSON errors from extract_json
JSONDecodeError = json.JSONDecodeError
