<div align="center">

# 🧪 AIchemy API

### Алхимический микросервис с точной визуализацией

*Два элемента + ИИ → новый результат, описание и изображение*



</div>

---

## 📋 Содержание

- [О проекте](#-о-проекте)
- [Архитектура](#-архитектура)
- [Как это работает](#-как-это-работает)
- [Быстрый старт](#-быстрый-старт)
- [Аутентификация](#-аутентификация)
- [API](#-api)
- [Структура проекта](#-структура-проекта)
- [Администрирование](#-администрирование)
- [Конфигурация](#-конфигурация)
- [Roadmap](#-roadmap)

---

## 🧙 О проекте

**AIchemy** — это компактный FastAPI-микросервис, который принимает два текстовых элемента, синтезирует через LLM новый уникальный объект (название + описание на русском), генерирует визуальное представление через нейросеть и кэширует результат в SQLite.

**Ключевая идея:** каждый рецепт крафтится только один раз — первый запрос проходит полный цикл (LLM + генерация картинки), все последующие мгновенно получают закэшированный результат из базы.

> ⚠️ Это **движок синтеза** для будущей многопользовательской алхимической игры. Дизайн продукта (аккаунты, рынок, колбы, таймеры, экономика) описан в `DESIGN.md`, спецификация для агентов — в `SPEC.md`, `PLAN.md`, `AGENTS.md` (все — локально, не в репозитории), но ещё **не реализован** в коде.

---

## 🏗 Архитектура

```
┌─────────────┐     POST /api/v1/craft     ┌──────────────────────────────────┐
│   Client    │ ──────────────────────────► │        FastAPI Server           │
│  (curl/UI)  │ ◄────────────────────────── │  (main.py → app.factory)        │
└─────────────┘     CraftResponse JSON      └──────┬───────────────────────────┘
                                                   │
                    ┌────────────────────────────────┼───────────────────────┐
                    │               HIT              │       MISS            │
                    ▼                                ▼                       │
            ┌──────────────┐                 ┌──────────────────┐           │
            │  SQLite DB   │                 │ services/llm.py  │           │
            │  recipes     │                 │  OpenRouter LLM  │           │
            │  (кэш)       │                 │  tencent/hy3     │           │
            └──────┬───────┘                 └────────┬─────────┘           │
                   │                                  │                     │
                   │                          ┌───────▼────────┐           │
                   │                          │ services/images│           │
                   │                          │  Pollinations  │           │
                   │                          │  flux 1024×1024│           │
                   │                          └───────┬────────┘           │
                   │                                  │                     │
                   └─────────────── сохраняем ◄────────┘                    │
                                                    │                      │
                                                    ▼                      │
                                            ┌──────────────────┐          │
                                            │ generated_images/│ ◄────────┘
                                            │    *.png files   │
                                            └──────────────────┘
```

### Стек технологий

| Слой | Технология |
|------|-----------|
| **Язык** | Python 3.12+ |
| **API-фреймворк** | FastAPI + Uvicorn |
| **Валидация** | Pydantic v2 |
| **ORM** | SQLAlchemy 2.x (async) |
| **БД** | SQLite (`aiosqlite`) / PostgreSQL (`asyncpg`) |
| **Аутентификация** | Серверные сессии + Argon2id (`argon2-cffi`), HttpOnly-cookie |
| **LLM** | OpenAI SDK → OpenRouter (`tencent/hy3:free`) |
| **Генерация изображений** | httpx → Pollinations (`flux`, 1024×1024) |
| **Config / secrets** | python-dotenv + `.env` (gitignored) |
| **LLM System Prompt** | `.env` → `SYSTEM_PROMPT` |
| **Admin UI** | Tkinter + Pillow |
| **Архитектура** | Модульная (пакет `app/` с роутерами, сервисами, утилитами) |

---

## ⚙️ Как это работает

### Алгоритм крафта

1. **Нормализация**: пара элементов приводится к единому регистру и сортируется — `"Огонь" + "Вода"` ≡ `"вода" + "ОГОНЬ"`.
2. **Cache hit**: если комбинация уже есть в БД — мгновенный ответ (если файл картинки удалён — перескачка по сохранённому промпту без LLM).
3. **Cache miss**: 
   - LLM синтезирует название, описание (RU) и английский промпт для картинки
   - Pollinations генерирует изображение (1024×1024, dark fantasy стиль)
   - Рецепт сохраняется в SQLite с уникальным именем файла (транслит ГОСТ 7.79 + хеш пары)
4. **Race condition**: конкурентные первые крафты обрабатываются через `IntegrityError` — второй запрос получает данные первого без потери.

---

## 🚀 Быстрый старт

### 1. Клонирование и окружение

```bash
git clone https://github.com/4il228/AIchemy-API.git
cd AIchemy-API

python -m venv venv

# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

pip install fastapi uvicorn openai python-dotenv sqlalchemy aiosqlite httpx pillow argon2-cffi
```

### 2. Переменные окружения

Создайте `.env` в корне проекта:

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Для локальной разработки по http (в проде за HTTPS — убрать или true)
COOKIE_SECURE=false

# Опционально — кастомные промпты (если не заданы → встроенные fallback'ы)
# SYSTEM_PROMPT="Your custom system prompt..."
# STYLE_MODIFIERS="Your custom style modifiers..."
```

Опционально — строка подключения к БД (по умолчанию — локальный SQLite):

```env
DATABASE_URL=sqlite+aiosqlite:///./alchemy.db
```

### 3. Запуск

```bash
python main.py
```

Сервер доступен на [http://localhost:8000](http://localhost:8000).  
Документация OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 🔐 Аутентификация

Сервис использует **серверные сессии** с cookie. Токен сессии передаётся исключительно в `HttpOnly`-cookie — клиентский JS не имеет к нему доступа, хранить его в `localStorage`/`sessionStorage` не нужно и нельзя.

### Меры безопасности

| Вектор атаки | Защита |
|--------------|--------|
| Кража пароля из БД | Argon2id (time_cost=3, 64 МиБ, parallelism=4), пароли не логируются |
| Кража токена из БД | В БД хранится только SHA-256 токена; сырой токен есть лишь в cookie клиента |
| XSS-кража токена | `HttpOnly`-cookie, токен недоступен из JS |
| CSRF | `SameSite=Strict` — браузер не отправляет cookie с чужих сайтов |
| Перехват по сети | `Secure`-cookie (только HTTPS; для локального http — `COOKIE_SECURE=false`) |
| Brute-force | Per-IP rate limiting: 5 попыток входа и 3 регистрации в минуту (настраивается) |
| User enumeration / timing | Единый ответ `401 «Неверный логин или пароль»` + dummy-верификация Argon2 при неизвестном логине |
| SQL-инъекции | Только SQLAlchemy ORM, никакого сырого SQL с пользовательским вводом |

### Эндпоинты

#### `POST /api/v1/auth/register`

Регистрация. Требования: никнейм 3–50 символов (`a-z`, `A-Z`, `0-9`, `_`, `-`), пароль 8–128 символов, минимум одна буква и одна цифра.

```json
{ "nickname": "alchemist_42", "password": "S3cretPass" }
```

Ответ `201` + сессионная cookie (сразу авторизован):

```json
{ "id": 2, "nickname": "alchemist_42" }
```

Ошибки: `409` — никнейм занят, `422` — невалидные данные, `429` — превышен лимит попыток.

#### `POST /api/v1/auth/login`

Вход. Тело как у регистрации. Ответ `200` + cookie `session_token` (`HttpOnly; Secure; SameSite=Strict`, TTL 7 дней по умолчанию).

Ошибки: `401` — неверный логин или пароль (единый ответ), `429` — превышен лимит попыток.

#### `POST /api/v1/auth/logout`

Выход: сессия удаляется в БД (мгновенная инвалидация), cookie стирается.

#### `GET /api/v1/auth/me`

Текущий пользователь по cookie-сессии. `401`, если не авторизован.

### Пример полного цикла

```bash
# Регистрация (cookie сохраняется в файл)
curl -c cookies.txt -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"nickname": "alchemist_42", "password": "S3cretPass"}'

# Крафт под своим аккаунтом (cookie отправляется из файла)
curl -b cookies.txt -X POST http://localhost:8000/api/v1/craft \
  -H "Content-Type: application/json" \
  -d '{"element_1": "Огонь", "element_2": "Вода"}'

# Выход
curl -b cookies.txt -X POST http://localhost:8000/api/v1/auth/logout
```

### Защита собственных эндпоинтов

Любой маршрут делается приватным одной зависимостью:

```python
from fastapi import Depends
from app.deps import get_current_user

@router.post("/my-private-route")
async def my_route(current_user_id: int = Depends(get_current_user)):
    ...
```

---

## 📡 API

### `POST /api/v1/craft` 🔒

Крафт нового элемента из двух компонентов. **Требует авторизации** (cookie-сессия): неавторизованный запрос получает `401`. Создателем рецепта (`creator_id`, `creator_nickname`) становится авторизованный пользователь, выполнивший реакцию первым.

**Запрос:**

```json
{
  "element_1": "Огонь",
  "element_2": "Вода"
}
```

**Успешный ответ (200):**

```json
{
  "result": "Пар",
  "description": "Огонь испаряет воду, образуя пар — газообразное состояние воды при высокой температуре.",
  "image_url": "/images/par_a1b2c3d4.png",
  "creator_id": 1,
  "creator_nickname": "AIchemist"
}
```

**Ошибки:**

| Код | Причина |
|-----|---------|
| 401 | Не авторизован (нет/истекла cookie-сессия) |
| 422 | Пустой элемент |
| 500 | Отсутствует API-ключ |
| 502 | Ошибка LLM / генерации картинки |

### Примеры использования

```bash
# Сначала вход (cookie в файл)
curl -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"nickname": "alchemist_42", "password": "S3cretPass"}'

# Крафт "Человек + Ёж" под своим аккаунтом
curl -b cookies.txt -X POST http://localhost:8000/api/v1/craft \
  -H "Content-Type: application/json" \
  -d '{"element_1": "Человек", "element_2": "Ёж"}'

# Просмотр картинки результата
curl http://localhost:8000/images/par_a1b2c3d4.png --output result.png
```

### `GET /api/v1/recipes`

Получение списка всех открытых рецептов (в порядке убывания ID). Публичный, read-only.

---

## 📁 Структура проекта

```
AIchemy-API/
├── main.py                 # Точка входа — создаёт приложение через create_app()
├── db.py                   # SQLAlchemy модели (Recipe, User, Session), async engine, init_db
├── admin.py                # Десктопная админка на Tkinter (CRUD рецептов)
├── README.md               # Этот файл
├── .env                    # Секреты и системные промпты (не коммитится)
├── .gitignore              # Игнорируемые файлы
├── alchemy.db              # SQLite-база (создаётся при старте)
├── generated_images/       # Сгенерированные PNG (создаётся при старте)
│
└── app/                    # Модульная структура приложения
    ├── __init__.py
    ├── config.py           # Настройки из .env (Settings + экземпляр settings)
    ├── schemas.py          # Pydantic-схемы (Craft*, Register/Login, UserResponse)
    ├── deps.py             # get_current_user — проверка cookie-сессии (401)
    ├── factory.py          # Фабрика FastAPI-приложения (create_app)
    ├── lifespan.py         # Startup/shutdown: init_db, сидирование пользователя
    │
    ├── routers/            # HTTP-роутеры (FastAPI APIRouter)
    │   ├── __init__.py     # api_router = /api/v1 + подключение auth + craft + recipes
    │   ├── auth.py         # POST /auth/register|login|logout, GET /auth/me
    │   ├── craft.py        # POST /api/v1/craft (приватный)
    │   └── recipes.py      # GET /api/v1/recipes
    │
    ├── services/           # Бизнес-логика
    │   ├── __init__.py
    │   ├── auth.py         # Argon2id-хеширование, сессии, timing-защита
    │   ├── craft.py        # Оркестрация крафта + работа с БД
    │   ├── llm.py          # LLM-клиент (OpenRouter → OpenAI SDK)
    │   └── images.py       # Генерация и скачивание картинок (Pollinations)
    │
    └── utils/              # Вспомогательные функции
        ├── __init__.py
        ├── ratelimit.py    # In-memory rate limiter (per-IP, sliding window)
        └── text.py         # Транслитерация, слаги, extract_json
```

> 📝 В репозитории только `README.md`. Файлы `AGENTS.md`, `PLAN.md`, `SPEC.md`, `SPEC(base).md`, `DESIGN.md` хранятся локально — они не отслеживаются git и отсутствуют в истории.

### Описание ключевых файлов

| Файл / Модуль | Назначение |
|---------------|-----------|
| `main.py` | Точка входа — вызывает `app.factory.create_app()` и запускает uvicorn |
| `db.py` | Модели ORM (Recipe, User, Session), движок, фабрика сессий, инициализация схемы |
| `admin.py` | Tkinter-приложение для управления БД рецептов без HTTP |
| `app/config.py` | Единый источник конфигурации (переменные окружения + константы) |
| `app/schemas.py` | Pydantic-схемы запросов/ответов + валидация никнейма и сложности пароля |
| `app/deps.py` | `get_current_user`: cookie → сессия в БД → `user_id`, иначе `401` |
| `app/factory.py` | Фабрика FastAPI: монтирует static, подключает роутеры |
| `app/lifespan.py` | Асинхронный lifespan: инициализация БД и seed-пользователя |
| `app/routers/` | HTTP-эндпоинты (auth, craft, recipes) — минимум логики, диспатч в сервисы |
| `app/services/auth.py` | Пароли (Argon2id), сессии (SHA-256 токена в БД), защита от timing-атак |
| `app/services/craft.py` | Оркестрация крафта: кэш, LLM → картинка → сохранение, race condition |
| `app/utils/ratelimit.py` | Rate limiter per-IP для `/auth/login` и `/auth/register` |
| `app/services/llm.py` | OpenAI-клиент → OpenRouter, строгая JSON-схема ответа |
| `app/services/images.py` | Скачивание картинок с Pollinations на диск |
| `app/utils/text.py` | Транслитерация (ГОСТ 7.79), слаги, извлечение JSON из ответа LLM |

---

## 🖥 Администрирование

В проекте есть десктопное приложение для управления базой рецептов:

```bash
python admin.py
```

Возможности:
- 📋 Таблица рецептов с сортировкой по ID
- 🔍 Поиск по названию/элементам (с поддержкой кириллицы)
- ✏️ Редактирование названия, описания, промпта
- 🖼️ Предпросмотр изображения (через Pillow)
- ❌ Удаление рецептов вместе с файлами картинок
- ➕ Добавление новых рецептов вручную

> Админка использует **синхронный** SQLAlchemy (Tkinter не дружит с asyncio).

---

## ⚙️ Конфигурация

### Переменные окружения

| Переменная | Обязательна | По умолчанию | Описание |
|-----------|-------------|-------------|----------|
| `OPENROUTER_API_KEY` | ✅ (для крафта) | — | Ключ API OpenRouter |
| `DATABASE_URL` | ❌ | `sqlite+aiosqlite:///./alchemy.db` | Строка подключения к БД |
| `SYSTEM_PROMPT` | ❌ | встроенный fallback | Системный промпт для LLM |
| `STYLE_MODIFIERS` | ❌ | встроенный fallback | Стилевой суффикс для генерации изображений |
| `COOKIE_SECURE` | ❌ | `true` | `Secure`-флаг сессионной cookie; `false` только для локального http |
| `SESSION_TTL_HOURS` | ❌ | `168` | Время жизни сессии (часов) |
| `SESSION_COOKIE_NAME` | ❌ | `session_token` | Имя сессионной cookie |
| `LOGIN_RATE_LIMIT` | ❌ | `5` | Попыток входа с одного IP за окно |
| `REGISTER_RATE_LIMIT` | ❌ | `3` | Регистраций с одного IP за окно |
| `RATE_LIMIT_WINDOW_SECONDS` | ❌ | `60` | Размер окна rate limiter (секунд) |

### Жёстко заданные параметры (в коде)

- Модель LLM: `tencent/hy3:free` (OpenRouter)
- Генерация картинок: Pollinations (`flux`, 1024×1024)
- Порт сервера: `8000`

### Переход на PostgreSQL

```bash
pip install asyncpg
```

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/alchemy
```

Схема создаётся автоматически при старте — миграции не требуются.

---

## 🗺 Roadmap

### Реализовано ✅
- [x] Крафт A + B → результат + описание + изображение
- [x] Глобальный кэш рецептов (SQLite)
- [x] Симметричные ключи (порядок и регистр не важны)
- [x] Локальное хранение PNG + статика `/images`
- [x] Desktop-админка (Tkinter)
- [x] Система создателей (`creator_id` + `creator_nickname`)
- [x] Обработка race condition при параллельном крафте
- [x] Автоматическая перегенерация изображений при потере файла
- [x] Модульная архитектура (роутеры, сервисы, утилиты, фабрика)
- [x] Регистрация и вход (Argon2id + серверные сессии в HttpOnly-cookie)
- [x] Приватный крафт: создателем рецепта становится авторизованный пользователь
- [x] Rate limiting на вход/регистрацию (защита от brute-force)

### В плане 📋
- [ ] Инвентарь игроков и ценность элементов
- [ ] Алхимические колбы с таймерами
- [ ] Рынок и торговля элементами
- [ ] Трансмутация Хаоса
- [ ] Стартовый набор для новых игроков
- [ ] Экономика и монетизация

---

<div align="center">

---

**AIchemy API** — *превращаем слова в артефакты* 🧪✨

[OpenAPI Docs](http://localhost:8000/docs) · [GitHub](https://github.com/4il228/AIchemy-API)

</div>
