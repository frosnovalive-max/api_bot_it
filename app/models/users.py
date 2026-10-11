"""ORM-модели пользователей: users, user_roles, user_departments и связанные таблицы."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,

    text,)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import ActiveMixin, SoftDeleteMixin, TimestampMixin


class User(Base, SoftDeleteMixin, TimestampMixin):
    """Все пользователи системы (заявители и сотрудники). Данные синхронизируются из MAX API."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )

    # Данные из MAX API
    max_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)
    last_activity_time: Mapped[int | None] = mapped_column(BigInteger)
    raw_profile: Mapped[dict | None] = mapped_column(JSONB)

    default_address_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id")
    )

    # Статус / блокировка
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)
    block_reason: Mapped[str | None] = mapped_column(Text)
    blocked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Геймификация
    rating: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)

    default_address: Mapped["Address"] = relationship(foreign_keys=[default_address_id])  # noqa
    roles_link: Mapped[list["UserRole"]] = relationship(
        back_populates="user", foreign_keys="UserRole.user_id"
    )
    departments_link: Mapped[list["UserDepartment"]] = relationship(back_populates="user")
    points: Mapped["UserPoints | None"] = relationship(back_populates="user", uselist=False)  # noqa


class UserRole(Base, ActiveMixin):
    """Ассоциативная таблица пользователь ↔ роль (многие-ко-многим)."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="roles_link", foreign_keys=[user_id])
    role: Mapped["Role"] = relationship(back_populates="user_roles")  # noqa


class UserDepartment(Base, ActiveMixin):
    """Привязка пользователей к подразделениям."""

    __tablename__ = "user_departments"
    __table_args__ = (UniqueConstraint("user_id", "department_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="departments_link")
    department: Mapped["Department"] = relationship()  # noqa


class ExecutorGroup(Base, ActiveMixin, SoftDeleteMixin, TimestampMixin):
    """Группы исполнителей (сетевая, оборудование, 1С и т. д.)."""

    __tablename__ = "executor_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class ExecutorGroupMember(Base, ActiveMixin):
    """Состав групп исполнителей."""

    __tablename__ = "executor_group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("executor_groups.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    group: Mapped[ExecutorGroup] = relationship()
    user: Mapped[User] = relationship()


class AddressResponsible(Base, ActiveMixin):
    """Ответственные по адресам. История через valid_from / valid_to (NULL = актуально)."""

    __tablename__ = "address_responsibles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    address_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("executor_groups.id"))
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    address: Mapped["Address"] = relationship()  # noqa
    user: Mapped[User] = relationship()
