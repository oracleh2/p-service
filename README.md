# Mobile Proxy Service

Система управления мобильными прокси с автоматической ротацией IP адресов.

## 🚀 Возможности

- **Автоматическая ротация IP** с настраиваемыми интервалами
- **Принудительная ротация** по требованию через админку
- **Мониторинг устройств** в реальном времени
- **Статистика и аналитика** запросов
- **Веб-интерфейс** для управления
- **REST API** для интеграции
- **Поддержка различных типов устройств** (Android, USB модемы, Raspberry Pi)

## 📋 Требования

- Docker и Docker Compose
- Python 3.11+ (для разработки)
- PostgreSQL 15+
- Redis 7+

## 🛠️ Установка и запуск

### 1. Клонирование репозитория

```bash
git clone <repository_url>
cd mobile-proxy-service
```

### 2. Настройка окружения

```bash
# Копируем пример файла окружения
cp .env.example .env

# Редактируем настройки (обязательно поменяйте секретные ключи!)
nano .env
```

### 3. Запуск через Docker Compose

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка сервисов
docker-compose down
```

### 4. Проверка работы

```bash
# Проверка API
curl http://localhost:8000/health

# Проверка прокси-сервера
curl http://localhost:8080/proxy/health

# Веб-интерфейс
open http://localhost:3000
```

## 🔧 Конфигурация

### Основные настройки

Все настройки задаются через переменные окружения в файле `.env`:

```bash
# Прокси настройки
DEFAULT_ROTATION_INTERVAL=600  # 10 минут по умолчанию
MAX_DEVICES=50
MAX_REQUESTS_PER_MINUTE=100
PROXY_PORT=8080
API_PORT=8000

# База данных
DATABASE_URL=postgresql://proxy_user:proxy_password@localhost:5432/mobile_proxy

# Redis
REDIS_URL=redis://localhost:6379

# Безопасность
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key
```

### Настройка ротации IP

По умолчанию система настроена на ротацию IP каждые 10 минут. Это можно изменить:

1. **Глобально** - через системные настройки в админке
2. **Для каждого устройства** - индивидуально в настройках устройства

## 📱 Подключение модемов

### USB 4G модемы

1. **Подключите USB модем к серверу**
   ```bash
   # Проверьте, что модем определился
   lsusb | grep -i "huawei\|zte\|quectel"
   ```

2. **Система автоматически обнаружит модем**
   - Модем будет доступен через последовательный порт (`/dev/ttyUSB0`, `/dev/ttyACM0`)
   - Ротация IP через AT-команды: `AT+CFUN=0/1`

3. **Никаких дополнительных агентов не требуется!**

### Android устройства как модемы

1. **Подключите Android устройство через USB**
   ```bash
   # Включите отладку по USB на устройстве
   # Включите USB tethering (USB-модем)
   
   # Проверьте подключение
   adb devices
   ```

2. **Система автоматически обнаружит устройство**
   - Устройство будет доступно через ADB
   - Ротация IP через команды: `svc data disable/enable`

3. **Без установки приложений на телефон!**

### Raspberry Pi с 4G модулями

1. **Подключите 4G модуль к Raspberry Pi**
   ```bash
   # Установите необходимые пакеты на RPi
   sudo apt update
   sudo apt install ppp wvdial
   ```

2. **Настройте PPP соединение**
   ```bash
   # Создайте конфигурацию wvdial
   sudo nano /etc/wvdial.conf
   ```

3. **Система обнаружит PPP интерфейс автоматически**

## 🎛️ Административный интерфейс

### Доступ к админке

```bash
# Пользователь по умолчанию
Логин: admin
Пароль: admin123

# URL админки
http://localhost:3000
```

### Основные функции

- **Управление устройствами** - добавление, удаление, настройка
- **Мониторинг** - состояние устройств, статистика
- **Настройка ротации** - интервалы, методы ротации
- **Логи и аналитика** - просмотр запросов, ошибок

## 🔄 Методы ротации IP

### Airplane Mode
```bash
# Включение/выключение режима полета
# Работает на Android устройствах
```

### Data Toggle
```bash
# Переключение мобильных данных
# Работает на Android устройствах
```

### Network Reset
```bash
# Сброс сетевых настроек
# Работает на всех типах устройств
```

### API Call
```bash
# Вызов внешнего API для ротации
# Настраивается индивидуально
```

## 📊 Использование прокси

### Основное использование

```bash
# Использование прокси
curl -x http://localhost:8080 https://httpbin.org/ip

# Выбор конкретного модема
curl -x http://localhost:8080 -H "X-Proxy-Modem-ID: usb_0" https://httpbin.org/ip

# Проверка доступных модемов
curl http://localhost:8080/proxy/modems
```

### Программное использование

```python
import requests

# Настройка прокси
proxies = {
    'http': 'http://localhost:8080',
    'https': 'http://localhost:8080'
}

# Выполнение запроса
response = requests.get('https://httpbin.org/ip', proxies=proxies)
print(response.json())

# Выбор конкретного модема
headers = {'X-Proxy-Modem-ID': 'android_ABC123'}
response = requests.get(
    'https://httpbin.org/ip', 
    proxies=proxies,
    headers=headers
)
```

### Методы ротации IP

#### USB модемы
```bash
# Автоматическая ротация через AT-команды
AT+CFUN=0  # Отключение радио
AT+CFUN=1  # Включение радио
```

#### Android устройства
```bash
# Автоматическая ротация через ADB
adb shell svc data disable  # Отключение данных
adb shell svc data enable   # Включение данных
```

#### Raspberry Pi
```bash
# Автоматическая ротация через системные команды
sudo ifdown ppp0  # Отключение PPP
sudo ifup ppp0    # Включение PPP
```

## 🔌 REST API

### Аутентификация

```bash
# Получение токена
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### Управление устройствами

```bash
# Список устройств
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/devices/

# Добавление устройства
curl -X POST http://localhost:8000/api/v1/devices/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Android-1",
    "device_type": "android",
    "ip_address": "192.168.1.100",
    "port": 8888,
    "operator": "МТС",
    "region": "Москва"
  }'

# Принудительная ротация IP
curl -X POST http://localhost:8000/api/v1/devices/DEVICE_ID/rotate \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Статистика

```bash
# Общая статистика
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/stats/overview

# Статистика устройства
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/devices/DEVICE_ID/stats
```

## 🏗️ Разработка

### Локальный запуск для разработки

```bash
# Установка зависимостей
cd backend
pip install -r requirements.txt

# Запуск только базы данных
docker-compose up -d postgres redis

# Запуск приложения
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Структура проекта

```
mobile-proxy-service/
├── backend/               # Backend приложение
│   ├── app/
│   │   ├── api/          # API endpoints
│   │   ├── core/         # Основная логика
│   │   ├── models/       # Модели данных
│   │   └── utils/        # Утилиты
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/             # Frontend приложение (Vue.js)
├── device-agents/        # Агенты для устройств
├── docker-compose.yml
└── README.md
```

### Запуск тестов

```bash
cd backend
pytest tests/
```

## 🐛 Устранение неполадок

### Общие проблемы

1. **Устройства не подключаются**
   - Проверьте сетевые настройки
   - Убедитесь, что агент запущен на устройстве
   - Проверьте firewall

2. **Ротация IP не работает**
   - Проверьте метод ротации в настройках
   - Убедитесь, что устройство поддерживает выбранный метод
   - Проверьте логи устройства

3. **Прокси не отвечает**
   - Проверьте статус прокси-сервера
   - Убедитесь, что есть доступные устройства
   - Проверьте конфигурацию прокси

### Логи

```bash
# Логи всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f backend

# Логи прокси-сервера
docker-compose logs -f backend | grep "proxy"
```

## 🔒 Безопасность

### Рекомендации

1. **Смените пароли по умолчанию**
2. **Используйте сильные секретные ключи**
3. **Настройте HTTPS для продакшена**
4. **Ограничьте доступ к API**
5. **Регулярно обновляйте систему**

### Настройка HTTPS

```bash
# Добавьте SSL сертификаты в nginx конфигурацию
# Обновите docker-compose.yml для использования HTTPS
```

## 📈 Мониторинг

### Метрики

Система собирает следующие метрики:

- Количество запросов в секунду
- Время отклика устройств
- Процент успешных запросов
- Частота ротации IP
- Статус устройств

### Алерты

Система может отправлять уведомления при:

- Отключении устройств
- Снижении успешности запросов
- Сбоях ротации IP

## 🤝 Поддержка

При возникновении проблем:

1. Проверьте документацию
2. Просмотрите логи системы
3. Создайте issue в репозитории
4. Обратитесь к разработчикам

## 📄 Лицензия

MIT License

## 🎯 Дорожная карта

- [ ] Поддержка больше типов устройств
- [ ] Геолокация IP адресов
- [ ] Расширенная аналитика
- [ ] Мобильное приложение для управления
- [ ] Интеграция с популярными парсерами
- [ ] Система уведомлений
- [ ] Бэкап и восстановление данных