"""Общие ответы/описания для Swagger: глобальные схемы ошибок, пагинация."""
from app.schemas.common import ErrorResponse

#: Глобальные описания ответов — подключаются к каждому роутеру
ERROR_400 = {
    "model": ErrorResponse,
    "description": "Некорректный запрос (данные не прошли валидацию бизнес-правил)",
    "content": {"application/json": {"example": {"detail": "Кабинет не может быть длиннее 100 символов"}}},
}
ERROR_401 = {
    "model": ErrorResponse,
    "description": "Требуется аутентификация",
    "content": {"application/json": {"example": {"detail": "Требуется Bearer токен"}}},
}
ERROR_403 = {
    "model": ErrorResponse,
    "description": "Доступ запрещён (недостаточно прав / пользователь заблокирован)",
    "content": {"application/json": {"example": {"detail": "Закрывать тикеты может только admin"}}},
}
ERROR_404 = {
    "model": ErrorResponse,
    "description": "Ресурс не найден",
    "content": {"application/json": {"example": {"detail": "Тикет не найден"}}},
}
ERROR_409 = {
    "model": ErrorResponse,
    "description": "Конфликт (нарушение уникальности)",
    "content": {"application/json": {"example": {"detail": "Код уже используется"}}},
}
ERROR_429 = {
    "model": ErrorResponse,
    "description": "Превышен лимит создания тикетов (role_limits)",
    "content": {"application/json": {"example": {"detail": "Превышен лимит тикетов в час (3)"}}},
}

COMMON_ERRORS = {400: ERROR_400, 401: ERROR_401, 403: ERROR_403, 404: ERROR_404}


def build_page(items: list, total: int, page: int, page_size: int, model_cls) -> dict:
    """Собрать словарь пагинированного ответа (Page[model])."""
    pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "items": [model_cls.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(pages, 0),
    }
