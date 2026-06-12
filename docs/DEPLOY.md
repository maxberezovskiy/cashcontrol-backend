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

## Типовые проблемы

| Симптом | Причина / решение |
|---------|-------------------|
| `pull access denied` на ВМ | Пакеты GHCR приватные → `docker login ghcr.io` с PAT `read:packages`, либо сделать пакеты публичными |
| Smoke-test падает после деплоя бэкенда | Падение миграции или невалидный `.env` → `docker compose logs backend` |
| `Permission denied (publickey)` в джобе | Публичный ключ не добавлен в `authorized_keys`, или в секрете не приватный ключ целиком |
| Деплои из двух репо одновременно | Безопасно: каждый трогает только свой сервис; `concurrency` сериализует деплои внутри репо |
