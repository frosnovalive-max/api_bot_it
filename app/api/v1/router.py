"""Главный роутер API v1 — собирает все доменные под-роутеры.

Примечание: роутер интеграций с MAX удалён — Core API не общается с мессенджером
напрямую. Бот работает как обычный REST-клиент (Users, Tickets, Notifications Queue).
"""
from fastapi import APIRouter

from app.api.v1 import (
    gamification,
    notifications,
    references,
    tickets,
    users,
)

api_v1_router = APIRouter()

# Префиксы/теги уже заданы внутри каждого под-роутера,
# кроме users/gamification — их эндпоинты начинаются с /users, /points, /rating, /complaints, /auth.
api_v1_router.include_router(users.router)
api_v1_router.include_router(tickets.router)
api_v1_router.include_router(references.router)
api_v1_router.include_router(gamification.router)
api_v1_router.include_router(notifications.router)
