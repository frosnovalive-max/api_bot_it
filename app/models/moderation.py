"""ORM-модели модерации и веб-панели: blacklist, complaints, audit_log, web_accounts."""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import SoftDeleteMixin


class BlacklistEntry(Base):
    """Чёрный список пользователей. expires_at NULL = бессрочная блокировка."""

    __tablename__ = "blacklist"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    blocked_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.true(), default=True
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa
    blocker: Mapped["User"] = relationship(foreign_keys=[blocked_by])  # noqa


class Complaint(Base, SoftDeleteMixin):
    """Жалобы сотрудников на пользователей (спам, некорректные обращения)."""

    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    complainant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="open",
        default="open",
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("status IN ('open','reviewed','resolved','dismissed')", name="ck_complaints_status"),
    )

    complainant: Mapped["User"] = relationship(foreign_keys=[complainant_id])  # noqa
    target: Mapped["User"] = relationship(foreign_keys=[target_user_id])  # noqa


class AuditLog(Base):
    """Аудит действий в веб-панели: login, view, create, update, delete, assign, close и т. д."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User | None"] = relationship()  # noqa


class WebAccount(Base, SoftDeleteMixin):
    """Аккаунты веб-панели (логин/пароль). password_hash: легаси MD5 → bcrypt при первом входе."""

    __tablename__ = "web_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    login: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.true(), default=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()  # noqa
