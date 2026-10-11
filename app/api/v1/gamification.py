"""Эндпоинты геймификации: баланс, история транзакций, ручная корректировка, топ рейтинга."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.api.v1.common import ERROR_403, ERROR_404
from app.core.database import get_db
from app.repositories.misc_repos import ModerationRepository, PointsRepository
from app.repositories.users_repo import UserRepository
from app.schemas.gamification import (
    PointBalanceOut,
    PointTransactionOut,
    PointsAdjust,
    RatingEntry,
)
from app.schemas.users import UserShort
from app.services.points_service import PointsService

router = APIRouter(tags=["Gamification"])


@router.get(
    "/users/{id}/points",
    response_model=dict,
    summary="Баланс и история баллов пользователя",
    description=(
        "Возвращает текущий баланс (`balance`), рейтинг и пагинированную историю транзакций. "
        "Владелец или сотрудник/админ может смотреть; для остальных — 403."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def get_points(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    urepo = UserRepository(session)
    user = await urepo.get(id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    roles = urepo.role_codes_of(current)
    from app.core.security import is_staff

    if current.id != id and not is_staff(roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Чужой баланс могут смотреть только сотрудники")

    repo = PointsRepository(session)
    balance = await repo.get_or_create(id)
    txs, total = await repo.list_transactions(id, offset=(page - 1) * page_size, limit=page_size)
    return {
        "balance": PointBalanceOut.model_validate(
            {"user_id": id, "balance": balance.balance, "rating": user.rating, "last_reset_at": balance.last_reset_at}
        ),
        "transactions": {
            "items": [PointTransactionOut.model_validate(t) for t in txs],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        },
    }


@router.post(
    "/points/adjust",
    response_model=PointTransactionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ручная корректировка баллов (админ)",
    description=(
        "Начисление (>0) или списание (<0) баллов конкретному пользователю. "
        "Создаёт `point_transaction`, обновляет `user_points.balance` и пишет `audit_log`. "
        "Только администраторы."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def adjust_points(
    payload: PointsAdjust,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[object, Depends(require_admin)],
):
    urepo = UserRepository(session)
    target = await urepo.get(payload.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")

    svc = PointsService(session)
    _, tx = await svc.apply_points(
        user_id=payload.user_id,
        amount=payload.amount,
        reason=payload.reason,
        performed_by=admin.id,
    )
    await ModerationRepository(session).write_audit(
        user_id=admin.id,
        action="points_adjust",
        entity_type="user_points",
        entity_id=payload.user_id,
        new_values={"amount": payload.amount, "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
    )
    return tx


@router.get(
    "/rating/top",
    response_model=list[RatingEntry],
    summary="Топ пользователей по рейтингу",
    description=(
        "Рейтинг = баланс баллов + users.rating. Возвращает верх N строк таблицы лидеров "
        "(по умолчанию 20). Доступен всем аутентифицированным."
    ),
)
async def rating_top(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_current_user)],
    limit: int = Query(20, ge=1, le=100),
):
    rows = await PointsRepository(session).top_rating(limit=limit)
    result = []
    for rank, (user, balance) in enumerate(rows, start=1):
        entry = RatingEntry(rank=rank, user=UserShort.model_validate(user), points_balance=balance)
        result.append(entry)
    return result
