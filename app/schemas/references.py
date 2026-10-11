"""Pydantic-схемы справочников (Request/Response DTO) с примерами для Swagger."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

USER_EXAMPLE_REF = {"$ref": "#/components/examples/UserShort"}


class RefCreate(BaseModel):
    """Базовая схема создания справочника с кодом."""

    code: str = Field(max_length=50, description="Уникальный код", examples=["broken"])
    name: str = Field(max_length=255, description="Название", examples=["Поломка техники"])
    description: str | None = Field(None, description="Описание", examples=["Неисправность оборудования"])
    is_active: bool = Field(True, description="Признак активности")


class RefUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class RefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="UUID записи", examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    code: str = Field(examples=["broken"])
    name: str = Field(examples=["Поломка техники"])
    description: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


class AddressCreate(BaseModel):
    name: str = Field(max_length=255, description="Короткое название (улица корпуса)", examples=["Ленина 38"])
    full_address: str | None = Field(
        None, description="Полный адрес", examples=["г. Примеровск, ул. Ленина, д. 38"]
    )
    is_active: bool = True


class AddressUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    full_address: str | None = None
    is_active: bool | None = None


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str = Field(examples=["Ленина 38"])
    full_address: str | None = Field(None, examples=["г. Примеровск, ул. Ленина, д. 38"])
    is_active: bool


class PriorityOut(RefOut):
    weight: int = Field(0, description="Вес сортировки: больше = выше приоритет", examples=[3])


class RoleCreate(BaseModel):
    code: str = Field(max_length=50, examples=["support"])
    name: str = Field(max_length=255, examples=["Служба поддержки"])
    description: str | None = None
    is_active: bool = True


class RoleUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str = Field(examples=["support"])
    name: str = Field(examples=["Служба поддержки"])
    description: str | None = None
    is_active: bool = True
