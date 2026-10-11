"""Общие Pydantic-схемы: пагинация, ошибки."""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """Базовая схема ответа (из ORM-объектов)."""

    model_config = ConfigDict(from_attributes=True)


class PaginationParams(BaseModel):
    """Параметры пагинации (используется как query-зависимость отдельно)."""

    page: int = Field(1, ge=1, description="Номер страницы, начиная с 1")
    page_size: int = Field(20, ge=1, le=100, description="Размер страницы (1–100)")


class Page(BaseModel, Generic[T]):
    """Универсальный пагинированный ответ."""

    items: list[T] = Field(description="Элементы текущей страницы")
    total: int = Field(description="Общее число элементов")
    page: int = Field(description="Текущая страница")
    page_size: int = Field(description="Размер страницы")
    pages: int = Field(description="Всего страниц")


class ErrorResponse(BaseModel):
    """Глобальная схема ошибок OpenAPI (400/403/404/409/422)."""

    detail: str = Field(description="Текст ошибки", examples=["Ресурс не найден"])


class MessageResponse(BaseModel):
    """Простое сообщение об успехе."""

    message: str = Field(examples=["Операция выполнена успешно"])
