# 🖥️ IT-служба колледжа — Core REST API

Центральный **чистый** бэкенд системы автоматизации IT-службы колледжа:
только данные и бизнес-логика. Core API **не знает о существовании мессенджера MAX**,
не хранит токены бота и не делает HTTP-запросов во внешние сети.

Вся коммуникация с MAX осуществляется отдельным приложением — **Ботом**,
который работает как обычный REST-клиент (см. раздел «Интеграция с Ботом»).

## Архитектура

```
┌──────────┐   REST (X-API-Key)    ┌─────────────────┐   asyncpg   ┌────────────┐
│  Бот MAX │ ◄───────────────────► │   Core API      │ ◄─────────► │ PostgreSQL │
│(MAX API, │  очередь уведомлений, │  (FastAPI)      │             │    15+     │
│ вебхуки) │  синк профилей        │  без внешних    │             │            │
└──────────┘                       │  вызовов в MAX  │             └────────────┘
┌──────────┐   REST (JWT)           └─────────────────┘
│Веб-панель│ ◄───────────────────►         ▲
└──────────┘                               │ паттерн «Очереди в БД»:
                              notifications + notification_history
```

* **Уведомления:** при бизнес-событиях (создан тикет, назначен исполнитель,
  сменён статус, дубль, изменение баллов) сервисы пишут запись в `notifications`
  (+ `pending` в `notification_history`). Доставку выполняет Бот/воркер.
* **Профили пользователей:** поля `max_user_id` и `raw_profile` (JSONB) остаются —
  это идентификаторы пользователя в экосистеме MAX; Бот синхронизирует их через
  `PATCH /users/by-max-id/{max_user_id}/profile`.

## Стек

Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, PostgreSQL 15+.

## Структура проекта

```text
app/
├── main.py                 # Точка входа: FastAPI, Swagger, CORS, обработчики ошибок
├── core/                   # config.py, database.py, security.py
├── models/                 # ORM: users, tickets, references, gamification, moderation, notifications
├── schemas/                # Pydantic DTO по доменам (+ notifications.py)
├── repositories/           # CRUD-слой (soft delete) + notifications_repo.py (очередь)
├── services/               # ticket_service, points_service, notification_service (очередь в БД)
├── api/                    # deps.py (JWT / X-API-Key), v1/: users, tickets, references,
│                           #       gamification, notifications
└── utils/
alembic/                    # миграции (async env)
scripts/seed.py             # сидирование справочников
```

## Быстрый старт (локально)

### 1. Установка зависимостей

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка окружения

```bash
cp .env.example .env
```

Заполните: `DATABASE_URL`, `JWT_SECRET_KEY`, `SERVICE_API_KEY`.
Переменные MAX API в `.env` **не нужны** — токен бота живёт только в репозитории Бота.

### 3. Миграции и сиды

```bash
alembic upgrade head
python scripts/seed.py
```

Сиды заполняют справочники: роли, статусы/типы/приоритеты/источники тикетов,
адреса, подразделения, правила баллов, шаблоны уведомлений (`ticket_received`,
`ticket_assigned`, `ticket_status_changed`, `ticket_duplicate`, `points_changed` …),
демо-аккаунт веб-панели `admin/admin`.

### 4. Запуск

```bash
uvicorn app.main:app --reload
```

Swagger: http://localhost:8000/docs , ReDoc: http://localhost:8000/redoc

## Запуск в Docker Compose

```bash
docker compose --profile setup up -d --build   # БД + миграции + сиды + API
# Swagger: http://localhost:8000/docs
docker compose logs -f api
docker compose down
```

Сервисы: `postgres` (данные в volume `postgres_data`), `api` (uvicorn, healthcheck `/health`),
одноразовый `migrate` (`alembic upgrade head && python scripts/seed.py`).

## Аутентификация

| Клиент | Способ | Описание |
|---|---|---|
| Веб-панель | `Authorization: Bearer <JWT>` | `POST /api/v1/auth/login` (web_accounts). Легаси-MD5 хэш при первом входе автоматически пересохраняется в bcrypt. |
| Бот / внутренние сервисы | `X-API-Key: <SERVICE_API_KEY>` | Действия от имени пользователя: `?user_id=<uuid>` или `?max_user_id=<id из MAX>`. |

## Интеграция с Ботом (MAX)

Core API предоставляет чистый REST. Бот — отдельное приложение, которое:

1. **Принимает вебхуки/события MAX сам** (Long Poll / webhook на своей стороне).
2. **Синхронизирует профили:** `PATCH /api/v1/users/by-max-id/{max_user_id}/profile`
   c телом из профиля MAX (`first_name`, `name`, `username`, `is_bot`,
   `last_activity_time`, `raw_profile` — JSON сохраняется как есть).
   Поиск: `GET /api/v1/users/by-max-id/{max_user_id}`.
3. **Создаёт тикеты от имени пользователя:** `POST /api/v1/tickets?max_user_id=...`
   с заголовком `X-API-Key` (проверки лимитов роли и баллов — на стороне API).
4. **Доставляет уведомления (очередь в БД):**
   * `GET /api/v1/notifications/queue/pending` — выбрать недоставленные;
   * отправить текст получателю через MAX API (`POST /v3/messages`, https://dev.max.ru/docs);
   * `PATCH /api/v1/notifications/{id}/delivery-status` `{"status": "sent"|"failed", "error_message": ...}`.
5. Опционально читает события тикетов через `GET /api/v1/tickets/{id}` и пишет сообщения
   `POST /api/v1/tickets/{id}/messages` (флаг `is_internal` для служебной переписки).

**Чего нет в Core API (и не должно быть):** HTTP-клиент к MAX, эндпоинты
`/integrations/max/webhooks`, `/integrations/max/send-message`, `/integrations/max/profile/*`,
токены `MAX_BOT_TOKEN`/`MAX_API_*` в конфигурации.

## Основные группы эндпоинтов (Swagger tags)

* **Auth** — JWT-логин веб-панели (MD5 → bcrypt ресейв).
* **Tickets** — создание (лимиты role_limits + списание баллов), assign, статусы
  (закрывает только admin), дубли, сообщения, история.
* **Users & Moderation** — поиск по `max_user_id`, синхронизация профиля (для бота),
  блокировка/blacklist, жалобы.
* **Gamification** — баланс/транзакции, ручная корректировка, топ рейтинга.
* **References** — CRUD справочников (мутации — только admin).
* **Notifications Queue** — чтение своих уведомлений, pending-очередь и отчёт о
  доставке для Бота/воркера.

## Безопасность и аудит

* Soft delete везде (`is_deleted`/`deleted_at`), UUID PK, двойная нумерация тикетов
  (`id` внутри, `ticket_number` наружу).
* Каждое критичное действие (статус, назначение, блокировка, баллы, синхронизация
  профиля) пишется в `audit_log`; изменения тикета — в `ticket_history`.
* Валидация входных данных Pydantic v2 (cabinet ≤ 100 симв., rating 1–5 и т. д.).

## Smoke-проверка

```bash
curl -s http://localhost:8000/health
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' -d '{"login":"admin","password":"admin"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s http://localhost:8000/api/v1/references/roles -H "Authorization: Bearer $TOKEN" | head -c 300
```

## Лицензия

MIT
