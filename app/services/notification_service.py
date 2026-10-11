"""Сервис очереди уведомлений (паттерн «Очереди в БД»).

Core API НЕ общается с мессенджером MAX. При наступлении бизнес-события
(создан тикет, назначен исполнитель, сменён статус, начислены/списаны баллы)
сервис только создаёт запись в таблице `notifications` (+ pending-запись в
`notification_history`). Фактическую доставку текста в MAX выполняет
отдельное приложение — Бот, забирая очередь через REST-эндпоинты
/notifications или обновляя профиль пользователя по max_user_id.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.notifications_repo import NotificationsRepository


class NotificationQueueService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationsRepository(session)

    async def notify(
        self,
        *,
        user_id: uuid.UUID,
        message: str,
        ticket_id: uuid.UUID | None = None,
        template_code: str | None = None,
    ) -> None:
        """Поставить уведомление в очередь (без доставки наружу)."""
        await self.repo.create_notification(
            user_id=user_id, message=message, ticket_id=ticket_id, template_code=template_code
        )

    # ---------- Высокоуровневые события тикета ----------

    async def ticket_created(self, *, author_id: uuid.UUID, ticket_id: uuid.UUID, ticket_number: int) -> None:
        await self.notify(
            user_id=author_id,
            ticket_id=ticket_id,
            template_code="ticket_received",
            message=f"Ваша заявка #{ticket_number} принята и ожидает исполнителя.",
        )

    async def ticket_assigned(
        self, *, executor_id: uuid.UUID, ticket_id: uuid.UUID, ticket_number: int, title: str
    ) -> None:
        await self.notify(
            user_id=executor_id,
            ticket_id=ticket_id,
            template_code="ticket_assigned",
            message=f"Вам назначена заявка #{ticket_number}: {title}",
        )

    async def ticket_status_changed(
        self, *, user_id: uuid.UUID, ticket_id: uuid.UUID, ticket_number: int, old_status: str, new_status: str
    ) -> None:
        await self.notify(
            user_id=user_id,
            ticket_id=ticket_id,
            template_code="ticket_status_changed",
            message=f"Статус заявки #{ticket_number} изменён: {old_status} → {new_status}.",
        )

    async def ticket_duplicate(
        self, *, user_id: uuid.UUID, ticket_id: uuid.UUID, ticket_number: int, original_number: int
    ) -> None:
        await self.notify(
            user_id=user_id,
            ticket_id=ticket_id,
            template_code="ticket_duplicate",
            message=(
                f"Заявка #{ticket_number} признана дублем заявки #{original_number}. "
                f"Начислен штраф за дубль."
            ),
        )

    async def points_changed(
        self, *, user_id: uuid.UUID, amount: int, reason: str, balance: int, ticket_id: uuid.UUID | None = None
    ) -> None:
        sign = "начислено" if amount > 0 else "списано"
        await self.notify(
            user_id=user_id,
            ticket_id=ticket_id,
            template_code="points_changed",
            message=f"{sign.capitalize()} {abs(amount)} баллов. Причина: {reason}. Текущий баланс: {balance}.",
        )
