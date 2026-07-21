"""In-memory rate limiter (sliding window, per-IP) — защита от brute-force.

Без внешних зависимостей: для одного процесса uvicorn достаточно словаря
в памяти. При переходе на несколько воркеров/реплик заменить на Redis.
"""

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import HTTPException, Request


class RateLimiter:
    """FastAPI-зависимость: не более max_requests за window_seconds с одного IP."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        # Прямое подключение: берём IP сокета. За reverse-proxy следует
        # доверять X-Forwarded-For только после настройки proxy_headers у uvicorn.
        return request.client.host if request.client else "unknown"

    async def __call__(self, request: Request) -> None:
        now = time.monotonic()
        window = self._hits[self._client_ip(request)]
        # Выкидываем запросы, вышедшие за скользящее окно
        while window and now - window[0] > self.window_seconds:
            window.popleft()
        if len(window) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail="Слишком много попыток. Повторите позже.",
            )
        window.append(now)


def build_rate_limiter(max_requests: int, window_seconds: float) -> Callable:
    """Фабрика лимитеров для Depends(...)."""
    return RateLimiter(max_requests, window_seconds)
