"""Базовый класс моделей с soft-delete и таймстампами."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """Поля мягкого удаления: is_deleted + deleted_at."""

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.true(), default=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TimestampMixin:
    """created_at / updated_at."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ActiveMixin:
    """Флаг активности справочников."""

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.true(), default=True
    )


class AuditColumns(SoftDeleteMixin, TimestampMixin):
    """Набор колонок аудита для наследования моделями (не создаёт отдельной таблицы)."""
