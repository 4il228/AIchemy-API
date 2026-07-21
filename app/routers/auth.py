"""Эндпоинты регистрации/входа/выхода.

Токен сессии передаётся ТОЛЬКО в HttpOnly-cookie:
- HttpOnly  — JS не имеет доступа к токену (защита от XSS-кражи);
- Secure    — cookie уходит только по HTTPS (отключаемо для локальной разработки);
- SameSite=Strict — браузер не отправит cookie с чужих сайтов, что закрывает
  CSRF для этого JSON-API без отдельного anti-CSRF-токена.
Хранение токена в localStorage/sessionStorage не используется и запрещено.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config import settings
from app.schemas import LoginRequest, MessageResponse, RegisterRequest, UserResponse
from app.services import auth as auth_service
from app.utils.ratelimit import build_rate_limiter
from db import async_session

router = APIRouter(prefix="/auth", tags=["auth"])

# Отдельные лимитеры на вход и регистрацию (защита от brute-force per-IP)
login_rate_limit = build_rate_limiter(
    settings.login_rate_limit, settings.rate_limit_window_seconds
)
register_rate_limit = build_rate_limiter(
    settings.register_rate_limit, settings.rate_limit_window_seconds
)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,                     # недоступна из JS (XSS)
        secure=settings.cookie_secure,     # только HTTPS (в проде)
        samesite="strict",                 # не отправляется cross-site (CSRF)
        path="/",
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    dependencies=[Depends(register_rate_limit)],
)
async def register(payload: RegisterRequest, response: Response) -> UserResponse:
    """Регистрация. Сложность пароля проверяется валидатором схемы."""
    async with async_session() as db:
        user = await auth_service.register_user(db, payload.nickname, payload.password)
        if user is None:
            raise HTTPException(status_code=409, detail="Никнейм уже занят")
        # Сразу выдаём сессию, чтобы не заставлять логиниться повторно
        token, _ = await auth_service.create_session(db, user.id)
        _set_session_cookie(response, token)
        return UserResponse(id=user.id, nickname=user.nickname)


@router.post(
    "/login",
    response_model=UserResponse,
    dependencies=[Depends(login_rate_limit)],
)
async def login(payload: LoginRequest, response: Response) -> UserResponse:
    async with async_session() as db:
        user = await auth_service.authenticate(db, payload.nickname, payload.password)
        if user is None:
            # Единый ответ для «нет пользователя» и «неверный пароль» —
            # защита от перечисления пользователей (user enumeration)
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")
        token, _ = await auth_service.create_session(db, user.id)
        _set_session_cookie(response, token)
        return UserResponse(id=user.id, nickname=user.nickname)


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response) -> MessageResponse:
    """Выход: удаляем сессию в БД (инвалидация) и cookie у клиента."""
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        async with async_session() as db:
            await auth_service.revoke_session(db, token)
    _delete_session_cookie(response)
    return MessageResponse(message="Вы вышли из системы")


@router.get("/me", response_model=UserResponse)
async def me(request: Request) -> UserResponse:
    """Текущий пользователь по cookie-сессии."""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    async with async_session() as db:
        user = await auth_service.resolve_session(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return UserResponse(id=user.id, nickname=user.nickname)
