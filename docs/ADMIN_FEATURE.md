# Постановка на разработку: Суперпользователь (Admin) — администрирование пользователей

**Проект:** CashControl · **Версия документа:** 1.1 · **Дата:** 2026-06-14
**Затрагивает репозитории:** `cashcontrol-backend`, `cashcontrol-frontend`

> История решений (v1.1): роль — бинарная `user/admin`; сброс пароля — по email-ссылке;
> объём доступа — профиль + read-only финансы; self-service «забыли пароль» — **обязателен**;
> `audit_logs` — **обязательная таблица** + доступ к ней из админ-интерфейса; почта — **Postmark**;
> удаление пользователя — **каскадное (hard delete) всех его данных, с подтверждением**.

## 1. Цель

Дать роли **admin** инструменты администрирования: просмотр списка пользователей, редактирование их
профилей, управление статусом и ролью, инициирование сброса пароля (по email-ссылке), read-only
просмотр финансовых данных пользователя для поддержки и просмотр журнала аудита админ-действий.
Обычные пользователи (`user`) сохраняют текущее поведение без изменений.

## 2. Функционально-ролевая модель

Модель — **бинарная**, на базе существующего `User.is_superuser`. Новых таблиц ролей нет; роль
выводится из флага. В API роль отдаётся строкой (`"admin"` / `"user"`) для расширяемости фронтенда,
но хранится булевым флагом.

### 2.1 Роли

| Роль | Признак | Кто это |
|------|---------|---------|
| `user` | `is_superuser = false` | Обычный пользователь. Видит только свои данные. |
| `admin` | `is_superuser = true` | Суперпользователь. Полный доступ к админ-разделу. |

### 2.2 Матрица прав (permissions matrix)

| Действие | user (свои) | user (чужие) | admin |
|---|:--:|:--:|:--:|
| Логин / refresh / `/me` | ✅ | — | ✅ |
| Self-service «забыли пароль» | ✅ | — | ✅ |
| Просмотр/правка **своего** профиля | ✅ | ❌ | ✅ |
| CRUD **своих** счетов/транзакций/бюджетов | ✅ | ❌ | ✅ (своих) |
| Список всех пользователей (поиск, пагинация) | ❌ | ❌ | ✅ |
| Карточка любого пользователя | ❌ | ❌ | ✅ |
| Правка профиля чужого юзера (email, ФИО) | ❌ | ❌ | ✅ |
| Активация / деактивация юзера | ❌ | ❌ | ✅ |
| Назначение / снятие роли admin | ❌ | ❌ | ✅ |
| Инициировать сброс пароля юзера (email) | ❌ | ❌ | ✅ |
| Удаление юзера (каскадно, с подтверждением) | ❌ | ❌ | ✅ |
| **Read-only** просмотр финансов чужого юзера | ❌ | ❌ | ✅ |
| Просмотр журнала аудита (`audit_logs`) | ❌ | ❌ | ✅ |
| Правка финансов чужого юзера | ❌ | ❌ | ❌ *(вне объёма)* |

### 2.3 Инварианты безопасности (обязательны)

1. **Защита от самоблокировки:** admin не может деактивировать, удалить или снять роль admin **с самого себя**.
2. **Защита последнего админа:** нельзя снять роль / деактивировать / удалить пользователя, если он — единственный активный admin (`count(active admins) > 1`).
3. **Сброс пароля не раскрывает пароль:** admin запускает сброс → пользователю уходит письмо со ссылкой → новый пароль задаёт сам пользователь. Admin пароль не видит и не задаёт.
4. Все админ-действия пишутся в **audit log** (см. §4.3) — обязательно.

## 3. Объём работ

**В объёме:** роль-зависимость на бэке; админ-CRUD пользователей; email-подсистема (**внешний SMTP**) +
сброс пароля по ссылке; **обязательный** self-service «забыли пароль»; read-only финансовый просмотр;
**обязательная** таблица `audit_logs` + админ-эндпоинт и UI её просмотра; админ-раздел во фронте;
бутстрап первого админа; миграции; тесты.

**Вне объёма:** правка чужих финансов; гранулярный RBAC (роли/права таблицами); 2FA; массовые
операции; экспорт.

## 4. Изменения модели данных

### 4.1 `User` (правка)
Поле `is_superuser` уже есть — схему менять не нужно. Добавляется опционально:
- `password_changed_at: datetime | null` — для будущего «сменить при следующем входе» (не блокер).

### 4.2 Новая таблица `password_reset_tokens`
| Поле | Тип | Назначение |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → users.id, index | владелец токена |
| `token_hash` | String(255), unique, index | **хэш** токена (сырой токен в БД не хранится) |
| `expires_at` | DateTime(tz) | TTL, по умолчанию 60 мин |
| `used_at` | DateTime(tz) \| null | одноразовость |
| `created_by` | FK → users.id \| null | кто инициировал (admin или сам юзер) |
| `created_at` | DateTime(tz) | |

Сырой токен: `secrets.token_urlsafe(32)`; в письмо/ссылку идёт сырой, в БД — `sha256`. При новом
сбросе старые неиспользованные токены пользователя инвалидируются.

### 4.3 Новая таблица `audit_logs` (обязательна)
| Поле | Тип | Назначение |
|---|---|---|
| `id` | PK | |
| `actor_user_id` | FK → users.id, index | кто совершил действие |
| `action` | String/Enum, index | тип действия (см. ниже) |
| `target_user_id` | FK → users.id \| null, index | над кем |
| `meta` | JSON \| null | детали (старое/новое значение и т.п.) |
| `ip` | String(45) \| null | IP инициатора |
| `created_at` | DateTime(tz), index | |

Действия (`action`): `user.update`, `user.activate`, `user.deactivate`, `user.role_change`,
`user.delete`, `user.password_reset_requested`, `auth.password_reset_completed`,
`auth.password_reset_self_requested`, `settings.smtp_update`. Запись — в той же транзакции, что и само действие.

### 4.4 Новая таблица `smtp_settings` (одна строка, конфиг почты)
Параметры SMTP задаются суперпользователем из UI и хранятся в БД (источник истины). Таблица —
single-row (например, `id=1`).
| Поле | Тип | Назначение |
|---|---|---|
| `id` | PK | всегда 1 |
| `host` | String \| null | SMTP-хост |
| `port` | Integer \| null | порт (587/465/25) |
| `username` | String \| null | аккаунт SMTP |
| `password_encrypted` | String \| null | пароль, **зашифрован at-rest** (Fernet) |
| `use_tls` | String | `starttls` \| `ssl` \| `none` |
| `from_email` | String \| null | адрес отправителя |
| `enabled` | Boolean | включена ли реальная отправка |
| `updated_by` | FK → users.id \| null | кто менял |
| `updated_at` | DateTime(tz) | |

Пароль шифруется при записи (Fernet из `cryptography`, уже в зависимостях через `python-jose`;
ключ — отдельная env `SETTINGS_ENC_KEY` или производная от `SECRET_KEY`). В API наружу пароль
**никогда** не отдаётся — только флаг `password_set: bool`.

## 5. Backend API

Новый модуль `app/api/v1/endpoints/admin.py`, подключается в `router.py` с префиксом `/admin`,
tag `admin`. Все эндпоинты защищены новой зависимостью `get_current_superuser`.

### 5.1 Новая зависимость (`app/core/dependencies.py`)
```python
async def get_current_superuser(current_user = Depends(get_current_active_user)):
    if not current_user.is_superuser:
        raise HTTPException(403, "Недостаточно прав")
    return current_user
```

### 5.2 Эндпоинты администрирования пользователей

| Метод | Путь | Назначение | Тело / параметры |
|---|---|---|---|
| `GET` | `/admin/users` | Список с поиском и пагинацией | `q`, `is_active`, `role`, `offset`, `limit`, `sort` → `{items, total}` |
| `GET` | `/admin/users/{id}` | Карточка пользователя | → `UserAdminRead` |
| `PATCH` | `/admin/users/{id}` | Правка профиля | `{email?, full_name?}` |
| `POST` | `/admin/users/{id}/activate` | Активировать | — |
| `POST` | `/admin/users/{id}/deactivate` | Деактивировать (инвариант §2.3) | — |
| `POST` | `/admin/users/{id}/role` | Сменить роль | `{role: "admin"\|"user"}` (инвариант) |
| `POST` | `/admin/users/{id}/reset-password` | Инициировать email-сброс | → `{detail}` |
| `DELETE` | `/admin/users/{id}` | Каскадно удалить пользователя и все его данные | инвариант §2.3, требует подтверждения на UI |
| `GET` | `/admin/users/{id}/accounts` | Read-only счета юзера | пагинация |
| `GET` | `/admin/users/{id}/transactions` | Read-only транзакции юзера | фильтры/пагинация |

### 5.3 Эндпоинты журнала аудита (admin)
| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/admin/audit-logs` | Список записей аудита: фильтры `actor_id`, `target_id`, `action`, `date_from`, `date_to`, пагинация `offset/limit`, sort по `created_at desc` → `{items, total}` |

### 5.4 Эндпоинты настроек SMTP (admin)
| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/admin/settings/smtp` | Текущие настройки **без пароля** (`+ password_set: bool`) |
| `PUT` | `/admin/settings/smtp` | Upsert настроек; `password` опционален (меняется только если передан), пишется зашифрованным; audit `settings.smtp_update` |
| `POST` | `/admin/settings/smtp/test` | Отправить тестовое письмо на указанный адрес — проверка до боевого использования; возвращает успех/ошибку SMTP |

### 5.5 Публичные эндпоинты сброса пароля (без авторизации)
| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/auth/password-reset/request` | **Обязательный** self-service «забыли пароль»: `{email}` → всегда `200` (анти-энумерация), при существующем активном юзере шлёт письмо |
| `POST` | `/auth/password-reset/confirm` | `{token, new_password}` → проверка хэша/TTL/used, установка пароля, инвалидация токена, audit `auth.password_reset_completed` |

Оба под rate-limit (переиспользуем `app/core/ratelimit.py`).

### 5.6 Изменения схем (`app/schemas/user.py`)
- В `UserRead` добавить `is_superuser` (или вычисляемое `role`) — чтобы `/me` отдавал роль фронту.
- Новые: `UserAdminRead` (полный: + `telegram_id`, `updated_at`, `is_superuser`, `is_active`),
  `UserAdminUpdate` (`email`, `full_name`), `RoleUpdate`, `PasswordResetRequest`,
  `PasswordResetConfirm`, `PaginatedUsers`, `AuditLogRead`, `PaginatedAuditLogs`,
  `SmtpSettingsRead` (с `password_set`, без пароля), `SmtpSettingsUpdate`, `SmtpTestRequest`
  (в `app/schemas/settings.py`).
- Роль в JWT можно положить claim'ом, но **источник истины — БД**: роль перепроверяется в
  `get_current_superuser`, иначе снятие прав не подействует до истечения токена.

### 5.7 CRUD
- `app/crud/user.py`: `search(...) -> (items, total)`, `set_active`, `set_role`, `count_active_admins`.
- `app/crud/password_reset.py`: создание/валидация/инвалидация токенов.
- `app/crud/audit_log.py`: `log(...)` и `search(...)`.
- `app/crud/smtp_settings.py`: `get()` (single-row), `upsert(...)` с шифрованием пароля,
  `get_decrypted_password()` для сервиса отправки.

## 6. Email-подсистема — внешний SMTP (настраивается из UI суперпользователя)

Почтовой инфраструктуры в проекте нет — добавляем отправку через **внешний SMTP-сервер**
(логин/пароль провайдера). Никакого SaaS-API и своих почтовых контейнеров. **Параметры SMTP
(хост, порт, аккаунт, пароль, TLS, отправитель, вкл/выкл) задаёт суперпользователь через
веб-интерфейс**, а не через env.
- **Источник истины — БД:** настройки хранятся в таблице `smtp_settings` (§4.4), редактируются через
  `GET/PUT /admin/settings/smtp` (§5.4). Env боевые SMTP-креды не содержит.
- **Шифрование пароля:** пароль хранится зашифрованным (Fernet); ключ — `SETTINGS_ENC_KEY` (env) или
  производная от `SECRET_KEY`. Наружу пароль не отдаётся (флаг `password_set`), в логи не пишется.
- **Транспорт:** SMTP по логину/паролю; асинхронная отправка через `aiosmtplib`
  (добавляется в `requirements.txt`); поддержка STARTTLS и SSL.
- **Сервис** `app/core/email.py`: на момент отправки читает актуальные настройки из БД,
  расшифровывает пароль, собирает `EmailMessage` и шлёт через `aiosmtplib` в `BackgroundTasks`.
- **Проверка из UI:** `POST /admin/settings/smtp/test` — тестовое письмо до боевого использования.
- **Состояние «выключено»:** если в `smtp_settings` `enabled=false` или настройки не заданы (свежая
  инсталляция) — письма не уходят, ссылка сброса логируется в консоль (как заглушка bot-secret).
- **env остаётся только для:** `SETTINGS_ENC_KEY` (шифрование) и `FRONTEND_BASE_URL` (сборка ссылки).
- **Шаблон:** «Сброс пароля CashControl» со ссылкой `${FRONTEND_BASE_URL}/reset-password?token=...`,
  срок действия 60 мин; инлайн-HTML + текстовая часть.
- **Анти-энумерация:** `/auth/password-reset/request` всегда отвечает `200`.
- **HTTPS-API транспорт (на случай, если провайдер режет исходящий SMTP).** Многие хостинги
  блокируют исходящие порты 25/465/587 (и даже 2525) — тогда прямой SMTP не работает. Поэтому у
  почты два транспорта, выбираемых из UI (`smtp_settings.transport` = `smtp` | `api`):
  - `smtp` — отправка через `aiosmtplib` (как описано выше);
  - `api` — отправка через **HTTPS-API провайдера по порту 443** (httpx). Поддержан **Brevo**
    (`POST https://api.brevo.com/v3/smtp/email`); поле `api_provider` расширяемо под другие.
    API-ключ хранится зашифрованным (`api_key_encrypted`, тот же Fernet), наружу — только флаг
    `api_key_set`. Поскольку 443 почти нигде не блокируется, это рабочий путь там, где SMTP закрыт.

**Поток (admin-инициированный):**
```
admin → POST /admin/users/{id}/reset-password
  → создать reset-token (хэш в БД), audit user.password_reset_requested
  → BackgroundTask: отправка письма юзеру со ссылкой через внешний SMTP
  → 200 {detail: "Письмо отправлено"}
юзер → /reset-password?token=... → вводит новый пароль
  → POST /auth/password-reset/confirm → валидация → set hashed_password
  → пометить токен used → audit auth.password_reset_completed
```

**Поток (self-service):** `POST /auth/password-reset/request {email}` → (если юзер существует и активен)
создать токен + письмо → дальше как выше.

## 7. Frontend

### 7.1 Загрузка текущего пользователя и роли (блокер)
Сейчас `auth.user` всегда `null`, `/me` не вызывается — без этого ролевой логики нет.
- Thunk `fetchMe()` → `GET /users/me`, диспатчится после логина и при инициализации приложения с токеном.
- В `authSlice`: хранить `user`, селекторы `selectCurrentUser`, `selectIsAdmin`.

### 7.2 Роутинг и навигация
- `AdminRoute` (по аналогии с `PrivateRoute`): пускает только при `is_superuser`, иначе redirect на `/`.
- В `Sidebar` секция «Администрирование» (🛡️) и подпункт «Журнал аудита» — видны только админу.
- Публичные роуты вне `PrivateRoute`: `/reset-password` (по токену) и кнопка «Забыли пароль?» на `/login`.

### 7.3 Новые страницы/компоненты
- `pages/admin/AdminUsersPage.jsx` — таблица пользователей: поиск, фильтры (статус/роль), пагинация, бейджи, действия в строке.
- `pages/admin/AdminUserDetailPage.jsx` — карточка: правка профиля (модалка по паттерну `EditTransactionModal`), активировать/деактивировать, смена роли, «Сбросить пароль» (confirm), вкладка read-only финансов.
- `pages/admin/AdminAuditLogPage.jsx` — таблица журнала аудита с фильтрами (actor/target/action/период) и пагинацией.
- `pages/admin/AdminSmtpSettingsPage.jsx` — форма настроек SMTP (хост/порт/аккаунт/пароль/TLS/отправитель/вкл), пароль — write-only (поле пустое + индикатор `password_set`), кнопка «Отправить тестовое письмо».
- `pages/ResetPasswordPage.jsx` — форма нового пароля по токену из query (react-hook-form).
- `pages/ForgotPasswordPage.jsx` (или модалка на `/login`) — ввод email для self-service сброса.
- `api/admin.js`, `store/adminSlice.js` — по существующим паттернам (`extractApiError`, async thunks).
- Confirm-диалоги для необратимых действий (деактивация / **каскадное удаление** / сброс) — переиспользовать паттерн delete-confirm из транзакций. Для удаления — явное предупреждение, что удалятся все счета/транзакции/бюджеты пользователя.

## 8. Бутстрап первого администратора

**Механизм — promote-only при старте приложения (зафиксировано).**
На старте (`app/main.py`, lifespan/startup) выполняется **идемпотентная** логика: найти пользователя
с заданным email и, если он не admin, выставить `is_superuser = True`. Если пользователя ещё нет или
он уже admin — no-op. Код безопасно выполняется при каждом запуске контейнера.

- Целевой email берётся из настройки `FIRST_SUPERUSER_EMAIL` (`app/core/config.py`, читается из env).
- **Значение по умолчанию: `berezovskiy.max@mail.ru` — этот пользователь всегда admin.**
  Даже если его роль снимут через `POST /admin/users/{id}/role`, ближайший рестарт бэкенда повысит его
  обратно — это постоянный аварийный «ключ» доступа к админке. (При необходимости список можно
  расширить до нескольких email, но по умолчанию — один.)
- **Promote-only:** пользователь должен быть уже зарегистрирован обычным путём (`/auth/register`).
  Startup-логика только повышает существующий аккаунт; создание пользователя из env — вне объёма
  (`FIRST_SUPERUSER_PASSWORD` не используется).

Регистрация и `crud_user.create` **никогда** не принимают `is_superuser` из запроса — повышение роли
возможно только этим доверенным startup-путём или штатно через админ-API уже существующим админом.

Резервные способы (только аварийно): CLI `python -m app.cli make-admin <email>` или ручной SQL
`UPDATE users SET is_superuser=true WHERE email=...`.

## 9. Миграции (Alembic)
- `password_reset_tokens` (новая таблица).
- `audit_logs` (новая таблица, обязательна).
- опц. `users.password_changed_at`.
- `is_superuser` уже в схеме — миграции не требует.

## 10. Тестирование
- **Бэкенд (pytest):** `get_current_superuser` (403 для user); инварианты §2.3 (самоблокировка, последний админ); флоу сброса (TTL истёк / used / неверный токен); self-service анти-энумерация (`200` для несуществующего email); пагинация/поиск; read-only финансы доступны только админу; **каждое админ-действие пишет запись в `audit_logs`**; фильтры `/admin/audit-logs`.
- **Email:** dev-режим (лог вместо отправки); SMTP-отправка (`aiosmtplib`) мокается; background-отправка не валит запрос.
- **Frontend:** `AdminRoute` гейтит не-админа; рендер таблиц/фильтров; reset-password и forgot-password happy path.

## 11. Декомпозиция на задачи (этапы)

| # | Этап | Состав | Оценка |
|---|---|---|---|
| 1 | **Роль на бэке** | `get_current_superuser`, `is_superuser`/`role` в `UserRead`, `/me` отдаёт роль | S |
| 2 | **Audit log (ядро)** | таблица `audit_logs` + миграция, `crud/audit_log.py`, хелпер записи | S |
| 3 | **Админ-CRUD пользователей** | `admin.py` (list/get/patch/activate/deactivate/role/delete), CRUD-методы, инварианты, запись аудита | L |
| 4 | **Эндпоинт аудита** | `GET /admin/audit-logs` + фильтры/пагинация | S |
| 5 | **Email-подсистема (внешний SMTP)** | `aiosmtplib` в deps; таблица `smtp_settings` + миграция; шифрование пароля (Fernet); `crud/smtp_settings.py`; `email.py` читает конфиг из БД; `GET/PUT/test /admin/settings/smtp`; dev-лог при `enabled=false` | L |
| 6 | **Сброс пароля** | таблица `password_reset_tokens` + миграция; `/admin/.../reset-password`; `/auth/password-reset/request` (self-service); `/auth/password-reset/confirm`; rate-limit | M |
| 7 | **Read-only финансы** | `/admin/users/{id}/accounts\|transactions` | S |
| 8 | **Бутстрап админа** | env-seed / CLI | S |
| 9 | **Frontend: ядро роли** | `fetchMe`, `selectIsAdmin`, `AdminRoute`, меню | M |
| 10 | **Frontend: админ-UI** | `AdminUsersPage`, `AdminUserDetailPage`, `AdminAuditLogPage`, `AdminSmtpSettingsPage`, `adminSlice`, `api/admin.js` | L |
| 11 | **Frontend: сброс пароля** | `ResetPasswordPage` + `ForgotPasswordPage` + публичные роуты | M |
| 12 | **Тесты + деплой** | pytest; обновить `.env.example`; прокинуть `SETTINGS_ENC_KEY`/`FRONTEND_BASE_URL`/`FIRST_SUPERUSER_EMAIL` в prod `/opt/cashcontrol/.env` (боевые SMTP-креды вводятся из UI); DEPLOY.md | M |

Рекомендуемый порядок: 1 → 2 → 3 → 4 → 9 → 10 (работающее администрирование + аудит без пароля),
затем 5 → 6 → 11 (email-сброс и self-service), 7/8/12 параллельно.

## 12. Открытые вопросы / эксплуатация
- **SMTP:** хост/порт и учётные данные (логин/пароль) внешнего SMTP-сервера + адрес отправителя
  суперпользователь вводит **из UI** (`/admin/settings/smtp`), они шифруются и хранятся в БД. Желателен
  SPF/DKIM на стороне почтового провайдера, чтобы письма не падали в спам. До первой настройки — письма
  не уходят, ссылка пишется в лог.
- **Ключ шифрования `SETTINGS_ENC_KEY`:** обязателен в проде; при его потере/смене ранее сохранённый
  SMTP-пароль расшифровать нельзя — потребуется ввести заново через UI. Хранить как секрет рядом с `SECRET_KEY`.
- **Каскадное удаление:** `DELETE /admin/users/{id}` удаляет пользователя и все связанные данные
  (`cascade="all, delete-orphan"` на `accounts/categories/budgets`, далее транзакции). Необратимо —
  обязателен confirm на UI + запись `user.delete` в аудит. Деактивацию рекомендуется делать основным
  «мягким» сценарием, hard-delete — редким.
- **Сессии после деактивации/смены пароля:** `get_current_active_user` проверяет `is_active` на каждом
  запросе, refresh — тоже; access-токен живёт до истечения (минуты). Достаточно. Опционально — версия
  токена для немедленного отзыва (вне объёма).
