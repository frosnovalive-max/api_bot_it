"""Pydantic-схемы тикетов (Request/Response DTO) с примерами для Swagger."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.users import UserShort


class TicketCreate(BaseModel):
    """POST /tickets — создание обращения. author берётся из токена."""

    type_id: uuid.UUID = Field(description="Тип обращения (справочник ticket_types)")
    title: str = Field(min_length=3, max_length=500, examples=["Не работает принтер в 212 кабинете"])
    description: str = Field(min_length=5, examples=["Принтер HP LaserJet не печатает, горит красный индикатор"])
    priority_id: uuid.UUID | None = Field(None, description="Приоритет (по умолчанию — средний)")
    source_id: uuid.UUID | None = Field(
        None, description="Источник (по умолчанию — 'web' / 'bot' в зависимости от клиента)"
    )
    address_id: uuid.UUID | None = Field(
        None, description="Адрес. Если не указан — подтягивается users.default_address_id"
    )
    cabinet: str | None = Field(None, max_length=100, description="Кабинет / аудитория", examples=["212"])


class TicketAssign(BaseModel):
    """PATCH /tickets/{id}/assign — исполнитель назначает себя (или админ назначает другого)."""

    executor_id: uuid.UUID | None = Field(
        None, description="Кого назначить. NULL = назначить себя"
    )


class TicketStatusChange(BaseModel):
    """PATCH /tickets/{id}/status — смена статуса. Закрыть может только admin."""

    status_code: str = Field(
        pattern="^(new|in_progress|done|closed|rejected|canceled|duplicate)$",
        description="Код нового статуса",
        examples=["in_progress"],
    )
    comment: str | None = Field(None, max_length=1000, examples=["Взял в работу"])


class TicketDuplicate(BaseModel):
    """POST /tickets/{id}/duplicate — признать дублем."""

    duplicate_of: uuid.UUID = Field(description="UUID оригинального тикета")
    penalty: bool = Field(True, description="Начислить штраф автору за дубль")


class TicketMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000, examples=["Проблема решена, принтер в работе"])
    is_internal: bool = Field(False, description="Внутреннее сообщение (видно только сотрудникам)")


class TicketRating(BaseModel):
    rating: int = Field(ge=1, le=5, description="Оценка качества 1–5", examples=[5])
    rating_comment: str | None = Field(None, max_length=1000, examples=["Быстро и качественно"])


class TicketHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_name: str = Field(examples=["status_id"])
    old_value: str | None = Field(None, examples=["new"])
    new_value: str | None = Field(None, examples=["in_progress"])
    changed_by: uuid.UUID
    created_at: datetime


class TicketMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author: UserShort
    message: str
    is_internal: bool
    created_at: datetime


class TicketAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    message_id: uuid.UUID | None
    file_name: str
    file_type: str | None
    file_size: int | None
    file_path: str
    uploaded_by: uuid.UUID
    created_at: datetime


class TicketBrief(BaseModel):
    """Элемент списка тикетов (для внешних клиентов отдаём ticket_number)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Внутренний UUID (для API-операций)")
    ticket_number: int = Field(description="Человекочитаемый номер", examples=[1042])
    title: str
    status_code: str = Field(examples=["new"])
    status_name: str = Field(examples=["Новый"])
    type_name: str = Field(examples=["Поломка техники"])
    priority_name: str | None = Field(None, examples=["Средний"])
    author: UserShort
    assignee: UserShort | None = None
    address_name: str | None = Field(None, examples=["Ленина 38"])
    cabinet: str | None = Field(None, examples=["212"])
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketBrief):
    description: str
    source_name: str | None = None
    closed_at: datetime | None
    closed_by: uuid.UUID | None
    duplicate_of: uuid.UUID | None
    rating: int | None = Field(None, ge=1, le=5)
    rating_comment: str | None
    rated_at: datetime | None
    assigned_at: datetime | None
    history: list[TicketHistoryOut] = Field(default_factory=list)
    messages: list[TicketMessageOut] = Field(default_factory=list)
    attachments: list[TicketAttachmentOut] = Field(default_factory=list)
