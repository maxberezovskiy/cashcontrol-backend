import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import login_limiter, password_reset_limiter
from app.crud.password_reset import crud_password_reset
from app.crud.smtp_settings import crud_smtp_settings
from app.crud.user import crud_user


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    # Лимитеры in-memory и переживают между тестами в одном процессе — чистим, чтобы
    # сброс пароля / логин не упирались в 429 из-за вызовов в соседних тестах.
    login_limiter._hits.clear()
    password_reset_limiter._hits.clear()
    yield


# ---- helpers ----

async def _register(client: AsyncClient, email: str, password: str = "password123", full_name=None):
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )


async def _login(client: AsyncClient, email: str, password: str = "password123") -> str:
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _promote(db: AsyncSession, email: str):
    user = await crud_user.get_by_email(db, email=email)
    user.is_superuser = True
    db.add(user)
    await db.flush()
    return user


async def _admin_headers(client: AsyncClient, db: AsyncSession, email: str = "admin@example.com"):
    await _register(client, email, full_name="Admin")
    await _promote(db, email)
    token = await _login(client, email)
    return {"Authorization": f"Bearer {token}"}


# ---- Роль / доступ (§2.2, 5.1) ----

@pytest.mark.asyncio
async def test_non_admin_forbidden(client: AsyncClient):
    await _register(client, "plain@example.com")
    token = await _login(client, "plain@example.com")
    r = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_no_token_unauthorized(client: AsyncClient):
    r = await client.get("/api/v1/admin/users")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_exposes_role(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    r = await client.get("/api/v1/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["is_superuser"] is True


# ---- Список / карточка / правка (§5.2) ----

@pytest.mark.asyncio
async def test_admin_lists_and_filters_users(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    await _register(client, "u1@example.com")
    r = await client.get("/api/v1/admin/users", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 2 and "items" in body
    # фильтр по роли
    r2 = await client.get("/api/v1/admin/users?role=admin", headers=headers)
    assert all(u["is_superuser"] for u in r2.json()["items"])


@pytest.mark.asyncio
async def test_admin_update_profile_and_email_conflict(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    await _register(client, "victim@example.com")
    await _register(client, "taken@example.com")
    uid = (await crud_user.get_by_email(db, email="victim@example.com")).id

    r = await client.patch(f"/api/v1/admin/users/{uid}", headers=headers, json={"full_name": "New Name"})
    assert r.status_code == 200 and r.json()["full_name"] == "New Name"

    r2 = await client.patch(f"/api/v1/admin/users/{uid}", headers=headers, json={"email": "taken@example.com"})
    assert r2.status_code == 400


# ---- Инварианты самоблокировки (§2.3) ----

@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    r = await client.post(f"/api/v1/admin/users/{me['id']}/deactivate", headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_admin_cannot_delete_self(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    r = await client.delete(f"/api/v1/admin/users/{me['id']}", headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_admin_cannot_demote_self(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    r = await client.post(f"/api/v1/admin/users/{me['id']}/role", headers=headers, json={"role": "user"})
    assert r.status_code == 409


# ---- Каскадное удаление (§12) ----

@pytest.mark.asyncio
async def test_delete_user_cascades_accounts(client: AsyncClient, db: AsyncSession):
    from app.crud.account import crud_account
    from app.schemas.account import AccountCreate

    headers = await _admin_headers(client, db)
    await _register(client, "todelete@example.com")
    victim = await crud_user.get_by_email(db, email="todelete@example.com")
    await crud_account.create_for_user(
        db, obj_in=AccountCreate(name="Wallet", account_type="cash"), user_id=victim.id
    )
    await db.flush()

    r = await client.delete(f"/api/v1/admin/users/{victim.id}", headers=headers)
    assert r.status_code == 204
    assert await crud_user.get(db, id=victim.id) is None
    assert (await crud_account.get_by_user(db, user_id=victim.id)) == []


# ---- Сброс пароля (§5.5) ----

@pytest.mark.asyncio
async def test_password_reset_request_anti_enumeration(client: AsyncClient):
    # Несуществующий email — всё равно 200 (не раскрываем наличие аккаунта).
    r = await client.post("/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_confirm_full_flow(client: AsyncClient, db: AsyncSession):
    await _register(client, "reset@example.com", password="oldpass123")
    user = await crud_user.get_by_email(db, email="reset@example.com")
    raw = await crud_password_reset.create(db, user_id=user.id, created_by=user.id, ttl_minutes=60)

    r = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": raw, "new_password": "brandnew456"},
    )
    assert r.status_code == 200
    # новый пароль работает, старый — нет
    assert (await client.post("/api/v1/auth/login", data={"username": "reset@example.com", "password": "brandnew456"})).status_code == 200
    assert (await client.post("/api/v1/auth/login", data={"username": "reset@example.com", "password": "oldpass123"})).status_code == 401


@pytest.mark.asyncio
async def test_password_reset_confirm_token_one_time(client: AsyncClient, db: AsyncSession):
    await _register(client, "once@example.com")
    user = await crud_user.get_by_email(db, email="once@example.com")
    raw = await crud_password_reset.create(db, user_id=user.id, created_by=user.id, ttl_minutes=60)
    assert (await client.post("/api/v1/auth/password-reset/confirm", json={"token": raw, "new_password": "firstchange1"})).status_code == 200
    # повторное использование того же токена
    assert (await client.post("/api/v1/auth/password-reset/confirm", json={"token": raw, "new_password": "secondchange1"})).status_code == 400


@pytest.mark.asyncio
async def test_password_reset_confirm_rejects_bad_and_short(client: AsyncClient):
    assert (await client.post("/api/v1/auth/password-reset/confirm", json={"token": "nope", "new_password": "longenough12"})).status_code == 400
    assert (await client.post("/api/v1/auth/password-reset/confirm", json={"token": "x", "new_password": "short"})).status_code == 400


@pytest.mark.asyncio
async def test_admin_reset_password_endpoint(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    await _register(client, "target@example.com")
    uid = (await crud_user.get_by_email(db, email="target@example.com")).id
    r = await client.post(f"/api/v1/admin/users/{uid}/reset-password", headers=headers)
    assert r.status_code == 200


# ---- Аудит (§4.3) ----

@pytest.mark.asyncio
async def test_admin_action_writes_audit(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    await _register(client, "audited@example.com")
    uid = (await crud_user.get_by_email(db, email="audited@example.com")).id
    await client.post(f"/api/v1/admin/users/{uid}/deactivate", headers=headers)

    r = await client.get("/api/v1/admin/audit-logs?action=user.deactivate", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(item["target_user_id"] == uid for item in body["items"])


# ---- SMTP-настройки (§5.4) ----

@pytest.mark.asyncio
async def test_smtp_defaults_and_non_admin(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    r = await client.get("/api/v1/admin/settings/smtp", headers=headers)
    assert r.status_code == 200
    assert r.json()["password_set"] is False and r.json()["enabled"] is False

    await _register(client, "plain2@example.com")
    utoken = await _login(client, "plain2@example.com")
    r2 = await client.get("/api/v1/admin/settings/smtp", headers={"Authorization": f"Bearer {utoken}"})
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_smtp_put_encrypts_and_hides_password(client: AsyncClient, db: AsyncSession):
    headers = await _admin_headers(client, db)
    payload = {"host": "smtp.example.com", "port": 587, "username": "mailer",
               "password": "s3cret-pw", "use_tls": "starttls", "from_email": "noreply@example.com",
               "enabled": True}
    r = await client.put("/api/v1/admin/settings/smtp", headers=headers, json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["password_set"] is True
    assert "password" not in body  # пароль наружу не отдаётся

    # at-rest зашифрован, но расшифровывается обратно
    cfg = await crud_smtp_settings.get(db)
    assert cfg.password_encrypted != "s3cret-pw"
    assert crud_smtp_settings.get_decrypted_password(cfg) == "s3cret-pw"

    # PUT без пароля не затирает сохранённый
    await client.put("/api/v1/admin/settings/smtp", headers=headers, json={"enabled": False})
    r2 = await client.get("/api/v1/admin/settings/smtp", headers=headers)
    assert r2.json()["password_set"] is True and r2.json()["enabled"] is False


# ---- Read-only финансы (§5.2) ----

@pytest.mark.asyncio
async def test_admin_readonly_finance(client: AsyncClient, db: AsyncSession):
    from app.crud.account import crud_account
    from app.schemas.account import AccountCreate

    headers = await _admin_headers(client, db)
    await _register(client, "finuser@example.com")
    fin = await crud_user.get_by_email(db, email="finuser@example.com")
    await crud_account.create_for_user(
        db, obj_in=AccountCreate(name="Acc", account_type="cash"), user_id=fin.id
    )
    await db.flush()

    r = await client.get(f"/api/v1/admin/users/{fin.id}/accounts", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1

    # missing user -> 404
    assert (await client.get("/api/v1/admin/users/999999/accounts", headers=headers)).status_code == 404
    # non-admin -> 403
    utoken = await _login(client, "finuser@example.com")
    assert (await client.get(f"/api/v1/admin/users/{fin.id}/accounts", headers={"Authorization": f"Bearer {utoken}"})).status_code == 403
