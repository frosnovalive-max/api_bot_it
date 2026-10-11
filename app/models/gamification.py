"""ORM-модели геймификации: point_rules, user_points, point_transactions, penalties, role_limits."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import ActiveMixin


class PointRule(Base, ActiveMixin):
    """Правила начисления/списания баллов. amount > 0 — начисление, < 0 — списание."""

    __tablename__ = "point_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"))
    reset_interval_days: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    role: Mapped["Role | None"] = relationship()  # noqa


class UserPoints(Base):
    """Текущий баланс баллов пользователя (может быть отрицательным при штрафах)."""

    __tablename__ = "user_points"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    last_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="points")  # noqa


class PointTransaction(Base):
    """История всех начислений и списаний баллов."""

    __tablename__ = "point_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("point_rules.id"))
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"))
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    performed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa
    performer: Mapped["User"] = relationship(foreign_keys=[performed_by])  # noqa
    rule: Mapped["PointRule | None"] = relationship()  # noqa


class Penalty(Base, ActiveMixin):
    """Штрафы (дубли, спам и т. д.). amount — отрицательное значение."""

    __tablename__ = "penalties"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa


class RoleLimit(Base, ActiveMixin):
    """Ограничения на создание тикетов по ролям."""

    __tablename__ = "role_limits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), unique=True, nullable=False
    )
    max_tickets_per_hour: Mapped[int | None] = mapped_column(Integer)
    max_tickets_per_day: Mapped[int | None] = mapped_column(Integer)
    min_rating: Mapped[int | None] = mapped_column(Integer)
    require_moderation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.false(), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    role: Mapped["Role"] = relationship(back_populates="limit")  # noqa
