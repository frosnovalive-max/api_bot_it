"""Pydantic-схемы геймификации: баллы, транзакции, рейтинг."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.users import UserShort


class PointBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    balance: int = Field(description="Текущий баланс (может быть отрицательным при штрафах)", examples=[35])
    rating: int = Field(0, description="Рейтинг пользователя", examples=[12])
    last_reset_at: datetime | None = None


class PointTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    rule_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    amount: int = Field(description="> 0 начисление, < 0 списание", examples=[-10])
    reason: str = Field(examples=["Списание за создание тикета #1042"])
    performed_by: uuid.UUID
    created_at: datetime


class PointsAdjust(BaseModel):
    """POST /points/adjust — ручная корректировка баллов администратором."""

    user_id: uuid.UUID = Field(description="Кому скорректировать баллы")
    amount: int = Field(
        description="Изменение баланса (> 0 начисление, < 0 списание), не может быть 0",
        ne=0,
        ge=-10000,
        le=10000,
        examples=[15],
    )
    reason: str = Field(min_length=3, max_length=500, examples=["Бонус за быстрое решение"])


class RatingEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int = Field(description="Место в рейтинге", examples=[1])
    user: UserShort
    points_balance: int = Field(0, examples=[120])


class PointRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str = Field(examples=["ticket_create"])
    name: str = Field(examples=["Создание тикета"])
    amount: int = Field(-10, examples=[-10])
    role_id: uuid.UUID | None
    reset_interval_days: int | None
    is_active: bool
