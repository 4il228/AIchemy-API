import urllib.parse

import httpx

from app.config import settings


async def download_image(image_prompt_en: str, filename: str) -> None:
    """Скачивает сгенерированную картинку с Pollinations на диск."""
    final_prompt = f"{image_prompt_en}, {settings.style_modifiers}"
    encoded_prompt = urllib.parse.quote(final_prompt)
    base = settings.image_base_url.rstrip("/")
    url = (
        f"{base}/{encoded_prompt}"
        f"?width={settings.image_width}&height={settings.image_height}"
        f"&model={settings.image_model}&nologo=true"
    )
    async with httpx.AsyncClient(
        timeout=settings.image_download_timeout, follow_redirects=True
    ) as http:
        resp = await http.get(url)
        resp.raise_for_status()
    (settings.images_dir / filename).write_bytes(resp.content)


def image_url_for(filename: str) -> str:
    return f"/images/{filename}"
