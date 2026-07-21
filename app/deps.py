"""Injected-зависимости FastAPI.

get_current_user — защита приватных маршрутов: проверяет cookie-сессию
и возвращает id пользователя. creator_id берётся ТОЛЬКО отсюда и никогда
из тела запроса (Client-Side Trust = False).

Использование: добавить параметр
    current_user_id: int = Depends(get_current_user)
в любой эндпоинт, который должен быть приватным.
"""

from fastapi import HTTPException, Request

from app.config import settings
from app.services import auth as auth_service
from db import async_session


async def get_current_user(request: Request) -> int:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    async with async_session() as db:
        user = await auth_service.resolve_session(db, token)
    if user is None:
        # Единый ответ для отсутствующей, чужой и истёкшей сессии
        raise HTTPException(status_code=401, detail="Не авторизован")
    return user.id
