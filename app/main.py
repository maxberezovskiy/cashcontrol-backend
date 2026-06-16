import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import api_router
from app.crud.user import crud_user
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("cashcontrol.bootstrap")


async def _bootstrap_superuser() -> None:
    """Promote-only бутстрап первого админа (idempotent, см. ADMIN_FEATURE.md §8).

    Находит пользователя с FIRST_SUPERUSER_EMAIL и, если он не admin, повышает.
    Если пользователя нет или он уже admin — no-op. Выполняется при каждом старте,
    поэтому даже снятая роль будет восстановлена на ближайшем рестарте.
    """
    email = (settings.FIRST_SUPERUSER_EMAIL or "").strip().lower()
    if not email:
        return
    async with AsyncSessionLocal() as db:
        user = await crud_user.get_by_email(db, email=email)
        if user and not user.is_superuser:
            user.is_superuser = True
            db.add(user)
            await db.commit()
            logger.warning("Bootstrap: пользователь %s повышен до admin", email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _bootstrap_superuser()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
def health_check():
    return {"status": "ok", "version": settings.VERSION}
