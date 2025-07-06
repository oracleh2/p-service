#!/bin/bash
# stop-dev.sh - Универсальный скрипт для остановки сервисов разработки

set -e

echo "🛑 Остановка Mobile Proxy Service (режим разработки)"
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
    echo "   Возможно, Docker не установлен или сервисы уже остановлены"
    exit 1
fi

echo ""

# Проверка наличия docker-compose.yml
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Файл docker-compose.yml не найден в текущей директории"
    echo "   Пожалуйста, запустите скрипт из корня проекта"
    exit 1
fi

# Остановка сервисов
echo "🐳 Остановка инфраструктурных сервисов..."
$DOCKER_COMPOSE_CMD -f docker-compose.yml down

echo ""
echo "📊 Проверка статуса контейнеров..."
$DOCKER_COMPOSE_CMD -f docker-compose.yml ps

echo ""
echo "🧹 Дополнительные команды очистки (опционально):"
echo ""
echo "   Удалить все контейнеры и данные:"
echo "   $DOCKER_COMPOSE_CMD -f docker-compose.yml down -v"
echo ""
echo "   Очистить неиспользуемые образы:"
echo "   docker system prune -f"
echo ""
echo "   Полная очистка Docker:"
echo "   docker system prune -af --volumes"
echo ""

# Проверка занятых портов
echo "🔍 Проверка портов после остановки:"

check_port_status() {
    local port=$1
    local service=$2
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "   ⚠️  Порт $port все еще занят ($service)"
        local pid=$(lsof -Pi :$port -sTCP:LISTEN -t)
        echo "      PID: $pid"
        echo "      Для принудительного завершения: kill -9 $pid"
    else
        echo "   ✅ Порт $port свободен ($service)"
    fi
}

check_port_status "5432" "PostgreSQL"
check_port_status "6379" "Redis"
check_port_status "9090" "Prometheus"
check_port_status "3001" "Grafana"
check_port_status "8000" "Backend (если запущен)"
check_port_status "3000" "Frontend (если запущен)"

echo ""
echo "✅ Инфраструктурные сервисы остановлены!"
echo ""
echo "💡 Для перезапуска используйте: ./start-dev.sh"
echo "💡 Используемая команда Docker Compose: $DOCKER_COMPOSE_CMD"
