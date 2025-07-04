# Mobile Proxy Service - Development Mode

Режим разработки с инфраструктурными сервисами в Docker и Backend/Frontend запущенными локально.

## 🚀 Быстрый старт

```bash
# Сделайте скрипты исполняемыми
chmod +x start-dev.sh stop-dev.sh

# Запустите инфраструктурные сервисы
./start-dev.sh

# В отдельных терминалах запустите:

# Terminal 1 - Backend
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - Frontend  
cd frontend
npm install
npm run dev
```

## 🐳 Что запускается в Docker

| Сервис | Порт | Описание |
|--------|------|----------|
| PostgreSQL | 5432 | База данных |
| Redis | 6379 | Кэш и очереди |
| Prometheus | 9090 | Мониторинг метрик |
| Grafana | 3001 | Дашборды (admin/admin123) |

## 💻 Что запускается локально

| Сервис | Порт | Команда запуска |
|--------|------|----------------|
| Backend API | 8000 | `uvicorn app.main:app --reload` |
| Frontend | 3000 | `npm run dev` |

## 🔧 Настройка Backend

```bash
cd backend

# Создайте виртуальное окружение (рекомендуется)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt

# Запустите сервер разработки
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Environment Variables для Backend

```bash
# Создайте .env в корне проекта (автоматически создается скриптом)
DATABASE_URL=postgresql://proxy_user:proxy_password@localhost:5432/mobile_proxy
REDIS_URL=redis://localhost:6379
SECRET_KEY=your-secret-key-change-in-production
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
DEBUG=true
RELOAD=true
```

## 🌐 Настройка Frontend

```bash
cd frontend

# Установите зависимости
npm install

# Запустите сервер разработки
npm run dev

# Или с определенным хостом
npm run dev -- --host 0.0.0.0
```

### Environment Variables для Frontend

```bash
# В frontend/.env.local
VITE_API_BASE_URL=http://localhost:8000
VITE_DEV_MODE=true
```

## 🛠️ Дополнительные инструменты

Запустите дополнительные инструменты для разработки:

```bash
# Adminer для управления БД + Redis Commander
docker-compose -f docker-compose.yml --profile tools up -d
```

| Инструмент | URL | Описание |
|------------|-----|----------|
| Adminer | http://localhost:8080 | Управление PostgreSQL |
| Redis Commander | http://localhost:8081 | Управление Redis |

## 📊 Мониторинг

- **Prometheus**: http://localhost:9090
  - Метрики Backend: http://localhost:8000/metrics
  - Системные метрики

- **Grafana**: http://localhost:3001
  - Логин: admin
  - Пароль: admin123
  - Дашборды настроены автоматически

## 🗃️ База данных

### Подключение к PostgreSQL

```bash
# Через psql
psql -h localhost -p 5432 -U proxy_user -d mobile_proxy

# Или через Adminer
# http://localhost:8080
# Сервер: postgres (или localhost)
# Пользователь: proxy_user
# Пароль: proxy_password
# База: mobile_proxy
```

### Миграции

```bash
cd backend

# Создание миграции
alembic revision --autogenerate -m "Description"

# Применение миграций
alembic upgrade head

# Откат миграции
alembic downgrade -1
```

## 🔄 Redis

### Подключение к Redis

```bash
# Через redis-cli
redis-cli -h localhost -p 6379

# Или через Redis Commander
# http://localhost:8081
```

## 📝 Разработка

### Структура Backend

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # Точка входа FastAPI
│   ├── config.py        # Конфигурация
│   ├── api/             # API endpoints
│   ├── core/            # Основная логика
│   ├── models/          # Модели данных
│   └── utils/           # Утилиты
├── requirements.txt
└── Dockerfile
```

### Структура Frontend

```
frontend/
├── src/
│   ├── components/      # Vue компоненты
│   ├── views/          # Страницы
│   ├── stores/         # Pinia stores
│   ├── router/         # Vue Router
│   ├── utils/          # Утилиты
│   └── main.js         # Точка входа
├── package.json
└── vite.config.js
```

## 🐛 Отладка

### Backend отладка

```bash
# Запуск с отладкой
python -m uvicorn app.main:app --reload --log-level debug

# Тесты
pytest

# Линтер
flake8 app/
```

### Frontend отладка

```bash
# Запуск с подробными логами
npm run dev -- --debug

# Сборка для проверки
npm run build

# Линтер
npm run lint
```

## 🔍 Логи

### Просмотр логов контейнеров

```bash
# Все сервисы
docker-compose -f docker-compose.yml logs -f

# Конкретный сервис
docker-compose -f docker-compose.yml logs -f postgres
docker-compose -f docker-compose.yml logs -f redis
```

### Логи приложений

- Backend логи: в консоли uvicorn
- Frontend логи: в консоли vite + браузере

## 🛑 Остановка

```bash
# Остановка инфраструктурных сервисов
./stop-dev.sh

# Остановка Backend/Frontend
# Ctrl+C в соответствующих терминалах

# Полная очистка (удаление данных)
docker-compose -f docker-compose.yml down -v
docker system prune -f
```

## 💡 Полезные команды

```bash
# Перезапуск инфраструктуры
docker-compose -f docker-compose.yml restart

# Пересборка контейнеров
docker-compose -f docker-compose.yml up -d --build

# Проверка статуса
docker-compose -f docker-compose.yml ps

# Подключение к контейнеру
docker-compose -f docker-compose.yml exec postgres psql -U proxy_user mobile_proxy
docker-compose -f docker-compose.yml exec redis redis-cli
```

## 🆘 Решение проблем

### Порты заняты

```bash
# Проверка занятых портов
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis
lsof -i :8000  # Backend
lsof -i :3000  # Frontend

# Остановка процесса
kill -9 <PID>
```

### Проблемы с базой данных

```bash
# Пересоздание базы
docker-compose -f docker-compose.yml down -v
docker-compose -f docker-compose.yml up -d postgres
```

### Проблемы с кэшем

```bash
# Очистка Redis
docker-compose -f docker-compose.yml exec redis redis-cli FLUSHALL
```

Этот режим идеален для разработки, так как позволяет быстро перезапускать Backend/Frontend с hot reload, а инфраструктурные сервисы остаются стабильными в Docker.
