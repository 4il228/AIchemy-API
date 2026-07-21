"""
MVP: Scalar UI вместо Swagger + отдача картинок, которые рендерятся прямо в Scalar.

Запуск:
    venv\\Scripts\\python.exe -m uvicorn scalar_mvp:app --reload --port 8001

Документация: http://127.0.0.1:8001/docs
Тестовая картинка: http://127.0.0.1:8001/api/images/test.png
"""

import struct
import zlib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from scalar_fastapi import get_scalar_api_reference

IMAGES_DIR = Path("static/images")

# Расширение -> media type. Только графические форматы, которые Scalar рендерит визуально.
MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _make_test_png(path: Path, size: int = 256) -> None:
    """Генерирует градиентный PNG чистым stdlib, чтобы MVP работал из коробки."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data))
        )

    raw = b"".join(
        b"\x00" + bytes(v for x in range(size) for v in (x, y, 255 - x))
        for y in range(size)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


IMAGES_DIR.mkdir(parents=True, exist_ok=True)
if not any(IMAGES_DIR.iterdir()):
    _make_test_png(IMAGES_DIR / "test.png")


# docs_url=None отключает стандартный Swagger UI; ReDoc тоже убираем.
app = FastAPI(
    title="Scalar Image MVP",
    docs_url=None,
    redoc_url=None,
)


@app.get("/docs", include_in_schema=False)
async def scalar_docs() -> object:
    """Scalar UI на месте привычного /docs."""
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


@app.get(
    "/api/images/{image_name}",
    # response_class=FileResponse убирает дефолтный application/json из схемы,
    # а responses ниже объявляет бинарный графический контент — именно по этой
    # паре image/* + format: binary Scalar понимает, что ответ нужно
    # отрендерить как картинку, а не предлагать скачать файл.
    response_class=FileResponse,
    responses={
        200: {
            "description": "Файл изображения (рендерится в Scalar как картинка)",
            "content": {
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        404: {"description": "Изображение не найдено"},
    },
    summary="Отдать картинку из static/images/",
)
async def get_image(image_name: str) -> FileResponse:
    suffix = Path(image_name).suffix.lower()
    media_type = MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise HTTPException(
            status_code=404,
            detail=f"Поддерживаются только {', '.join(MEDIA_TYPES)}",
        )

    file_path = (IMAGES_DIR / image_name).resolve()
    # Защита от path traversal: файл обязан лежать внутри IMAGES_DIR.
    if IMAGES_DIR.resolve() not in file_path.parents:
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Изображение не найдено")

    # Явный media_type, чтобы Content-Type ответа совпадал со схемой OpenAPI.
    return FileResponse(file_path, media_type=media_type)
