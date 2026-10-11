"""Точка входа: инициализация FastAPI, Swagger (OpenAPI), CORS, роутеры, обработчики ошибок."""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("app.main")

# ----------------------------------------------------------------Swagger теги
tags_metadata = [
    {
        "name": "Auth",
        "description": "Аутентификация веб-панели: логин/пароль через `web_accounts`, выдача JWT. "
        "При первом входе легаси-MD5 хэш автоматически пересохраняется в bcrypt.",
    },
    {
        "name": "Tickets",
        "description": "Жизненный цикл обращений: создание с проверкой лимитов роли и баланса баллов, "
        "назначение исполнителя, смена статусов (закрытие — только admin), признание дублей, "
        "переписка (в т.ч. внутренние сообщения) и история изменений.",
    },
    {
        "name": "Users & Moderation",
        "description": "Пользователи (поиск по `max_user_id` — критично для бота MAX), блокировка "
        "с записью в blacklist, жалобы сотрудников на пользователей.",
    },
    {
        "name": "Gamification",
        "description": "Баллы и рейтинг: баланс/история транзакций, ручная корректировка админом, топ рейтинга.",
    },
    {
        "name": "References",
        "description": "Справочники: адреса (корпуса), типы и статусы тикетов, приоритеты, роли, подразделения. "
        "Чтение — всем аутентифицированным, мутации — только админам.",
    },
    {
        "name": "Notifications Queue",
        "description": "Очередь уведомлений (паттерн «Очереди в БД»). Core API только формирует "
        "записи в `notifications`/`notification_history`; фактическую доставку в мессенджер MAX "
        "выполняет отдельное приложение — Бот, выбирая pending-очередь и отчитываясь о статусе "
        "доставки по сервисному ключу.",
    },
]

# ------------------------------------------------------------------- OpenAPI
openapi_extra: dict = {
    "components": {
        "examples": {
            "TicketExample": {
                "summary": "Пример тикета",
                "value": {
                    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "ticket_number": 1042,
                    "title": "Не печатает принтер в кабинете 305",
                    "description": "Принтер HP LaserJet зависает на очереди печати.",
                    "type_id": "b0a7d2c4-0000-4000-8000-000000000001",
                    "status_code": "new",
                    "priority_code": "medium",
                    "source_code": "bot",
                    "author_id": "c0a7d2c4-0000-4000-8000-000000000002",
                    "address_id": "d0a7d2c4-0000-4000-8000-000000000003",
                    "cabinet": "305",
                    "assigned_to": None,
                    "created_at": "2026-10-11T09:00:00+03:00",
                },
            },
            "ErrorResponse": {
                "summary": "Типовая ошибка",
                "value": {"detail": "Недостаточно баллов для создания тикета"},
            },
        },
        "securitySchemes": {
            "BearerJwt": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT-токен веб-панели (выдаётся через POST /auth/login).",
            },
            "ServiceApiKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Сервисный ключ внутренних клиентов (бот MAX).",
            },
        },
    }
}

app = FastAPI(
    title=settings.app_name,
    description=(
        f"{settings.app_description}\n\n"
        "## Аутентификация\n"
        "* **Веб-панель** — JWT Bearer-токен (`POST /api/v1/auth/login`).\n"
        "* **Бот/внутренние сервисы** — заголовок `X-API-Key` (сервисный токен).\n"
        "* Бот работает как обычный REST-клиент: сам общается с MAX API, "
        "синхронизирует профили (`PATCH /users/by-max-id/{id}/profile`) и доставляет очередь уведомлений.\n\n"
        "## Соглашения\n"
        "* Внешний номер тикета — `ticket_number`, внутренний UUID — `id`.\n"
        "* Удаление — мягкое (`is_deleted`), REST DELETE выполняет UPDATE.\n"
        "* Пагинация — параметры `page` / `page_size`, ответ обёрнут в `Page`."
    ),
    version=settings.app_version,
    openapi_tags=tags_metadata,
    servers=[
        {"url": "http://localhost:8000", "description": "Dev"},
        {"url": "https://it-service.college.example.com", "description": "Prod"},
    ],
    openapi_extra=openapi_extra,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "IT-служба колледжа", "email": "support@college.example.com"},
    license_info={"name": "MIT"},
)

# ----------------------------------------------------------------------- CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # '*' + credentials несовместимы
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------- Router
app.include_router(api_v1_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["Health"], summary="Корневой/health-check эндпоинт")
async def root() -> dict:
    """Возвращает базовую информацию о сервисе. Полезен для мониторинга и быстрой проверки запуска."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "openapi_url": app.openapi_url,
    }


@app.get("/health", tags=["Health"], summary="Health-check для Docker/orchestrator")
async def health() -> dict:
    """Лёгкая проверка живости сервиса (используется healthcheck'ом в docker-compose)."""
    return {"status": "ok"}


# ---------------------------------------------------------- Обработчики ошибок
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Стандартная обработка HTTPException в едином формате {\"detail\": ...}."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Фолбэк: логируем стектрейс на сервере, клиенту — 500 без утечки деталей."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера. Попробуйте позже."},
    )
