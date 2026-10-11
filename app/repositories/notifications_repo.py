"""Репозиторий очереди уведомлений (паттерн «Очереди в БД»).

Core API только создаёт записи в `notifications` (+ заглушку `pending`
в `notification_history`). Фактическую доставку во внешние каналы (MAX)
выполняет отдельное приложение — Бот/воркер, выбирая непрочитанные
уведомления через get_pending() и отмечая их доставленными.
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.notifications import Notification, NotificationHistory, NotificationTemplate


class NotificationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- Написание (Core API) ----------

    async def create_notification(
        self,
        *,
        user_id: uuid.UUID,
        message: str,
        ticket_id: uuid.UUID | None = None,
        template_code: str | None = None,
    ) -> Notification:
        """Поставить уведомление в очередь: запись в notifications + pending-запись
        в notification_history (для будущего воркера доставки)."""
        template_id = None
        if template_code:
            template_id = (
                await self.session.execute(
                    select(NotificationTemplate.id).where(
                        NotificationTemplate.code == template_code,
                        NotificationTemplate.is_active == True,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()

        notif = Notification(
            user_id=user_id,
            template_id=template_id,
            ticket_id=ticket_id,
            message=message[:10000],
            is_read=False,
        )
        self.session.add(notif)
        await self.session.flush()

        history = NotificationHistory(notification_id=notif.id, status="pending")
        self.session.add(history)
        await self.session.flush()
        return notif

    # ---------- Чтение (веб-панель / бот как REST-клиент) ----------

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        only_unread: bool = False,
    ) -> tuple[Sequence[Notification], int]:
        base = select(Notification).where(Notification.is_deleted == False)  # noqa: E712
        base = base.where(Notification.user_id == user_id)
        if only_unread:
            base = base.where(Notification.is_read == False)  # noqa: E712
        total = (
            await self.session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            (
                await self.session.execute(
                    base.options(joinedload(Notification.template))
                    .order_by(Notification.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    async def unread_count(self, user_id: uuid.UUID) -> int:
        return (
            await self.session.execute(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.is_read == False,  # noqa: E712
                    Notification.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one()

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> Notification | None:
        notif = (
            await self.session.execute(
                select(Notification).where(
                    Notification.id == notification_id,
                    Notification.user_id == user_id,
                    Notification.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if notif is None:
            return None
        notif.is_read = True
        await self.session.flush()
        return notif

    # ---------- Интерфейс для Бота/воркера доставки ----------

    async def get_pending(self, *, limit: int = 100) -> Sequence[Notification]:
        """Недоставленные уведомления (pending в истории) — выборка для воркера."""
        return (
            (
                await self.session.execute(
                    select(Notification)
                    .join(NotificationHistory, NotificationHistory.notification_id == Notification.id)
                    .where(
                        NotificationHistory.status == "pending",
                        Notification.is_deleted == False,  # noqa: E712
                    )
                    .distinct()
                    .order_by(Notification.created_at.asc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    async def update_delivery_status(
        self,
        notification_id: uuid.UUID,
        *,
        status: str,
        error_message: str | None = None,
    ) -> NotificationHistory | None:
        """Обновить статус доставки (sent/failed) — вызывается Ботом/воркером."""
        if status not in ("pending", "sent", "failed"):
            raise ValueError(f"Недопустимый статус доставки: {status}")
        hist = (
            await self.session.execute(
                select(NotificationHistory)
                .where(NotificationHistory.notification_id == notification_id)
                .order_by(NotificationHistory.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if hist is None:
            return None
        hist.status = status
        hist.error_message = error_message
        if status == "sent":
            hist.sent_at = datetime.now(timezone.utc)
        await self.session.flush()
        return hist
