import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    openrouter_api_key: str = os.environ.get("OPENROUTER_API_KEY", "")
    system_prompt: str = os.environ.get("SYSTEM_PROMPT", "")
    style_modifiers: str = os.environ.get("STYLE_MODIFIERS", "")

    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "tencent/hy3:free"
    llm_timeout: float = 45.0
    llm_max_retries: int = 2
    llm_temperature: float = 1.2
    llm_max_tokens: int = 2000

    images_dir: Path = Path("generated_images")
    image_width: int = 1024
    image_height: int = 1024
    image_model: str = "flux"
    image_download_timeout: float = 120.0

    app_title: str = "Алхимический Микросервис с Точной Визуализацией"
    default_creator_nickname: str = "AIchemist"
    seed_user_id: int = 1
    seed_user_nickname: str = "AIchemist"


settings = Settings()
