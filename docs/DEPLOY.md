# Деплой на виртуальную машину

CI/CD: пуш в `main` любого из репозиториев → GitHub Actions собирает Docker-образ → публикует в GHCR → по SSH обновляет соответствующий сервис на ВМ.

```
push в main ──► ci.yml (тесты) ─┐
                                 │  (независимо)
push в main ──► deploy.yml:
                  build-push ──► ghcr.io/maxberezovskiy/cashcontrol-{backend,frontend}
                                   :latest + :<git-sha>
                  deploy ──SSH──► ВМ: TAG=<sha> → docker compose pull → up -d → smoke-test
```

## Разовая настройка ВМ

```bash
# 1. Docker + compose-плагин (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh

# 2. Каталог деплоя
sudo mkdir -p /opt/cashcontrol && sudo chown $USER /opt/cashcontrol
cd /opt/cashcontrol

# 3. Прод-компоуз (копируется ОДИН раз; обновления приложения приходят образами)
curl -fsSL https://raw.githubusercontent.com/maxberezovskiy/cashcontrol-backend/main/docker-compose.prod.yml \
  -o docker-compose.yml

# 4. Переменные окружения
cat > .env <<'EOF'
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change-me-strong-password
POSTGRES_DB=cashcontrol
SECRET_KEY=change-me-to-a-random-32-char-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_DAYS=30
ALLOWED_ORIGINS=["http://YOUR_VM_IP"]
# Админ-фича (см. раздел ниже). SMTP-аккаунт здесь НЕ задаётся — вводится из UI суперпользователя.
SETTINGS_ENC_KEY=PASTE_FERNET_KEY_HERE
FRONTEND_BASE_URL=http://YOUR_VM_IP
PASSWORD_RESET_TTL_MINUTES=60
FIRST_SUPERUSER_EMAIL=berezovskiy.max@mail.ru
BACKEND_TAG=latest
FRONTEND_TAG=latest
EOF
chmod 600 .env

# 5. Доступ к GHCR (если пакеты приватные; для публичных не нужно)
#    PAT с правом read:packages
docker login ghcr.io -u maxberezovskiy

# 6. Первый запуск
docker compose pull && docker compose up -d
```

## Секреты GitHub Actions

Задать в **обоих** репозиториях (Settings → Secrets and variables → Actions):

| Секрет | Значение |
|--------|----------|
| `VM_HOST` | IP или hostname ВМ |
| `VM_USER` | SSH-пользователь (член группы `docker`) |
| `VM_SSH_KEY` | Приватный SSH-ключ (PEM), парный ключ — в `~/.ssh/authorized_keys` на ВМ |

Рекомендуется отдельный ключ только для деплоя: `ssh-keygen -t ed25519 -f deploy_key -C cashcontrol-deploy`.

## Как устроен деплой

- Образы тегируются `latest` **и** git-SHA — каждый деплой воспроизводим.
- У каждого сервиса свой тег: деплой бэкенда пишет `BACKEND_TAG=<sha>`, фронтенда — `FRONTEND_TAG=<sha>` в `/opt/cashcontrol/.env`; запущенные версии видны через `grep TAG /opt/cashcontrol/.env`. Раздельные переменные обязательны: SHA-теги двух репозиториев не совпадают, общий тег ломал бы соседний сервис.
- Миграции Alembic выполняются автоматически при старте контейнера бэкенда (`command` в compose).
- После рестарта сервиса выполняется smoke-test (`curl` через nginx); при провале джоба падает и в логи попадает хвост логов контейнера.
- **Релиз — по кнопке**: на окружении `production` включены required reviewers (в обоих репо: Settings → Environments → production). Каждый пуш в `main` собирает и публикует образ в GHCR, но деплой-джоба останавливается со статусом «Waiting» — на ВМ уезжает только сборка, одобренная в Actions кнопкой **Review deployments → Approve and deploy**. Неодобренные сборки остаются в GHCR со своими SHA-тегами, их можно потестировать локально: `BACKEND_TAG=<sha> docker compose -f docker-compose.prod.yml up backend`.

## Откат

Actions → нужный репозиторий → «Deploy Backend/Frontend» → **Run workflow** → в поле `tag` указать git-SHA предыдущей рабочей версии (виден в истории успешных раннов или `git log --oneline`). Сборка пропускается, на ВМ разворачивается существующий образ.

## Суперпользователь и почта (админ-фича)

Полная постановка — `docs/ADMIN_FEATURE.md`, ручные тест-кейсы — `docs/ADMIN_FEATURE_TESTCASES.md`.

**Переменные `.env` (прод):**

| Переменная | Назначение |
|---|---|
| `SETTINGS_ENC_KEY` | **Обязателен в проде.** Fernet-ключ для шифрования SMTP-пароля в БД. Постоянный: при потере/смене ранее сохранённый SMTP-пароль не расшифровать — придётся ввести заново через UI. Сгенерировать: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Хранить как секрет рядом с `SECRET_KEY`. |
| `FRONTEND_BASE_URL` | Публичный URL фронтенда — из него собирается ссылка сброса пароля в письме (`${FRONTEND_BASE_URL}/reset-password?token=...`). |
| `PASSWORD_RESET_TTL_MINUTES` | Срок жизни токена сброса (по умолчанию 60). |
| `FIRST_SUPERUSER_EMAIL` | Этот пользователь повышается до admin при каждом старте бэкенда (promote-only, идемпотентно). |

**Первый администратор (бутстрап):** механизм — *promote-only*. Пользователь с `FIRST_SUPERUSER_EMAIL` должен быть зарегистрирован обычным путём (`/auth/register`); на старте бэкенда (`lifespan`) он автоматически получает роль admin. Даже если роль снять через UI, ближайший рестарт вернёт её — это постоянный аварийный доступ. Резервно: `UPDATE users SET is_superuser=true WHERE email='...'` в БД.

**Миграции** `audit_logs`, `smtp_settings`, `password_reset_tokens` применяются автоматически (`alembic upgrade head` в `command` бэкенда) — отдельных действий не требуют.

**Настройка SMTP — из UI, не из env.** Войти под админом → раздел «Настройки SMTP» (`/admin/smtp`) → ввести хост/порт/аккаунт/пароль/TLS/отправителя, включить отправку, проверить кнопкой «Отправить тестовое письмо». Пароль шифруется (`SETTINGS_ENC_KEY`) и наружу из API не отдаётся. **Пока SMTP не настроен или выключен — письма не уходят, а ссылка сброса пишется в лог бэкенда** (`docker compose logs backend | grep "DEV EMAIL"`). Желателен SPF/DKIM у почтового провайдера, чтобы письма не падали в спам.

### Если провайдер блокирует исходящий SMTP (HTTPS-API транспорт)

Многие хостинги/ДЦ режут исходящие SMTP-порты (25/465/587, иногда и 2525) — прямая отправка через
`smtp.*` тогда не работает (симптомы: `Timed out` или `Network is unreachable` при коннекте).
Проверить с ВМ:
```bash
docker compose exec backend python -c "import socket; socket.create_connection(('smtp.mail.ru',587),8); print('OK')"
```
Если `unreachable`/timeout, а `python -c "import socket; socket.create_connection(('1.1.1.1',443),8)"` — OK,
значит исходящий SMTP закрыт, но HTTPS (443) открыт. В этом случае используется **API-транспорт**:

1. Завести аккаунт у провайдера (по умолчанию **Brevo**), подтвердить адрес-отправитель (Senders),
   создать API-ключ (SMTP & API → API Keys).
2. Админка → «Настройки почты» → **Способ отправки: HTTPS-API** → провайдер **Brevo**, вставить
   API-ключ, указать подтверждённый `from`, включить → «Отправить тестовое письмо».

Ключ шифруется (`SETTINGS_ENC_KEY`) и хранится в `smtp_settings.api_key_encrypted`; наружу не отдаётся.
Миграция `d4e5f6a7b8c9` (поля `transport`/`api_provider`/`api_key_encrypted`) применяется автоматически
при старте бэкенда. Альтернатива — тикет провайдеру на разблокировку 587/465 (тогда хватит обычного SMTP).

## Бэкапы БД

На ВМ настроен cron пользователя `deploy`: каждый день в 00:00 UTC (03:00 МСК) скрипт `/opt/cashcontrol/backup.sh` делает `pg_dump` в `/opt/cashcontrol/backups/cashcontrol-YYYY-MM-DD.sql.gz`, проверяет архив и хранит **7 последних** дампов (старые удаляются). Журнал — `backups/backup.log`.

Восстановление из дампа:

```bash
cd /opt/cashcontrol
gunzip -c backups/cashcontrol-ДАТА.sql.gz | docker compose exec -T db psql -U postgres -d cashcontrol
```

(при восстановлении «с нуля» сначала пересоздать пустую БД: `docker compose exec -T db psql -U postgres -c "DROP DATABASE cashcontrol; CREATE DATABASE cashcontrol;"` — бэкенд на это время остановить)

Бэкапы лежат на той же ВМ — от потери самой машины не защищают. При появлении ценных данных стоит добавить выгрузку в офсайт (S3/rclone).

## Типовые проблемы

| Симптом | Причина / решение |
|---------|-------------------|
| `pull access denied` на ВМ | Пакеты GHCR приватные → `docker login ghcr.io` с PAT `read:packages`, либо сделать пакеты публичными |
| Smoke-test падает после деплоя бэкенда | Падение миграции или невалидный `.env` → `docker compose logs backend` |
| `Permission denied (publickey)` в джобе | Публичный ключ не добавлен в `authorized_keys`, или в секрете не приватный ключ целиком |
| Деплои из двух репо одновременно | Безопасно: каждый трогает только свой сервис; `concurrency` сериализует деплои внутри репо |
