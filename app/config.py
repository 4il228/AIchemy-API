import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    openrouter_api_key: str = os.environ.get("OPENROUTER_API_KEY", "")
    system_prompt: str = os.environ.get("SYSTEM_PROMPT", "")
    style_modifiers: str = os.environ.get("STYLE_MODIFIERS", "")

    openrouter_base_url: str = os.environ.get(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    llm_model: str = os.environ.get("LLM_MODEL", "poolside/laguna-xs-2.1:free")
    llm_timeout: float = float(os.environ.get("LLM_TIMEOUT", "45.0"))
    llm_max_retries: int = int(os.environ.get("LLM_MAX_RETRIES", "2"))
    llm_temperature: float = float(os.environ.get("LLM_TEMPERATURE", "1.2"))
    llm_max_tokens: int = int(os.environ.get("LLM_MAX_TOKENS", "2000"))

    images_dir: Path = Path("generated_images")
    image_base_url: str = os.environ.get(
        "IMAGE_BASE_URL", "https://image.pollinations.ai/p/"
    )
    image_width: int = int(os.environ.get("IMAGE_WIDTH", "1024"))
    image_height: int = int(os.environ.get("IMAGE_HEIGHT", "1024"))
    image_model: str = os.environ.get("IMAGE_MODEL", "flux")
    image_download_timeout: float = float(os.environ.get("IMAGE_DOWNLOAD_TIMEOUT", "120.0"))

    # --- Авторизация / сессии ---
    session_cookie_name: str = os.environ.get("SESSION_COOKIE_NAME", "session_token")
    session_ttl_hours: int = int(os.environ.get("SESSION_TTL_HOURS", "168"))
    # Secure-флаг cookie: true в проде (HTTPS); false — только для локального http
    cookie_secure: bool = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
    # Rate limiting (per-IP, скользящее окно в секундах)
    login_rate_limit: int = int(os.environ.get("LOGIN_RATE_LIMIT", "5"))
    register_rate_limit: int = int(os.environ.get("REGISTER_RATE_LIMIT", "3"))
    rate_limit_window_seconds: float = float(
        os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60")
    )

    app_title: str = "Алхимический Микросервис с Точной Визуализацией"
    default_creator_nickname: str = "AIchemist"
    seed_user_id: int = 1
    seed_user_nickname: str = "AIchemist"


settings = Settings()
