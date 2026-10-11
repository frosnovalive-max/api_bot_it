#!/usr/bin/env python3
"""Сидирование справочников начальными данными (ТЗ, раздел «Миграции»).

Идемпотентен: все вставки выполняются через ON CONFLICT DO NOTHING,
повторный запуск безопасен.

Запуск:
    python scripts/seed.py                    # использует DATABASE_URL из .env
    docker compose run --rm migrate           # внутри контейнера (после alembic upgrade head)
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

# Позволяет запускать скрипт из любого места: python scripts/seed.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402

# ------------------------------------------------------------------ Данные ---

ROLES = [
    ("admin", "Администратор", "Полный доступ: закрытие тикетов, справочники, баллы, модерация"),
    ("support", "Сотрудник IT-службы", "Исполнитель: берёт задачи в работу, внутренние сообщения"),
    ("teacher", "Педагог", "Заявитель с повышенным лимитом обращений"),
    ("staff", "Сотрудник", "Заявитель (иной персонал колледжа)"),
    ("student", "Студент", "Заявитель с базовыми лимитами"),
]

TICKET_STATUSES = [
    ("new", "Новый"),
    ("in_progress", "В работе"),
    ("closed", "Закрыт"),
    ("rejected", "Отклонён"),
    ("cancelled", "Отменён"),
    ("duplicate", "Дубль"),
]

TICKET_TYPES = [
    ("breakdown", "Поломка", "Не работает оборудование/ПО/сеть"),
    ("access_request", "Запрос доступа", "Доступ к ресурсам, учётным записям, ПО"),
    ("cartridge_request", "Заявка на картридж", "Замена/выдача картриджа принтера"),
    ("equipment_request", "Запрос оборудования", "Выдача/подключение техники"),
]

TICKET_PRIORITIES = [
    ("low", "Низкий", 10),
    ("medium", "Средний", 50),
    ("high", "Высокий", 100),
    ("critical", "Критический", 200),
]

TICKET_SOURCES = [
    ("bot", "Бот MAX"),
    ("personal", "Личное обращение"),
]

POINT_RULES = [
    # code, name, amount (см. ТЗ: создание -10, успешное закрытие +10, дубль -20)
    ("create_ticket", "Создание тикета (списание)", -10),
    ("ticket_closed_ok", "Успешное закрытие тикета (возврат)", 10),
    ("duplicate_penalty", "Штраф за дубль обращения", -20),
]

# 6 корпусов (фиксированный справочник)
ADDRESSES = [
    f"Корпус {i} — ул. Учебная, {i * 10}" for i in range(1, 7)
]

DEPARTMENTS = ["IT-служба", "Учебная часть", "Бухгалтерия", "Библиотека", "Кадров"]

NOTIFICATION_TEMPLATES = [
    ("ticket_created", "Заявка получена", "Ваша заявка №{ticket_number} принята в обработку."),
    # Шаблоны очереди уведомлений (паттерн «Очереди в БД»):
    ("ticket_received", "Заявка принята", "Ваша заявка №{ticket_number} принята и ожидает исполнителя."),
    ("ticket_assigned", "Заявка назначена", "По заявке №{ticket_number} назначен исполнитель."),
    ("ticket_status_changed", "Смена статуса", "Статус заявки №{ticket_number} изменён на {new_status}."),
    ("ticket_duplicate", "Заявка — дубль", "Заявка №{ticket_number} признана дублем."),
    ("points_changed", "Изменение баллов", "{reason}. Текущий баланс: {balance}."),
    ("ticket_resolved", "Заявка решена", "Заявка №{ticket_number} закрыта. Оцените качество решения."),
    ("ticket_overdue", "Заявка просрочена", "Заявка №{ticket_number} не обработана в срок."),
]

TEST_ADMIN = {  # демо-аккаунт веб-панели (пароль: admin) — для smoke-теста
    "login": "admin",
    "plain_password": "admin",
    "max_user_id": 900000000001,
    "first_name": "Системный",
    "name": "Администратор",
    "username": "sysadmin",
}


async def seed() -> None:
    async with AsyncSessionLocal() as s:
        # --- Справочники -----------------------------------------------------
        for code, name, desc in ROLES:
            await s.execute(
                text("INSERT INTO roles (code, name, description) VALUES (:c,:n,:d) "
                     "ON CONFLICT (code) DO NOTHING"),
                {"c": code, "n": name, "d": desc},
            )

        for code, name in TICKET_STATUSES:
            await s.execute(
                text("INSERT INTO ticket_statuses (code, name) VALUES (:c,:n) "
                     "ON CONFLICT (code) DO NOTHING"),
                {"c": code, "n": name},
            )

        for code, name, desc in TICKET_TYPES:
            await s.execute(
                text("INSERT INTO ticket_types (code, name, description) VALUES (:c,:n,:d) "
                     "ON CONFLICT (code) DO NOTHING"),
                {"c": code, "n": name, "d": desc},
            )

        for code, name, weight in TICKET_PRIORITIES:
            await s.execute(
                text("INSERT INTO ticket_priorities (code, name, weight) VALUES (:c,:n,:w) "
                     "ON CONFLICT (code) DO NOTHING"),
                {"c": code, "n": name, "w": weight},
            )

        for code, name in TICKET_SOURCES:
            await s.execute(
                text("INSERT INTO ticket_sources (code, name) VALUES (:c,:n) "
                     "ON CONFLICT (code) DO NOTHING"),
                {"c": code, "n": name},
            )

        for code, name, amount in POINT_RULES:
            await s.execute(
                text("INSERT INTO point_rules (code, name, amount) VALUES (:c,:n,:a) "
                     "ON CONFLICT (code) DO NOTHING"),
                {"c": code, "n": name, "a": amount},
            )

        for addr in ADDRESSES:
            await s.execute(
                text("INSERT INTO addresses (name) SELECT CAST(:n AS text) "
                     "WHERE NOT EXISTS (SELECT 1 FROM addresses WHERE name = CAST(:n AS text))"),
                {"n": addr},
            )

        for dep in DEPARTMENTS:
            await s.execute(
                text("INSERT INTO departments (name) SELECT CAST(:n AS text) "
                     "WHERE NOT EXISTS (SELECT 1 FROM departments WHERE name = CAST(:n AS text))"),
                {"n": dep},
            )

        for code, name, body in NOTIFICATION_TEMPLATES:
            await s.execute(
                text("INSERT INTO notification_templates (code, name, body) VALUES (:c,:n,:b) "
                     "ON CONFLICT (code) DO NOTHING"),
                {"c": code, "n": name, "b": body},
            )

        # --- Лимиты по ролям (role_limits) -----------------------------------
        limits = {  # role_code: (per_hour, per_day, min_rating, require_moderation)
            "student": (2, 5, -10, False),
            "staff": (3, 10, -10, False),
            "teacher": (5, 20, -10, False),
            "support": (None, None, None, False),
            "admin": (None, None, None, False),
        }
        for role_code, (ph, pd, mr, rm) in limits.items():
            await s.execute(
                text("INSERT INTO role_limits (role_id, max_tickets_per_hour, max_tickets_per_day, "
                     "min_rating, require_moderation) "
                     "SELECT r.id, :ph, :pd, :mr, :rm FROM roles r WHERE r.code = :rc "
                     "ON CONFLICT (role_id) DO NOTHING"),
                {"rc": role_code, "ph": ph, "pd": pd, "mr": mr, "rm": rm},
            )

        # --- Демо-администратор веб-панели ------------------------------------
        a = TEST_ADMIN
        md5_hash = hashlib.md5(a["plain_password"].encode()).hexdigest()  # легаси-MD5:
        # при первом входе /auth/login сервис автоматически пересохранит его в bcrypt.
        await s.execute(
            text("""
                INSERT INTO users (max_user_id, first_name, name, username, rating,
                                   default_address_id)
                VALUES (:mu, :fn, :nm, :un, 0,
                        (SELECT id FROM addresses ORDER BY name LIMIT 1))
                ON CONFLICT (max_user_id) DO NOTHING
            """),
            {"mu": a["max_user_id"], "fn": a["first_name"], "nm": a["name"], "un": a["username"]},
        )
        await s.execute(
            text("""
                INSERT INTO user_roles (user_id, role_id)
                SELECT u.id, r.id FROM users u, roles r
                WHERE u.max_user_id = :mu AND r.code = 'admin'
                ON CONFLICT (user_id, role_id) DO NOTHING
            """),
            {"mu": a["max_user_id"]},
        )
        await s.execute(
            text("""
                INSERT INTO user_points (user_id, balance)
                SELECT u.id, 1000 FROM users u WHERE u.max_user_id = :mu
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"mu": a["max_user_id"]},
        )
        await s.execute(
            text("""
                INSERT INTO web_accounts (user_id, login, password_hash)
                SELECT u.id, :login, :ph FROM users u WHERE u.max_user_id = :mu
                ON CONFLICT (login) DO NOTHING
            """),
            {"mu": a["max_user_id"], "login": a["login"], "ph": md5_hash},
        )

        await s.commit()

        print("✅ Сидирование завершено:")
        for table in ("roles", "ticket_statuses", "ticket_types", "ticket_priorities",
                      "ticket_sources", "point_rules", "role_limits", "addresses",
                      "departments", "notification_templates", "web_accounts"):
            row = (await s.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar()  # noqa: S608
            print(f"   {table:<22} {row}")
        print('\n🔑 Демо-доступ веб-панели: POST /api/v1/auth/login  {"login": "admin", "password": "admin"}')


if __name__ == "__main__":
    asyncio.run(seed())
