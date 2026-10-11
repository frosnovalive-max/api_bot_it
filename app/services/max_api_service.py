"""HTTP-клиент для MAX API (документация: https://dev.max.ru/docs).

Используемые методы MAX IM Bot API:
  * GET  /v3/users?user_id={id}            — получение профиля пользователя;
  * POST /v3/messages?user_id={id}         — отправка сообщения (text + attachments: inline_keyboard);
Запросы выполняются с заголовком авторизации: Authorization: Access token <BOT_TOKEN>.
"""
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MaxApiError(Exception):
    """Ошибка вызова MAX API."""

    def __init__(self, status_code: int | None, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"MAX API error {status_code}: {detail}")


class MaxApiService:
    """Асинхронный клиент MAX API. Один экземпляр переиспользует пул соединений."""

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or settings.max_api_base_url).rstrip("/")
        self.token = token or settings.max_api_token

    # ---------- Внутреннее ----------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Access token {self.token}", "Content-Type": "application/json"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.request(
                    method, url, headers=self._headers(), params=params, json=json_body
                )
        except httpx.HTTPError as exc:
            logger.error("MAX API network error: %s", exc)
            raise MaxApiError(None, f"network error: {exc}") from exc

        if resp.status_code >= 400:
            raise MaxApiError(resp.status_code, resp.text[:500])
        if not resp.content:
            return {}
        return resp.json()

    # ---------- Публичные методы ----------

    async def get_user(self, user_id: int) -> dict[str, Any]:
        """GET /v3/users?user_id=... — профиль пользователя MAX."""
        return await self._request("GET", "/users", params={"user_id": user_id})

    async def send_message(
        self,
        user_id: int,
        text: str,
        *,
        buttons: list[dict[str, Any]] | None = None,
        disable_notification: bool = False,
    ) -> dict[str, Any]:
        """POST /v3/messages?user_id=... — текст + опциональные inline-кнопки.

        Формат кнопок (по dev.max.ru/docs): [{"text": "...", "link": "..."} или
        {"text": "...", "payload": "..."}].
        """
        body: dict[str, Any] = {
            "text": text,
            "disable_notification": disable_notification,
        }
        if buttons:
            keyboard_buttons = []
            for b in buttons:
                btn: dict[str, Any] = {"type": "button"}
                data: dict[str, Any] = {"text": b.get("text", "")}
                if "link" in b:
                    data["link"] = b["link"]
                if "payload" in b:
                    data["payload"] = b["payload"]
                btn["data"] = data
                keyboard_buttons.append(btn)
            body["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": [keyboard_buttons]}}]

        return await self._request("POST", "/messages", params={"user_id": user_id}, json_body=body)
