# CashControl — Семейный бюджет

Веб-приложение для управления личными и семейными финансами. Два отдельных репозитория: бэкенд (FastAPI + PostgreSQL) и фронтенд (React + Vite).

---

## Быстрый старт

### Требования
- Docker + Docker Compose
- Node.js 20+ (для локальной разработки фронтенда)
- Python 3.12+ (для локальной разработки бэкенда)

### Запуск всего стека (Docker)

```bash
cd cashcontrol-backend
cp .env.example .env          # Отредактируйте SECRET_KEY
docker compose up --build
```

Поднимаются три контейнера: PostgreSQL, бэкенд и фронтенд (репозитории должны лежать рядом — `build: ../cashcontrol-frontend`).

- Приложение: http://localhost (nginx раздаёт статику и проксирует `/api/` на бэкенд)
- Бэкенд напрямую: http://localhost:8000
- Swagger UI: http://localhost:8000/api/v1/docs

### Запуск фронтенда локально (разработка)

```bash
cd cashcontrol-frontend
cp .env.example .env.local
npm install
npm run dev
```

Фронтенд: http://localhost:5173

Скрипты фронтенда: `npm run dev` (dev-сервер), `npm run build` (прод-сборка), `npm run preview` (просмотр сборки), `npm run lint` (ESLint), `npm test` (Jest).

### Деплой на сервер

Пуш в `main` автоматически собирает образы, публикует их в GHCR и обновляет сервисы на ВМ (`.github/workflows/deploy.yml` в обоих репозиториях + `docker-compose.prod.yml`). Настройка ВМ, секреты и откат — в [docs/DEPLOY.md](docs/DEPLOY.md).

---

## Архитектура

```
cashcontrol/
├── cashcontrol-backend/      # Python + FastAPI
│   ├── app/
│   │   ├── api/v1/           # REST endpoints
│   │   ├── core/             # Config, JWT, Dependencies
│   │   ├── crud/             # Database операции
│   │   ├── db/               # SQLAlchemy session, Base
│   │   ├── models/           # ORM models
│   │   └── schemas/          # Pydantic schemas
│   ├── alembic/              # Миграции БД
│   ├── tests/                # pytest
│   ├── docker-compose.yml    # db + backend + frontend
│   └── Dockerfile
│
└── cashcontrol-frontend/     # React + Vite
    ├── src/
    │   ├── api/              # Axios клиент + методы
    │   ├── components/       # UI компоненты
    │   ├── pages/            # Страницы приложения
    │   ├── store/            # Redux Toolkit slices
    │   └── utils/            # formatMoney, даты, обработка ошибок API
    ├── nginx.conf            # Раздача статики + прокси /api/ → backend
    └── Dockerfile
```

---

## API Endpoints

<!-- AUTO-GENERATED: app/api/v1/endpoints/*.py -->
| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/v1/auth/register` | Регистрация |
| POST | `/api/v1/auth/login` | Вход (OAuth2 form) |
| POST | `/api/v1/auth/refresh` | Обновление токена |
| GET | `/api/v1/users/me` | Текущий пользователь |
| PATCH | `/api/v1/users/me` | Обновить профиль |
| GET | `/api/v1/accounts/` | Список счетов |
| POST | `/api/v1/accounts/` | Создать счёт |
| GET | `/api/v1/accounts/{id}` | Счёт по id |
| PATCH | `/api/v1/accounts/{id}` | Обновить счёт |
| DELETE | `/api/v1/accounts/{id}` | Удалить счёт |
| GET | `/api/v1/transactions/` | Список транзакций (с фильтрами) |
| POST | `/api/v1/transactions/` | Добавить транзакцию (корректирует баланс счёта) |
| GET | `/api/v1/transactions/{id}` | Транзакция по id |
| PATCH | `/api/v1/transactions/{id}` | Обновить транзакцию (изменение суммы корректирует баланс) |
| DELETE | `/api/v1/transactions/{id}` | Удалить транзакцию (возвращает баланс счёта) |
| GET | `/api/v1/categories/` | Категории |
| POST | `/api/v1/categories/` | Создать категорию |
| PATCH | `/api/v1/categories/{id}` | Обновить категорию |
| DELETE | `/api/v1/categories/{id}` | Удалить категорию |
| GET | `/api/v1/budgets/` | Бюджеты + прогресс расходов |
| POST | `/api/v1/budgets/` | Создать бюджет |
| PATCH | `/api/v1/budgets/{id}` | Обновить бюджет |
| DELETE | `/api/v1/budgets/{id}` | Удалить бюджет |
<!-- /AUTO-GENERATED -->

Суммы транзакций (`amount`) должны быть строго больше нуля — иначе API вернёт 422.

---

## Миграции

```bash
# Создать новую миграцию
docker compose exec backend alembic revision --autogenerate -m "описание"

# Применить миграции
docker compose exec backend alembic upgrade head

# Откатить на 1 шаг
docker compose exec backend alembic downgrade -1
```

---

## Тесты (бэкенд)

```bash
cd cashcontrol-backend
pip install -r requirements.txt
pytest tests/ -v
```

---

## Переменные окружения

### Бэкенд (`cashcontrol-backend/.env`)

<!-- AUTO-GENERATED: cashcontrol-backend/.env.example -->
| Переменная | Описание | Пример |
|------------|----------|--------|
| `PROJECT_NAME` | Имя проекта (заголовок API) | `CashControl` |
| `VERSION` | Версия API | `0.1.0` |
| `DATABASE_URL` | Строка подключения к PostgreSQL (asyncpg) | `postgresql+asyncpg://postgres:postgres@db:5432/cashcontrol` |
| `SECRET_KEY` | Секрет для JWT (min 32 символа) — обязательно поменять | — |
| `ALGORITHM` | Алгоритм подписи JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Время жизни access-токена | `1440` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Время жизни refresh-токена | `30` |
| `ALLOWED_ORIGINS` | CORS origins (JSON массив) | `["http://localhost:5173"]` |
<!-- /AUTO-GENERATED -->

### Фронтенд (`cashcontrol-frontend/.env.local`)

<!-- AUTO-GENERATED: cashcontrol-frontend/.env.example -->
| Переменная | Описание | Пример |
|------------|----------|--------|
| `VITE_API_URL` | База URL API (относительный путь проксируется nginx/vite) | `/api/v1` |
<!-- /AUTO-GENERATED -->
