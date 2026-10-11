"""ORM-модели справочников: roles, departments, addresses, ticket_types/statuses/priorities/sources."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import ActiveMixin, SoftDeleteMixin, TimestampMixin


class Role(Base, ActiveMixin):
    """Справочник ролей: admin, support, teacher, staff, student."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="role")  # noqa
    limit: Mapped["RoleLimit | None"] = relationship(back_populates="role", uselist=False)  # noqa


class Department(Base, ActiveMixin, SoftDeleteMixin, TimestampMixin):
    """Подразделения учреждения (иерархия через parent_id)."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id")
    )

    parent: Mapped["Department | None"] = relationship(remote_side=[id], backref="children")


class Address(Base, ActiveMixin, SoftDeleteMixin, TimestampMixin):
    """Адреса (корпуса) колледжа. Фиксированные: 6 шт."""

    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_address: Mapped[str | None] = mapped_column(Text)


class TicketType(Base, ActiveMixin):
    """Типы обращений: поломка, запрос доступа, картридж, оборудование."""

    __tablename__ = "ticket_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketStatus(Base, ActiveMixin):
    """Статусы: новый, в работе, закрыт, отклонён, отменён, дубль."""

    __tablename__ = "ticket_statuses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketPriority(Base, ActiveMixin):
    """Приоритеты обращений. weight: больше = выше приоритет."""

    __tablename__ = "ticket_priorities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0", default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketSource(Base, ActiveMixin):
    """Источники: бот, личное обращение."""

    __tablename__ = "ticket_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
