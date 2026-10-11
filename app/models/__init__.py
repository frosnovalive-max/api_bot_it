"""Регистрация всех ORM-моделей для Alembic autogenerate и приложения."""
# ruff: noqa: F401
from app.models.base import ActiveMixin, AuditColumns, SoftDeleteMixin, TimestampMixin
from app.models.gamification import (
    Penalty,
    PointRule,
    PointTransaction,
    RoleLimit,
    UserPoints,
)
from app.models.moderation import AuditLog, BlacklistEntry, Complaint, WebAccount
from app.models.notifications import (
    Notification,
    NotificationHistory,
    NotificationTemplate,
)
from app.models.references import (
    Address,
    Department,
    Role,
    TicketPriority,
    TicketSource,
    TicketStatus,
    TicketType,
)
from app.models.tickets import (
    Ticket,
    TicketAttachment,
    TicketHistory,
    TicketMessage,
)
from app.models.users import (
    AddressResponsible,
    ExecutorGroup,
    ExecutorGroupMember,
    User,
    UserDepartment,
    UserRole,
)

__all__ = [
    "Address",
    "AddressResponsible",
    "AuditLog",
    "BlacklistEntry",
    "Complaint",
    "Department",
    "ExecutorGroup",
    "ExecutorGroupMember",
    "Notification",
    "NotificationHistory",
    "NotificationTemplate",
    "Penalty",
    "PointRule",
    "PointTransaction",
    "Role",
    "RoleLimit",
    "Ticket",
    "TicketAttachment",
    "TicketHistory",
    "TicketMessage",
    "TicketPriority",
    "TicketSource",
    "TicketStatus",
    "TicketType",
    "User",
    "UserDepartment",
    "UserPoints",
    "UserRole",
    "WebAccount",
]
