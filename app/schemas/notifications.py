"""Pydantic-схемы очереди уведомлений (паттерн «Очереди в БД»).

Core API только формирует уведомления; доставка во внешние каналы (MAX) —
зона ответственности отдельного приложения (Бота/воркера).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    user_id: uuid.UUID
    ticket_id: uuid.UUID | None = Field(None, examples=["7c9e6679-7425-40de-944b-e07fc1f90ae7"])
    template_code: str | None = Field(None, examples=["ticket_received"])
    message: str = Field(examples=["Ваша заявка #1042 принята и ожидает исполнителя."])
    is_read: bool = False
    created_at: datetime


class DeliveryStatusUpdate(BaseModel):
    """PATCH /notifications/{id}/delivery-status — отчёт Бота о фактической доставке."""

    status: str = Field(
        pattern="^(sent|failed)$",
        description="Итог доставки уведомления во внешний канал (MAX)",
        examples=["sent"],
    )
    error_message: str | None = Field(
        None, max_length=2000, description="Текст ошибки, если status=failed", examples=[None]
    )
