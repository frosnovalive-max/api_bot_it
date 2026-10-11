"""Репозиторий пользователей: поиск по max_user_id, роли, пагинация с фильтрами."""
import uuid
from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.references import Role
from app.models.users import User, UserRole
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_with_roles(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            self._base_stmt()
            .where(User.id == user_id)
            .options(selectinload(User.roles_link).selectinload(UserRole.role))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_max_id(self, max_user_id: int) -> User | None:
        stmt = (
            self._base_stmt()
            .where(User.max_user_id == max_user_id)
            .options(selectinload(User.roles_link).selectinload(UserRole.role))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        query: str | None = None,
        role_code: str | None = None,
        is_blocked: bool | None = None,
        address_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[User], int]:
        """Пагинированный поиск с фильтрами. Возвращает (items, total)."""
        stmt = self._base_stmt().options(
            selectinload(User.roles_link).selectinload(UserRole.role)
        )
        count_stmt = select(func.count()).select_from(User).where(User.is_deleted == False)  # noqa: E712

        if query:
            like = f"%{query}%"
            cond = or_(
                User.first_name.ilike(like),
                User.name.ilike(like),
                User.username.ilike(like),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        if is_blocked is not None:
            stmt = stmt.where(User.is_blocked == is_blocked)
            count_stmt = count_stmt.where(User.is_blocked == is_blocked)
        if address_id:
            stmt = stmt.where(User.default_address_id == address_id)
            count_stmt = count_stmt.where(User.default_address_id == address_id)
        if role_code:
            role_cond = User.roles_link.any(
                UserRole.role.has(Role.code == role_code) & (UserRole.is_active == True)  # noqa: E712
            )
            stmt = stmt.where(role_cond)
            count_stmt = count_stmt.where(role_cond)

        stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
        items = (await self.session.execute(stmt)).scalars().all()
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return items, total

    async def set_roles(self, user: User, role_codes: list[str]) -> None:
        """Полностью переопределить активные роли пользователя."""
        roles = (
            (
                await self.session.execute(
                    select(Role).where(Role.code.in_(role_codes), Role.is_active == True)  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        existing = {ur.role_id: ur for ur in user.roles_link}
        wanted = {r.id for r in roles}
        for role in roles:
            if role.id not in existing:
                self.session.add(UserRole(user_id=user.id, role_id=role.id))
        for role_id, link in existing.items():
            link.is_active = role_id in wanted
        await self.session.flush()

    @staticmethod
    def role_codes_of(user: User) -> set[str]:
        """Коды активных ролей загруженного пользователя."""
        return {
            ur.role.code for ur in user.roles_link if ur.is_active and ur.role and ur.role.is_active
        }
