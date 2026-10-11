"""Базовый CRUD-репозиторий с учётом soft-delete."""
import uuid
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Базовый репозиторий.

    * SELECT автоматически фильтрует is_deleted == False (если у модели есть это поле);
    * delete() выполняет soft-delete (UPDATE is_deleted=True, deleted_at=now()).
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- Внутреннее ----------

    @property
    def _has_soft_delete(self) -> bool:
        return hasattr(self.model, "is_deleted")

    def _base_stmt(self) -> Any:
        stmt = select(self.model)
        if self._has_soft_delete:
            stmt = stmt.where(self.model.is_deleted == False)  # noqa: E712
        return stmt

    # ---------- CRUD ----------

    async def get(self, obj_id: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(self._base_stmt().where(self.model.id == obj_id))
        return result.scalar_one_or_none()

    async def get_by(self, **filters: Any) -> ModelT | None:
        stmt = self._base_stmt()
        for k, v in filters.items():
            stmt = stmt.where(getattr(self.model, k) == v)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        order_by: str = "created_at",
        desc: bool = True,
        **filters: Any,
    ) -> Sequence[ModelT]:
        stmt = self._base_stmt()
        for k, v in filters.items():
            stmt = stmt.where(getattr(self.model, k) == v)
        col = getattr(self.model, order_by, self.model.created_at)
        stmt = stmt.order_by(col.desc() if desc else col.asc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        stmt = self._base_stmt()
        for k, v in filters.items():
            stmt = stmt.where(getattr(self.model, k) == v)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await self.session.execute(count_stmt)
        return int(result.scalar_one())

    async def create(self, **values: Any) -> ModelT:
        obj = self.model(**values)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj_id: uuid.UUID, **values: Any) -> ModelT | None:
        obj = await self.get(obj_id)
        if obj is None:
            return None
        for k, v in values.items():
            setattr(obj, k, v)
        await self.session.flush()
        return obj

    async def soft_delete(self, obj_id: uuid.UUID) -> bool:
        """Мягкое удаление: UPDATE вместо DELETE."""
        if not self._has_soft_delete:
            raise NotImplementedError(f"{self.model.__name__} не поддерживает soft-delete")
        result = await self.session.execute(
            update(self.model)
            .where(self.model.id == obj_id, self.model.is_deleted == False)  # noqa: E712
            .values(is_deleted=True, deleted_at=func.now())
        )
        return result.rowcount > 0
