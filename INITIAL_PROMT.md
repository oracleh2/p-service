# Системный промт: Разработка мобильного прокси-сервиса

## Описание проекта

Разработать собственный мобильный прокси-сервис для нужд парсинга с автоматической ротацией IP, мониторингом устройств и веб-интерфейсом управления. Система должна работать как мини-версия коммерческого прокси-провайдера.

## Архитектура системы

### Компоненты

1. **Центральный прокси-сервер** - координатор всех запросов
2. **Мобильные устройства** - исполнители с мобильными IP
3. **Система управления** - веб-интерфейс и мониторинг
4. **API для интеграции** - подключение парсера

### Схема работы
```
[Парсер] → [Центральный сервер] → [Пул мобильных устройств] → [Интернет]
```

## Технологический стек

### Backend
- **Python 3.11+** - основной язык
- **FastAPI** - веб-фреймворк для API
- **aiohttp** - HTTP клиент и прокси-сервер
- **SQLAlchemy 2.0 (async)** - ORM для работы с БД
- **Alembic** - миграции базы данных
- **asyncio** - асинхронное программирование
- **asyncpg** - PostgreSQL драйвер
- **Redis** - кэширование и очереди
- **Celery** - фоновые задачи
- **Pydantic** - валидация данных
- **structlog** - логирование

### Frontend
- **Vue.js 3** - фронтенд фреймворк
- **Tailwind CSS** - стилизация
- **Vite** - сборщик проекта
- **Axios** - HTTP клиент
- **Chart.js** - графики и диаграммы

### Инфраструктура
- **PostgreSQL 15+** - основная база данных
- **Redis 7+** - кэш и брокер сообщений
- **Nginx** - reverse proxy и load balancer
- **Docker + Docker Compose** - контейнеризация
- **Prometheus + Grafana** - мониторинг

## Структура базы данных

```sql
-- Устройства в пуле прокси
CREATE TABLE proxy_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    device_type VARCHAR(50) NOT NULL, -- 'android', 'usb_modem', 'raspberry_pi'
    ip_address VARCHAR(45) NOT NULL,
    port INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'offline', -- 'online', 'offline', 'busy', 'maintenance'
    current_external_ip VARCHAR(45),
    operator VARCHAR(100), -- 'МТС', 'Билайн', 'Мегафон', 'Теле2'
    region VARCHAR(100),
    last_heartbeat TIMESTAMP,
    last_ip_rotation TIMESTAMP,
    rotation_interval INTEGER DEFAULT 600, -- секунды
    total_requests INTEGER DEFAULT 0,
    successful_requests INTEGER DEFAULT 0,
    failed_requests INTEGER DEFAULT 0,
    avg_response_time_ms INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Конфигурация ротации IP
CREATE TABLE rotation_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID REFERENCES proxy_devices(id) ON DELETE CASCADE,
    rotation_method VARCHAR(50) NOT NULL, -- 'airplane_mode', 'data_toggle', 'api_call'
    rotation_interval INTEGER NOT NULL,
    auto_rotation BOOLEAN DEFAULT TRUE,
    rotation_url VARCHAR(500), -- для API ротации
    auth_token VARCHAR(255),
    rotation_success_rate FLOAT DEFAULT 0.0,
    last_successful_rotation TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Логи запросов
CREATE TABLE request_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID REFERENCES proxy_devices(id) ON DELETE CASCADE,
    client_ip VARCHAR(45),
    target_url VARCHAR(1000),
    method VARCHAR(10),
    status_code INTEGER,
    response_time_ms INTEGER,
    external_ip VARCHAR(45),
    user_agent TEXT,
    request_size INTEGER,
    response_size INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- История IP адресов
CREATE TABLE ip_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID REFERENCES proxy_devices(id) ON DELETE CASCADE,
    ip_address VARCHAR(45) NOT NULL,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_requests INTEGER DEFAULT 0,
    operator VARCHAR(100),
    geo_location VARCHAR(100),
    city VARCHAR(100),
    is_blocked BOOLEAN DEFAULT FALSE,
    blocked_reason TEXT
);

-- Пользователи и аутентификация
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    api_key VARCHAR(255) UNIQUE,
    role VARCHAR(50) DEFAULT 'user', -- 'admin', 'user'
    is_active BOOLEAN DEFAULT TRUE,
    requests_limit INTEGER DEFAULT 10000,
    requests_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Статистика использования
CREATE TABLE usage_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID REFERENCES proxy_devices(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    requests_count INTEGER DEFAULT 0,
    successful_requests INTEGER DEFAULT 0,
    failed_requests INTEGER DEFAULT 0,
    avg_response_time_ms INTEGER DEFAULT 0,
    unique_ips_count INTEGER DEFAULT 0,
    data_transferred_mb INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(device_id, user_id, date)
);

-- Конфигурация системы
CREATE TABLE system_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(255) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    description TEXT,
    config_type VARCHAR(50) DEFAULT 'string', -- 'string', 'integer', 'boolean', 'json'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Структура проекта

```
mobile-proxy-service/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # Точка входа FastAPI
│   │   ├── config.py               # Конфигурация
│   │   ├── database.py             # Подключение к БД
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── proxy_server.py     # Основной прокси-сервер
│   │   │   ├── load_balancer.py    # Балансировщик нагрузки
│   │   │   ├── device_manager.py   # Управление устройствами
│   │   │   ├── rotation_manager.py # Управление ротацией IP
│   │   │   ├── health_monitor.py   # Мониторинг здоровья
│   │   │   └── stats_collector.py  # Сбор статистики
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── admin.py           # API администрирования
│   │   │   ├── proxy.py           # API прокси
│   │   │   ├── stats.py           # API статистики
│   │   │   ├── devices.py         # API устройств
│   │   │   └── auth.py            # API аутентификации
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # Базовые модели
│   │   │   ├── device.py          # Модели устройств
│   │   │   ├── request.py         # Модели запросов
│   │   │   ├── user.py            # Модели пользователей
│   │   │   └── stats.py           # Модели статистики
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── device.py          # Pydantic схемы устройств
│   │   │   ├── request.py         # Pydantic схемы запросов
│   │   │   ├── user.py            # Pydantic схемы пользователей
│   │   │   └── stats.py           # Pydantic схемы статистики
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── security.py        # Безопасность и хеширование
│   │   │   ├── logger.py          # Настройка логирования
│   │   │   └── validators.py      # Валидаторы
│   │   └── tasks/
│   │       ├── __init__.py
│   │       ├── celery_app.py      # Конфигурация Celery
│   │       ├── rotation_tasks.py  # Задачи ротации
│   │       └── monitoring_tasks.py # Задачи мониторинга
│   ├── alembic/
│   │   ├── versions/
│   │   ├── env.py
│   │   └── alembic.ini
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_proxy.py
│   │   ├── test_devices.py
│   │   └── test_api.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.vue
│   │   │   ├── DeviceList.vue
│   │   │   ├── DeviceCard.vue
│   │   │   ├── StatsChart.vue
│   │   │   ├── ConfigModal.vue
│   │   │   └── AlertPanel.vue
│   │   ├── views/
│   │   │   ├── Home.vue
│   │   │   ├── Devices.vue
│   │   │   ├── Statistics.vue
│   │   │   ├── Configuration.vue
│   │   │   └── Logs.vue
│   │   ├── stores/
│   │   │   ├── auth.js
│   │   │   ├── devices.js
│   │   │   └── stats.js
│   │   ├── router/
│   │   │   └── index.js
│   │   ├── utils/
│   │   │   ├── api.js
│   │   │   └── helpers.js
│   │   ├── App.vue
│   │   └── main.js
│   ├── public/
│   ├── package.json
│   └── vite.config.js
├── device-agents/
│   ├── android/
│   │   ├── agent.py              # Агент для Android
│   │   ├── proxy_manager.py      # Управление прокси
│   │   ├── rotation_handler.py   # Обработка ротации
│   │   └── requirements.txt
│   ├── raspberry-pi/
│   │   ├── agent.py              # Агент для Raspberry Pi
│   │   ├── modem_manager.py      # Управление модемом
│   │   └── requirements.txt
│   └── common/
│       ├── base_agent.py         # Базовый класс агента
│       ├── heartbeat.py          # Heartbeat функциональность
│       └── config.py             # Конфигурация агента
├── docker-compose.yml
├── .env.example
├── README.md
└── requirements.txt
```

## Основные функции системы

### 1. Центральный прокси-сервер

**Функции:**
- Прием HTTP/HTTPS запросов от клиентов
- Маршрутизация запросов к мобильным устройствам
- Load balancing между устройствами
- Кэширование и оптимизация запросов
- Логирование всех операций

**Алгоритмы балансировки:**
- Round Robin - поочередное распределение
- Least Connections - к наименее загруженному
- Random - случайный выбор
- Weighted - с учетом весов устройств
- IP Hash - привязка к конкретному устройству

### 2. Управление мобильными устройствами

**Типы поддерживаемых устройств:**
- Android смартфоны/планшеты
- USB 4G модемы
- Raspberry Pi с 4G модулями
- Мини-ПК с встроенными модемами

**Функции управления:**
- Автоматическая регистрация устройств
- Мониторинг состояния в реальном времени
- Управление конфигурацией
- Удаленное обновление агентов

### 3. Система ротации IP

**Методы ротации:**
- **Airplane Mode** - включение/выключение режима полета
- **Data Toggle** - переключение мобильных данных
- **Network Reset** - сброс сетевых настроек
- **API Call** - вызов API оператора (если доступно)

**Стратегии ротации:**
- По времени (каждые N минут)
- По количеству запросов
- По сессиям
- Принудительная по запросу

### 4. Мониторинг и аналитика

**Метрики для отслеживания:**
- Количество активных устройств
- Загрузка каждого устройства
- Успешность запросов (success rate)
- Время отклика (response time)
- Частота ротации IP
- Уникальность IP адресов
- Географическое распределение IP

**Алерты:**
- Устройство недоступно >5 минут
- Success rate <85%
- Отказ ротации IP
- Превышение лимитов запросов

## API Endpoints

### Администрирование

```
GET    /api/v1/admin/devices              # Список устройств
POST   /api/v1/admin/devices              # Добавить устройство
PUT    /api/v1/admin/devices/{id}         # Обновить устройство
DELETE /api/v1/admin/devices/{id}         # Удалить устройство
POST   /api/v1/admin/devices/{id}/rotate  # Принудительная ротация
GET    /api/v1/admin/devices/{id}/stats   # Статистика устройства
POST   /api/v1/admin/devices/{id}/restart # Перезапуск устройства
```

### Клиентское API

```
GET    /api/v1/proxy/list                 # Список доступных прокси
GET    /api/v1/proxy/random               # Случайный прокси
GET    /api/v1/proxy/by-operator          # Прокси по оператору
POST   /api/v1/proxy/rotate               # Ротация всех прокси
GET    /api/v1/proxy/status               # Статус прокси-сервиса
```

### Статистика

```
GET    /api/v1/stats/overview             # Общая статистика
GET    /api/v1/stats/devices              # Статистика по устройствам
GET    /api/v1/stats/requests             # Статистика запросов
GET    /api/v1/stats/ips                  # Статистика IP адресов
GET    /api/v1/stats/export               # Экспорт статистики
```

## Агенты на устройствах

### Android Agent

**Функции:**
- Запуск локального HTTP прокси
- Мониторинг состояния устройства
- Выполнение команд ротации IP
- Отправка heartbeat в центральный сервер
- Сбор статистики использования

**Методы ротации для Android:**
- Airplane Mode API
- Mobile Data Toggle
- Network Manager Reset
- Restart Mobile Radio

### Raspberry Pi Agent

**Функции:**
- Управление 4G модемом
- Мониторинг качества сигнала
- Перезагрузка модема при проблемах
- Сбор данных о соединении

**Методы ротации для Raspberry Pi:**
- AT команды модему
- Переподключение к сети
- Смена APN настроек
- Физическая перезагрузка модема

## Конфигурация по умолчанию

### Система
- Интервал ротации IP: 600 секунд (10 минут)
- Health check интервал: 30 секунд
- Heartbeat timeout: 60 секунд
- Максимальное количество устройств: 50
- Лимит запросов в минуту: 100 на устройство

### Прокси-сервер
- Порт прокси: 8080
- API порт: 8000
- Timeout запросов: 30 секунд
- Максимальные concurrent connections: 100
- Размер буфера: 8192 bytes

### Ротация IP
- Автоматическая ротация: включена
- Интервал между ротациями: 10 минут
- Максимальное время ротации: 60 секунд
- Количество попыток ротации: 3
- Задержка между попытками: 10 секунд

### Мониторинг
- Интервал сбора метрик: 30 секунд
- Хранение логов: 30 дней
- Retention статистики: 90 дней
- Размер лог файла: 100 MB

## Безопасность

### Аутентификация
- JWT токены для API
- API ключи для клиентов
- Bcrypt для хеширования паролей
- Rate limiting для API

### Защита данных
- HTTPS для всех соединений
- Шифрование чувствительных данных
- Secure cookies
- CORS политики

### Мониторинг безопасности
- Логирование всех API вызовов
- Детекция подозрительной активности
- Блокировка по IP при превышении лимитов
- Регулярные аудиты безопасности

## Развертывание

### Docker Compose

```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: mobile_proxy
      POSTGRES_USER: proxy_user
      POSTGRES_PASSWORD: proxy_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql://proxy_user:proxy_password@postgres:5432/mobile_proxy
      REDIS_URL: redis://redis:6379

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - backend
      - frontend

volumes:
  postgres_data:
```

### Переменные окружения

```bash
# Database
DATABASE_URL=postgresql://proxy_user:proxy_password@localhost:5432/mobile_proxy
DATABASE_POOL_SIZE=20

# Redis
REDIS_URL=redis://localhost:6379
REDIS_POOL_SIZE=10

# Security
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key
API_KEY_LENGTH=32

# Proxy Settings
PROXY_PORT=8080
API_PORT=8000
DEFAULT_ROTATION_INTERVAL=600
MAX_DEVICES=50
MAX_REQUESTS_PER_MINUTE=100

# Monitoring
HEALTH_CHECK_INTERVAL=30
HEARTBEAT_TIMEOUT=60
LOG_RETENTION_DAYS=30
METRICS_RETENTION_DAYS=90

# External Services
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
SLACK_WEBHOOK_URL=your-slack-webhook-url
```

## Мониторинг и алерты

### Prometheus метрики

```python
# Основные метрики для мониторинга
active_devices_count = Gauge('active_devices_total', 'Number of active devices')
request_duration_seconds = Histogram('request_duration_seconds', 'Request duration')
requests_total = Counter('requests_total', 'Total requests', ['device', 'status'])
ip_rotations_total = Counter('ip_rotations_total', 'Total IP rotations', ['device', 'method'])
device_health_status = Gauge('device_health_status', 'Device health status', ['device'])
```

### Grafana Dashboard

**Панели мониторинга:**
- Общая статистика системы
- Состояние устройств
- Загрузка прокси-сервера
- Статистика ротации IP
- Успешность запросов
- Время отклика
- Использование ресурсов

## Тестирование

### Unit тесты
- Тестирование API endpoints
- Тестирование логики ротации
- Тестирование балансировщика
- Тестирование агентов

### Integration тесты
- Тестирование взаимодействия компонентов
- Тестирование базы данных
- Тестирование Redis
- Тестирование внешних API

### Load тесты
- Тестирование производительности
- Тестирование масштабируемости
- Тестирование стабильности
- Тестирование восстановления

## План этапов разработки

### Этап 1: Основа (3-4 недели)
- Настройка инфраструктуры
- Создание структуры проекта
- Базовые модели данных
- Простой прокси-сервер
- Базовое API

### Этап 2: Устройства (2-3 недели)
- Агенты для устройств
- Система heartbeat
- Регистрация устройств
- Базовый мониторинг

### Этап 3: Ротация IP (2-3 недели)
- Система ротации IP
- Различные методы ротации
- Автоматическая ротация по расписанию
- Принудительная ротация

### Этап 4: Балансировка (1-2 недели)
- Load balancer
- Различные алгоритмы распределения
- Failover механизмы
- Оптимизация производительности

### Этап 5: Веб-интерфейс (3-4 недели)
- Frontend приложение
- Dashboard с метриками
- Управление устройствами
- Конфигурация системы

### Этап 6: Мониторинг (1-2 недели)
- Prometheus интеграция
- Grafana дашборды
- Система алертов
- Логирование

### Этап 7: Тестирование (2-3 недели)
- Unit и integration тесты
- Load тестирование
- Security тестирование
- Документация

### Этап 8: Деплой (1-2 недели)
- Docker контейнеры
- CI/CD pipeline
- Production конфигурация
- Мониторинг в продакшене

**Общий срок разработки: 15-23 недели**

## Требования к производительности

- Поддержка 100+ одновременных соединений
- Время отклика API <100ms
- Обработка 10,000+ запросов в час
- Uptime 99.5%
- Автоматическое восстановление после сбоев
- Поддержка 50+ мобильных устройств

## Масштабирование

### Горизонтальное масштабирование
- Добавление новых устройств
- Распределение по регионам
- Множественные центральные серверы
- Кластеризация Redis

### Вертикальное масштабирование
- Увеличение мощности серверов
- Оптимизация базы данных
- Тюнинг прокси-сервера
- Кеширование запросов

Данный промт содержит полную спецификацию для создания собственного мобильного прокси-сервиса с возможностью масштабирования под любые нужды парсинга.
