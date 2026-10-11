"""Pydantic-схемы пользователей, веб-аккаунтов (JWT) и модерации."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    max_user_id: int | None = Field(None, description="Внешний ID из MAX API", examples=[123456789])
    first_name: str | None = Field(None, examples=["Иван"])
    name: str | None = Field(None, description="Фамилия / отображаемое имя", examples=["Петров"])
    username: str | None = Field(None, examples=["ivan_petrov"])
    rating: int = Field(0, examples=[12])


class UserOut(UserShort):
    is_bot: bool = False
    last_activity_time: int | None = Field(None, description="Unix timestamp (мс)", examples=[1734987654321])
    default_address_id: uuid.UUID | None = None
    is_active: bool = True
    is_blocked: bool = False
    block_reason: str | None = None
    blocked_at: datetime | None = None
    roles: list[str] = Field(default_factory=list, description="Коды ролей", examples=[["student"]])
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserUpdate(BaseModel):
    """Обновление пользователя (админ/бот-синхронизация)."""

    first_name: str | None = Field(None, max_length=255)
    name: str | None = Field(None, max_length=255)
    username: str | None = Field(None, max_length=255)
    default_address_id: uuid.UUID | None = None
    is_active: bool | None = None
    role_codes: list[str] | None = Field(
        None, description="Задать набор ролей (коды)", examples=[["student"]]
    )


class BlockRequest(BaseModel):
    """PATCH /users/{id}/block — блокировка/разблокировка."""

    is_blocked: bool = Field(True, description="True — заблокировать, False — разблокировать")
    reason: str | None = Field(
        "Нарушение правил", max_length=1000, description="Причина блокировки (для blacklist)"
    )
    expires_at: datetime | None = Field(
        None, description="Срок блокировки. NULL = бессрочно"
    )


class LoginRequest(BaseModel):
    """Аутентификация веб-панели через web_accounts."""

    login: str = Field(min_length=1, max_length=255, examples=["admin"])
    password: str = Field(min_length=1, max_length=255, examples=["s3cret!"])


class TokenResponse(BaseModel):
    access_token: str = Field(examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."])
    token_type: str = Field("bearer", examples=["bearer"])
    user: UserOut


class ComplaintCreate(BaseModel):
    target_user_id: uuid.UUID = Field(description="На кого жалоба")
    ticket_id: uuid.UUID | None = Field(None, description="Связанный тикет (опционально)")
    reason: str = Field(min_length=5, max_length=2000, examples=["Спам в чате поддержки"])


class ComplaintReview(BaseModel):
    status: str = Field(pattern="^(open|reviewed|resolved|dismissed)$", examples=["resolved"])
    resolution_note: str | None = Field(None, examples=["Пользователь предупреждён"])


class ComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    complainant_id: uuid.UUID
    target_user_id: uuid.UUID
    ticket_id: uuid.UUID | None
    reason: str
    status: str = Field(examples=["open"])
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    resolution_note: str | None
    created_at: datetime


class UserProfileSyncRequest(BaseModel):
    """PUT /users/by-max-id/{max_user_id}/profile — синхронизация профиля из MAX.

    Вызывается Ботом (сервисный X-API-Key). API НЕ ходит в MAX сам: бот получает
    профиль из MAX API и перекладывает его сюда. Поле raw_profile хранится как
    есть, без строгой валидации.
    """

    first_name: str | None = Field(None, max_length=255, examples=["Иван"])
    name: str | None = Field(None, max_length=255, description="Фамилия / отображаемое имя", examples=["Петров"])
    username: str | None = Field(None, max_length=255, examples=["ivan_petrov"])
    is_bot: bool = Field(False, examples=[False])
    last_activity_time: int | None = Field(
        None, description="Unix timestamp (мс) последней активности", examples=[1734987654321]
    )
    raw_profile: dict | None = Field(
        None,
        description="Сырой JSON-ответ профиля из MAX API (хранится без жёсткой валидации)",
        examples=[{"user_id": 123456789, "name": "Петров", "first_name": "Иван", "username": "ivan_petrov"}],
    )
    default_address_id: uuid.UUID | None = None
