# Тест-кейсы: Суперпользователь (Admin) — Фазы A–C

Краткий чек-лист ручной проверки. Покрывает бэкенд Фаз A (роль), B (админ-CRUD + аудит),
C (SMTP из UI + сброс пароля). Спецификация: [ADMIN_FEATURE.md](ADMIN_FEATURE.md).

## Предусловия

```bash
# Поднять стек
docker compose up -d db backend
curl -s http://localhost:8000/health        # -> {"status":"ok",...}
```

Назначение первого админа пока — вручную через SQL (бутстрап = Фаза D):

```bash
API=http://localhost:8000/api/v1
# Регистрируем будущего админа и обычного юзера
curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"OldPass123","full_name":"Admin"}'
curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"OldPass123","full_name":"User"}'
# Повышаем до admin
docker compose exec -T db psql -U postgres -d cashcontrol \
  -c "UPDATE users SET is_superuser=true WHERE email='admin@example.com';"
# Токены
ATOK=$(curl -s -X POST $API/auth/login -d 'username=admin@example.com&password=OldPass123' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
UTOK=$(curl -s -X POST $API/auth/login -d 'username=user@example.com&password=OldPass123' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AH="Authorization: Bearer $ATOK"; UH="Authorization: Bearer $UTOK"
```

## Фаза A — роль

| # | Шаг | Ожидаемо |
|---|---|---|
| A1 | `GET /users/me` с `$AH` | `200`, поле `"is_superuser": true` |
| A2 | `GET /users/me` с `$UH` | `200`, `"is_superuser": false` |
| A3 | `GET /admin/users` с `$UH` (не админ) | `403` «Недостаточно прав» |
| A4 | `GET /admin/users` без токена | `401` |

```bash
curl -s $API/users/me -H "$AH"
curl -s -o /dev/null -w "%{http_code}\n" $API/admin/users -H "$UH"   # 403
```

## Фаза B — админ-CRUD пользователей + аудит

| # | Шаг | Ожидаемо |
|---|---|---|
| B1 | `GET /admin/users?q=user&limit=50` | `200`, `{items, total}`, фильтр по email/ФИО работает |
| B2 | `GET /admin/users?role=admin` / `?is_active=true` | фильтрация по роли/статусу |
| B3 | `GET /admin/users/{id}` | `200`, карточка `UserAdminRead` (с `updated_at`, `telegram_id`) |
| B4 | `PATCH /admin/users/{id}` `{"full_name":"X"}` | `200`, профиль обновлён, аудит `user.update` |
| B5 | `PATCH` на занятый чужой email | `400` «Email already registered» |
| B6 | `POST /admin/users/{id}/deactivate` (чужой) | `200`, `is_active=false`, аудит `user.deactivate` |
| B7 | `POST /admin/users/{id}/activate` | `200`, `is_active=true` |
| B8 | `POST /admin/users/{id}/role` `{"role":"admin"}` | `200`, аудит `user.role_change` |
| B9 | Деактивировать/удалить/снять роль с **самого себя** | `409` (защита от самоблокировки) |
| B10 | Снять роль/деактивировать **последнего** активного админа | `409` (защита последнего админа) |
| B11 | `DELETE /admin/users/{id}` (чужой) | `204`, юзер и его счета/транзакции/бюджеты удалены каскадно, аудит `user.delete` (email/id в `meta`) |
| B12 | `GET /admin/audit-logs?action=user.delete` | `200`, запись присутствует; фильтры `actor_id/target_id/action/date_from/date_to` работают |

```bash
TID=$(curl -s "$API/admin/users?q=user@example.com" -H "$AH" | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
curl -s -X POST $API/admin/users/$TID/deactivate -H "$AH" | python3 -m json.tool
AID=$(curl -s $API/users/me -H "$AH" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -o /dev/null -w "self-deactivate: %{http_code}\n" -X POST $API/admin/users/$AID/deactivate -H "$AH"  # 409
curl -s "$API/admin/audit-logs?limit=5" -H "$AH" | python3 -m json.tool
```

## Фаза C — SMTP из UI + сброс пароля

### SMTP-настройки (только админ)

| # | Шаг | Ожидаемо |
|---|---|---|
| C1 | `GET /admin/settings/smtp` (первый раз) | `200`, дефолты, `"password_set": false`, пароль не возвращается |
| C2 | `PUT /admin/settings/smtp` с `host/port/username/password/use_tls/from_email/enabled` | `200`, `"password_set": true`, поля `password` в ответе **нет** |
| C3 | Проверить пароль в БД | в `smtp_settings.password_encrypted` — шифртекст Fernet (`gAAAAA…`), не открытый текст |
| C4 | `PUT /admin/settings/smtp` `{"enabled":false}` (без `password`) | `200`, прежний пароль сохранён (`password_set` остаётся `true`) |
| C5 | `POST /admin/settings/smtp/test` `{"to":"x@example.com"}` на несуществующий хост | `502` «Ошибка SMTP» (путь отправки рабочий) |
| C6 | `GET/PUT /admin/settings/smtp` с `$UH` | `403` |

```bash
curl -s $API/admin/settings/smtp -H "$AH"
curl -s -X PUT $API/admin/settings/smtp -H "$AH" -H 'Content-Type: application/json' \
  -d '{"host":"smtp.example.com","port":587,"username":"mailer","password":"s3cret","use_tls":"starttls","from_email":"noreply@example.com","enabled":true}'
docker compose exec -T db psql -U postgres -d cashcontrol \
  -c "SELECT left(password_encrypted,8) enc, password_encrypted='s3cret' AS plain FROM smtp_settings WHERE id=1;"
```

### Сброс пароля

| # | Шаг | Ожидаемо |
|---|---|---|
| C7 | `POST /admin/users/{id}/reset-password` | `200`, аудит `user.password_reset_requested`; письмо в фоне (или ссылка в логе, если SMTP выкл) |
| C8 | `POST /auth/password-reset/request` `{"email":"user@example.com"}` | `200` всегда |
| C9 | То же с несуществующим email | `200` (анти-энумерация — не выдаёт факт наличия аккаунта) |
| C10 | Взять токен из лога (когда SMTP выкл), `POST /auth/password-reset/confirm` `{"token","new_password"}` | `200`, аудит `auth.password_reset_completed` |
| C11 | Логин с **новым** паролем / со **старым** | `200` / `401` |
| C12 | Повторно использовать тот же токен | `400` «недействительна или истекла» (одноразовость) |
| C13 | `confirm` с `new_password` < 8 символов | `400` |
| C14 | `confirm` с истёкшим/неверным токеном | `400` |

```bash
# Чтобы ссылка попала в лог, отключаем реальную отправку:
curl -s -o /dev/null -X PUT $API/admin/settings/smtp -H "$AH" -H 'Content-Type: application/json' -d '{"enabled":false}'
SINCE=$(date -u +%Y-%m-%dT%H:%M:%S)
curl -s -X POST $API/auth/password-reset/request -H 'Content-Type: application/json' -d '{"email":"user@example.com"}'
sleep 2
RAW=$(docker compose logs backend --since=$SINCE 2>&1 | grep 'DEV EMAIL' | grep -o 'token=[A-Za-z0-9_-]*' | tail -1 | cut -d= -f2)
curl -s -X POST $API/auth/password-reset/confirm -H 'Content-Type: application/json' -d "{\"token\":\"$RAW\",\"new_password\":\"BrandNew456\"}"
curl -s -o /dev/null -w "new-pw login: %{http_code}\n" -X POST $API/auth/login -d 'username=user@example.com&password=BrandNew456'  # 200
curl -s -o /dev/null -w "old-pw login: %{http_code}\n" -X POST $API/auth/login -d 'username=user@example.com&password=OldPass123'  # 401
```

> Примечание: dev-ссылка сброса пишется в лог backend на уровне **WARNING** (`[DEV EMAIL] …token=…`),
> когда SMTP выключён или не настроен. Сам сырой токен в БД не хранится — только его sha256-хэш.

## Swagger

Все эндпоинты доступны в интерактивной документации: <http://localhost:8000/api/v1/docs>
(Authorize → токен админа из `/auth/login`).
