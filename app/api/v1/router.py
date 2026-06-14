from fastapi import APIRouter

# Полностью инициализируем Base и все модели до импорта эндпоинтов: некоторые crud/email-модули
# импортируют модель напрямую, и без этого предзагрузка приводит к циклическому импорту
# (модуль модели → app.db.base → повторный импорт ещё не готовой модели).
import app.db.base  # noqa: F401, E402

from app.api.v1.endpoints import auth, users, accounts, transactions, categories, budgets, telegram, admin  # noqa: E402

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(budgets.router, prefix="/budgets", tags=["budgets"])
api_router.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
