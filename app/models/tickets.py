"""ORM-модели тикетов: tickets, ticket_messages, ticket_attachments, ticket_history."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TimestampMixin


class Ticket(Base, SoftDeleteMixin, TimestampMixin):
    """Тикеты (обращения) технической поддержки.

    Двойная нумерация: id (UUID, внутренний) + ticket_number (bigint, внешний).
    """

    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticket_number: Mapped[int] = mapped_column(
        BigInteger, Identity(), unique=True, nullable=False
    )

    type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ticket_types.id"), nullable=False)
    status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ticket_statuses.id"), nullable=False
    )
    priority_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ticket_priorities.id"))
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ticket_sources.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    address_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("addresses.id"))
    cabinet: Mapped[str | None] = mapped_column(String(100))

    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"))

    rating: Mapped[int | None] = mapped_column(
        SmallInteger, CheckConstraint("rating >= 1 AND rating <= 5")
    )
    rating_comment: Mapped[str | None] = mapped_column(Text)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    type: Mapped["TicketType"] = relationship()  # noqa
    status: Mapped["TicketStatus"] = relationship()  # noqa
    priority: Mapped["TicketPriority | None"] = relationship()  # noqa
    source: Mapped["TicketSource"] = relationship()  # noqa
    author: Mapped["User"] = relationship(foreign_keys=[author_id])  # noqa
    address: Mapped["Address | None"] = relationship()  # noqa
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assigned_to])  # noqa
    closer: Mapped["User | None"] = relationship(foreign_keys=[closed_by])  # noqa
    original: Mapped["Ticket | None"] = relationship(remote_side=[id], foreign_keys=[duplicate_of])

    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket")
    history: Mapped[list["TicketHistory"]] = relationship(back_populates="ticket")
    attachments: Mapped[list["TicketAttachment"]] = relationship(back_populates="ticket")


class TicketMessage(Base, SoftDeleteMixin):
    """Переписка по тикету. is_internal — видно только сотрудникам."""

    __tablename__ = "ticket_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.false(), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[Ticket] = relationship(back_populates="messages")
    author: Mapped["User"] = relationship()  # noqa


class TicketAttachment(Base, SoftDeleteMixin):
    """Вложения. Файлы в хранилище, здесь — метаданные."""

    __tablename__ = "ticket_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ticket_messages.id"))
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[Ticket] = relationship(back_populates="attachments")
    uploader: Mapped["User"] = relationship()  # noqa


class TicketHistory(Base):
    """История изменений тикета: статус, приоритет, исполнитель и т. д."""

    __tablename__ = "ticket_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[Ticket] = relationship(back_populates="history")
    changer: Mapped["User"] = relationship()  # noqa
