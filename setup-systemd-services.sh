#!/bin/bash
# setup-systemd-services.sh - Настройка SystemD сервисов для автозапуска

set -e

echo "🚀 Настройка SystemD сервисов для Mobile Proxy Service"
echo ""

# Определение доступной команды Docker Compose
DOCKER_COMPOSE_CMD=""

if command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
    echo "📦 Используется: docker-compose"
elif docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
    echo "📦 Используется: docker compose"
else
    echo "❌ Ошибка: Не найдена команда docker-compose или docker compose"
    echo "   Установите Docker Compose перед продолжением"
    exit 1
fi

echo ""

# Получение текущего пользователя и директории проекта
CURRENT_USER=$(whoami)
PROJECT_DIR=$(pwd)
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "👤 Пользователь: $CURRENT_USER"
echo "📁 Директория проекта: $PROJECT_DIR"
echo ""

# Проверка, что мы в правильной директории
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Пожалуйста, запустите скрипт из корня проекта (где находится docker-compose.yml)"
    exit 1
fi

# Проверка наличия виртуального окружения
if [ ! -f "$BACKEND_DIR/venv/bin/python" ]; then
    echo "❌ Виртуальное окружение не найдено в $BACKEND_DIR/venv/"
    echo "   Запустите сначала: ./setup-backend-env.sh"
    exit 1
fi

# Проверка наличия node_modules
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "❌ Node modules не найдены в $FRONTEND_DIR/"
    echo "   Запустите: cd frontend && npm install"
    exit 1
fi

# Сборка frontend для production
echo "🔨 Сборка frontend для production..."
cd "$FRONTEND_DIR"
npm run build
echo "✅ Frontend собран"
echo ""

cd "$PROJECT_DIR"

# Создание backend systemd сервиса
echo "📝 Создание systemd сервиса для Backend..."

sudo tee /etc/systemd/system/mobile-proxy-backend.service > /dev/null << EOF
[Unit]
Description=Mobile Proxy Service Backend
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$BACKEND_DIR
Environment=PATH=$BACKEND_DIR/venv/bin
ExecStart=$BACKEND_DIR/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mobile-proxy-backend

# Переменные окружения
EnvironmentFile=$PROJECT_DIR/.env

# Безопасность
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PROJECT_DIR
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Backend systemd сервис создан"

# Создание frontend systemd сервиса
echo "📝 Создание systemd сервиса для Frontend..."

sudo tee /etc/systemd/system/mobile-proxy-frontend.service > /dev/null << EOF
[Unit]
Description=Mobile Proxy Service Frontend
After=network.target mobile-proxy-backend.service
Wants=mobile-proxy-backend.service

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$FRONTEND_DIR
Environment=PATH=/usr/bin:/bin
Environment=NODE_ENV=production
ExecStart=/usr/bin/npm run preview -- --host 0.0.0.0 --port 3000
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mobile-proxy-frontend

# Переменные окружения
EnvironmentFile=$FRONTEND_DIR/.env.local

# Безопасность
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PROJECT_DIR
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Frontend systemd сервис создан"
echo ""

# Перезагрузка systemd
echo "🔄 Перезагрузка systemd..."
sudo systemctl daemon-reload
echo "✅ SystemD перезагружен"
echo ""

# Включение автозапуска сервисов
echo "🎯 Включение автозапуска сервисов..."
sudo systemctl enable mobile-proxy-backend.service
sudo systemctl enable mobile-proxy-frontend.service
echo "✅ Автозапуск включен"
echo ""

# Запуск сервисов
echo "▶️  Запуск сервисов..."
sudo systemctl start mobile-proxy-backend.service
sudo systemctl start mobile-proxy-frontend.service
echo "✅ Сервисы запущены"
echo ""

# Ожидание запуска
echo "⏳ Ожидание запуска сервисов..."
sleep 5

# Проверка статуса
echo "🔍 Проверка статуса сервисов..."
echo ""

echo "📡 Backend статус:"
sudo systemctl status mobile-proxy-backend.service --no-pager -l
echo ""

echo "🌐 Frontend статус:"
sudo systemctl status mobile-proxy-frontend.service --no-pager -l
echo ""

# Проверка доступности
echo "🔗 Проверка доступности сервисов..."

# Функция проверки HTTP сервиса
check_http_service() {
    local url=$1
    local name=$2
    local max_attempts=10
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$url" > /dev/null; then
            echo "✅ $name доступен: $url"
            return 0
        fi
        echo "⏳ Попытка $attempt/$max_attempts: $name недоступен, ожидание..."
        sleep 3
        attempt=$((attempt + 1))
    done

    echo "❌ $name недоступен после $max_attempts попыток: $url"
    return 1
}

check_http_service "http://localhost:8000/health" "Backend API"
check_http_service "http://localhost:3000" "Frontend"

echo ""
echo "🎉 Настройка SystemD сервисов завершена!"
echo ""
echo "📋 Полезные команды:"
echo ""
echo "🔍 Просмотр статуса:"
echo "  sudo systemctl status mobile-proxy-backend.service"
echo "  sudo systemctl status mobile-proxy-frontend.service"
echo ""
echo "📜 Просмотр логов:"
echo "  sudo journalctl -u mobile-proxy-backend.service -f"
echo "  sudo journalctl -u mobile-proxy-frontend.service -f"
echo ""
echo "🔄 Перезапуск сервисов:"
echo "  sudo systemctl restart mobile-proxy-backend.service"
echo "  sudo systemctl restart mobile-proxy-frontend.service"
echo ""
echo "🛑 Остановка сервисов:"
echo "  sudo systemctl stop mobile-proxy-backend.service"
echo "  sudo systemctl stop mobile-proxy-frontend.service"
echo ""
echo "❌ Отключение автозапуска:"
echo "  sudo systemctl disable mobile-proxy-backend.service"
echo "  sudo systemctl disable mobile-proxy-frontend.service"
echo ""
echo "🌐 Доступные сервисы:"
echo "  Backend API: http://localhost:8000"
echo "  Frontend:    http://localhost:3000"
echo "  API Docs:    http://localhost:8000/docs"
echo ""
echo "✅ Сервисы будут автоматически запускаться при загрузке системы"
echo "✅ При падении процессы будут автоматически перезапускаться"
echo ""
echo "💡 Используемая команда Docker Compose: $DOCKER_COMPOSE_CMD"
