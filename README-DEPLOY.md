# Развертывание Mobile Proxy Service на Ubuntu 24

[← Вернуться к общей документации](README.md)

Полная инструкция по настройке чистого Ubuntu 24 для работы с мобильным прокси-сервисом.

## 📋 Содержание

- [🚀 Подготовка системы](#-подготовка-системы)
- [📁 Клонирование и настройка проекта](#-клонирование-и-настройка-проекта)
- [🐳 Запуск инфраструктуры](#-запуск-инфраструктуры)
- [🚀 Запуск приложений](#-запуск-приложений)
- [🔍 Проверка работы системы](#-проверка-работы-системы)
- [🛠️ Дополнительные настройки](#️-дополнительные-настройки)
- [📊 Мониторинг и логи](#-мониторинг-и-логи)
- [🛑 Остановка и очистка](#-остановка-и-очистка)
- [🆘 Решение проблем](#-решение-проблем)

## 🚀 Подготовка системы

### 1. Обновление системы

```bash
# Обновление пакетов
sudo apt update && sudo apt upgrade -y

# Установка базовых инструментов
sudo apt install -y curl wget git htop nano vim unzip software-properties-common apt-transport-https ca-certificates gnupg lsb-release
```

### 2. Установка Docker и Docker Compose

```bash
# Удаление старых версий (если есть)
sudo apt remove -y docker docker-engine docker.io containerd runc

# Добавление официального GPG ключа Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавление официального репозитория Docker
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Добавление пользователя в группу docker
sudo usermod -aG docker $USER

# Перелогин или применение изменений
newgrp docker

# Проверка установки
docker --version
docker compose version
```

### 3. Установка Python 3.11+

```bash
# Установка Python и инструментов разработки
sudo apt install -y python3 python3-pip python3-venv python3-dev build-essential

# Проверка версии Python
python3 --version

# Если нужна более новая версия Python (опционально)
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
```

### 4. Установка Node.js и npm

```bash
# Установка NodeSource репозитория для последней LTS версии
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -

# Установка Node.js
sudo apt install -y nodejs

# Проверка установки
node --version
npm --version

# Обновление npm до последней версии
sudo npm install -g npm@latest
```

### 5. Установка дополнительных инструментов (для работы с модемами)

```bash
# Инструменты для работы с USB модемами
sudo apt install -y usb-modeswitch usb-modeswitch-data

# Инструменты для работы с Android устройствами (ОБЯЗАТЕЛЬНО для Android модемов)
sudo apt install -y android-tools-adb android-tools-fastboot

# Проверка установки ADB
adb version

# Инструменты мониторинга системы
sudo apt install -y htop iotop nethogs nmon

# Дополнительные пакеты для работы с сетевыми интерфейсами
sudo apt install -y net-tools iproute2 iputils-ping
```

**⚠️ Важно для Android устройств**: ADB (Android Debug Bridge) обязательно нужен для:
- Обнаружения подключенных Android устройств
- Выполнения команд ротации IP (`svc data disable/enable`)
- Получения информации о состоянии устройства
- Управления режимом полета (`airplane_mode`)

Без ADB система не сможет управлять Android устройствами как прокси!

### 6. Проверка настройки Android устройств

```bash
# Проверка доступности ADB
which adb
adb version

# Подключите Android устройство и проверьте
adb devices

# Если устройство не видно, проверьте:
# 1. Включена ли USB-отладка на телефоне
# 2. Разрешили ли отладку с этого компьютера (на телефоне появится запрос)
# 3. Правильно ли настроены udev правила

# Тест выполнения команд ротации
adb shell svc data disable
sleep 3
adb shell svc data enable

# Проверка доступности команд режима полета
adb shell settings put global airplane_mode_on 1
adb shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true
sleep 5
adb shell settings put global airplane_mode_on 0
adb shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false
```

### 1. Клонирование репозитория

```bash
# Переход в домашнюю директорию
cd ~

# Клонирование репозитория
git clone https://github.com/oracleh2/p-service.git

# Переход в директорию проекта
cd p-service

# Проверка содержимого
ls -la
```

### 2. Настройка файлов окружения

```bash
# Создание основного .env файла из примера
cp .env.example .env

# Редактирование основного файла окружения
nano .env
```

**Обязательные изменения в .env:**

```bash
# Измените секретные ключи на случайные строки
SECRET_KEY=your-very-long-random-secret-key-here-make-it-at-least-32-chars
JWT_SECRET_KEY=another-very-long-random-jwt-secret-key-at-least-32-chars

# Настройки базы данных (оставить как есть для локальной разработки)
DATABASE_URL=postgresql://proxy_user:proxy_password@localhost:5432/mobile_proxy

# Настройки Redis (оставить как есть)
REDIS_URL=redis://localhost:6379

# Настройки прокси
DEFAULT_ROTATION_INTERVAL=600
MAX_DEVICES=50
MAX_REQUESTS_PER_MINUTE=100

# Режим разработки
DEBUG=false
RELOAD=false
```

### 3. Настройка backend окружения

```bash
# Переход в директорию backend
cd backend

# Создание виртуального окружения
python3 -m venv venv

# Активация виртуального окружения
source venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt

# Создание .env файла для backend (если нужен отдельный)
cp ../.env .env

# Возврат в корень проекта
cd ..
```

### 4. Настройка frontend окружения

```bash
# Переход в директорию frontend
cd frontend

# Установка зависимостей
npm install

# Создание файла окружения для frontend
cat > .env.local << 'EOF'
VITE_API_BASE_URL=http://localhost:8000
VITE_DEV_MODE=true
EOF

# Возврат в корень проекта
cd ..
```

## 🐳 Запуск инфраструктуры

### 1. Создание недостающих конфигурационных файлов

```bash
# Запуск скрипта создания конфигураций
chmod +x fix-missing-configs.sh
./fix-missing-configs.sh
```

### 2. Запуск инфраструктурных сервисов

```bash
# Запуск Docker Compose сервисов
chmod +x start-dev.sh
./start-dev.sh
```

Этот скрипт запустит:
- PostgreSQL (порт 5432)
- Redis (порт 6379)  
- Prometheus (порт 9090)
- Grafana (порт 3001)

### 3. Проверка запуска сервисов

```bash
# Проверка статуса контейнеров
docker compose ps

# Проверка логов
docker compose logs -f

# Проверка подключения к PostgreSQL
docker compose exec postgres pg_isready -U proxy_user

# Проверка подключения к Redis
docker compose exec redis redis-cli ping
```

## 🚀 Запуск приложений

### 1. Запуск Backend (в отдельном терминале)

```bash
# Переход в директорию backend
cd backend

# Активация виртуального окружения
source venv/bin/activate

# Применение миграций базы данных
alembic upgrade head

# Запуск сервера разработки
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Запуск Frontend (в отдельном терминале)

```bash
# Переход в директорию frontend  
cd frontend

# Запуск сервера разработки
npm run dev
```

## 🔍 Проверка работы системы

### 1. Проверка API

```bash
# Проверка health endpoint
curl http://localhost:8000/health

# Проверка API документации
curl http://localhost:8000/docs
```

### 2. Проверка веб-интерфейса

Откройте в браузере:
- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs  
- **Grafana**: http://localhost:3001 (admin/admin123)
- **Prometheus**: http://localhost:9090

### 3. Проверка прокси-сервера

```bash
# Проверка прокси endpoint
curl http://localhost:8080/proxy/health
```

## 🛠️ Дополнительные настройки

### 1. Настройка firewall (опционально)

```bash
# Установка ufw
sudo apt install -y ufw

# Базовые правила
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Открытие нужных портов
sudo ufw allow ssh
sudo ufw allow 3000  # Frontend
sudo ufw allow 8000  # Backend API
sudo ufw allow 8080  # Proxy server
sudo ufw allow 3001  # Grafana
sudo ufw allow 9090  # Prometheus

# Включение firewall
sudo ufw enable
```

### 2. Настройка для работы с USB модемами

```bash
# Добавление пользователя в группы для работы с устройствами
sudo usermod -aG dialout $USER
sudo usermod -aG plugdev $USER

# Перелогин для применения изменений
newgrp dialout
newgrp plugdev

# Создание udev правил для автоматического обнаружения модемов
sudo tee /etc/udev/rules.d/99-usb-modems.rules << 'EOF'
# Huawei modems
SUBSYSTEM=="tty", ATTRS{idVendor}=="12d1", GROUP="dialout", MODE="0664"
# ZTE modems  
SUBSYSTEM=="tty", ATTRS{idVendor}=="19d2", GROUP="dialout", MODE="0664"
# Quectel modems
SUBSYSTEM=="tty", ATTRS{idVendor}=="2c7c", GROUP="dialout", MODE="0664"
EOF

# Перезагрузка udev правил
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 3. Настройка для работы с Android устройствами

```bash
# Создание правил для ADB
sudo tee /etc/udev/rules.d/51-android.rules << 'EOF'
# Google/Pixel devices
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"
# Samsung devices
SUBSYSTEM=="usb", ATTR{idVendor}=="04e8", MODE="0666", GROUP="plugdev"
# HTC devices
SUBSYSTEM=="usb", ATTR{idVendor}=="0bb4", MODE="0666", GROUP="plugdev"
# LG devices
SUBSYSTEM=="usb", ATTR{idVendor}=="1004", MODE="0666", GROUP="plugdev"
# Motorola devices
SUBSYSTEM=="usb", ATTR{idVendor}=="22b8", MODE="0666", GROUP="plugdev"
# Sony devices
SUBSYSTEM=="usb", ATTR{idVendor}=="0fce", MODE="0666", GROUP="plugdev"
# OnePlus devices
SUBSYSTEM=="usb", ATTR{idVendor}=="2a70", MODE="0666", GROUP="plugdev"
# Xiaomi devices
SUBSYSTEM=="usb", ATTR{idVendor}=="2717", MODE="0666", GROUP="plugdev"
# Huawei devices
SUBSYSTEM=="usb", ATTR{idVendor}=="12d1", MODE="0666", GROUP="plugdev"
EOF

sudo chmod a+r /etc/udev/rules.d/51-android.rules
sudo udevadm control --reload-rules

# Перезапуск ADB сервера
adb kill-server
adb start-server

# Проверка подключенных устройств
adb devices
```

**Важные шаги для настройки Android устройств:**

1. **На Android устройстве:**
   - Включите "Режим разработчика" (Settings → About → Build number - тапнуть 7 раз)
   - Включите "USB-отладку" (Settings → Developer options → USB debugging)
   - Включите "USB-модем" (Settings → Network → Mobile hotspot and tethering → USB tethering)

2. **Проверка подключения:**
   ```bash
   # Должно показать подключенное устройство
   adb devices
   
   # Проверка возможности выполнения команд
   adb shell svc data disable
   adb shell svc data enable
   ```

## 🔄 Настройка автоматического перезапуска

Для обеспечения постоянной работы backend и frontend с автоматическим перезапуском при падении рекомендуется использовать SystemD сервисы.

### Автоматическая настройка SystemD сервисов

```bash
# Сделать скрипт исполняемым
chmod +x setup-systemd-services.sh

# Запустить настройку (сборка frontend + создание сервисов)
./setup-systemd-services.sh
```

Этот скрипт автоматически:
- Соберет frontend для production
- Создаст SystemD сервисы для backend и frontend
- Включит автозапуск при загрузке системы
- Запустит сервисы
- Настроит автоматический перезапуск при падении

### Управление сервисами

```bash
# Просмотр статуса
sudo systemctl status mobile-proxy-backend.service
sudo systemctl status mobile-proxy-frontend.service

# Просмотр логов в реальном времени
sudo journalctl -u mobile-proxy-backend.service -f
sudo journalctl -u mobile-proxy-frontend.service -f

# Перезапуск сервисов
sudo systemctl restart mobile-proxy-backend.service
sudo systemctl restart mobile-proxy-frontend.service

# Остановка сервисов
sudo systemctl stop mobile-proxy-backend.service
sudo systemctl stop mobile-proxy-frontend.service
```

### Удаление SystemD сервисов

Если нужно вернуться к ручному запуску:

```bash
# Удаление сервисов
chmod +x remove-systemd-services.sh
./remove-systemd-services.sh
```

**Преимущества SystemD сервисов:**
- ✅ Автоматический запуск при загрузке системы
- ✅ Автоматический перезапуск при падении процесса
- ✅ Управление зависимостями (запуск после БД)
- ✅ Централизованное логирование через journald
- ✅ Интеграция с системным мониторингом

### 1. Просмотр логов

```bash
# Логи всех сервисов
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f postgres
docker compose logs -f redis

# Логи backend (в отдельном терминале с запущенным backend)
tail -f backend/logs/app.log

# Системные логи
sudo journalctl -f
```

### 2. Мониторинг ресурсов

```bash
# Мониторинг использования ресурсов
htop

# Мониторинг сетевой активности  
nethogs

# Мониторинг дискового I/O
iotop
```

## 🛑 Остановка и очистка

### 1. Остановка сервисов

```bash
# Остановка frontend/backend (Ctrl+C в соответствующих терминалах)

# Остановка Docker сервисов
./stop-dev.sh
# или
docker compose down
```

### 2. Полная очистка (при необходимости)

```bash
# Остановка и удаление всех контейнеров и данных
docker compose down -v

# Очистка неиспользуемых образов и контейнеров
docker system prune -af

# Удаление виртуального окружения Python
rm -rf backend/venv

# Удаление node_modules
rm -rf frontend/node_modules
```

## 🆘 Решение проблем

### 1. Проблемы с правами доступа

```bash
# Если Docker требует sudo
sudo usermod -aG docker $USER
newgrp docker

# Если проблемы с USB устройствами
sudo usermod -aG dialout $USER
sudo usermod -aG plugdev $USER
```

### 2. Проблемы с портами

```bash
# Проверка занятых портов
sudo netstat -tulpn | grep :8000
sudo netstat -tulpn | grep :3000

# Завершение процессов на портах
sudo fuser -k 8000/tcp
sudo fuser -k 3000/tcp
```

### 3. Проблемы с базой данных

```bash
# Пересоздание базы данных
docker compose down -v
docker compose up -d postgres
```

### 4. Проблемы с виртуальным окружением

```bash
# Пересоздание виртуального окружения
cd backend
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Проблемы с Node.js зависимостями

```bash
# Очистка кэша npm и переустановка
cd frontend
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

## 🔧 Автоматические скрипты

Проект включает несколько удобных скриптов для автоматизации:

### Доступные скрипты

- **`start-dev.sh`** - Запуск инфраструктурных сервисов для разработки
- **`stop-dev.sh`** - Остановка всех сервисов
- **`fix-missing-configs.sh`** - Создание недостающих конфигурационных файлов
- **`setup-backend-env.sh`** - Автоматическая настройка backend окружения

### Использование скриптов

```bash
# Сделать все скрипты исполняемыми
chmod +x *.sh

# Запуск инфраструктуры
./start-dev.sh

# Остановка сервисов
./stop-dev.sh

# Настройка backend окружения
./setup-backend-env.sh
```

## 📝 Заметки

- После выполнения всех шагов у вас будет полностью настроенная система для разработки и тестирования мобильного прокси-сервиса
- Для production развертывания рекомендуется использовать более безопасные настройки в файле `.env`
- Обязательно измените секретные ключи перед использованием в production
- Для работы с USB модемами может потребоваться дополнительная настройка в зависимости от модели устройства

---

[← Вернуться к общей документации](README.md)
