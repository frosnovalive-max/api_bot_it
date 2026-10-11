"""Pydantic-схемы интеграции с MAX API (вебхуки, отправка сообщений, профили)."""
from typing import Any

from pydantic import BaseModel, Field


class MaxWebhookPayload(BaseModel):
    """POST /integrations/max/webhooks — событие из MAX (упрощённая схема по dev.max.ru/docs)."""

    event_type: str = Field(
        pattern="^(user_created|user_updated|message_created|message_updated|callback)$",
        description="Тип события MAX",
        examples=["user_updated"],
    )
    user: dict[str, Any] | None = Field(
        None,
        description="Сырой профиль пользователя MAX (user_id, name, first_name, username, is_bot, "
        "last_activity_time)",
        examples=[
            {
                "user_id": 123456789,
                "name": "Петров",
                "first_name": "Иван",
                "username": "ivan_petrov",
                "is_bot": False,
                "last_activity_time": 1734987654321,
            }
        ],
    )
    payload: dict[str, Any] | None = Field(None, description="Дополнительные данные события")


class MaxSendMessageRequest(BaseModel):
    """POST /integrations/max/send-message — отправка текста/кнопок пользователю в MAX."""

    max_user_id: int = Field(description="Получатель — внешний ID пользователя MAX", examples=[123456789])
    text: str = Field(min_length=1, max_length=4000, examples=["Ваш тикет №1042 взят в работу"])
    buttons: list[dict[str, Any]] | None = Field(
        None,
        description="Кнопки (inline keyboard) по формату MAX API: [{'text': ..., 'link'/'payload': ...}]",
        examples=[[{"text": "Открыть тикет", "link": "https://panel.example.ru/tickets/1042"}]],
    )
    disable_notification: bool = Field(False, description="Без звукового уведомления")


class MaxSendMessageResponse(BaseModel):
    sent: bool = Field(examples=[True])
    message_id: str | None = Field(None, description="ID сообщения в MAX", examples=["msg_987654"])
    detail: str | None = None


class MaxWebhookResult(BaseModel):
    """Результат обработки вебхука MAX."""

    processed: bool = Field(examples=[True])
    action: str = Field(description="Что сделано", examples=["user_updated"])
    user_db_id: str | None = Field(None, examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])


class MaxProfileResponse(BaseModel):
    """Прокси-ответ профиля из MAX API."""

    found_in_db: bool = Field(True, description="Есть ли пользователь в нашей БД")
    max_user_id: int = Field(examples=[123456789])
    profile: dict[str, Any] | None = Field(
        None,
        description="Сырой профиль из MAX API",
        examples=[
            {
                "user_id": 123456789,
                "name": "Петров",
                "first_name": "Иван",
                "username": "ivan_petrov",
                "is_bot": False,
            }
        ],
    )
