#!/bin/bash
# start-dev.sh - Скрипт для запуска в режиме разработки

set -e

echo "🚀 Запуск Mobile Proxy Service в режиме разработки"
echo ""

# Функция для проверки доступности порта
check_port() {
    local port=$1
    local service=$2
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null; then
        echo "⚠️  Порт $port уже занят ($service)"
        return 1
    fi
    return 0
}

# Функция для ожидания готовности сервиса
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1

    echo "⏳ Ожидание готовности $service_name..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "✅ $service_name готов"
            return 0
        fi

        echo "   Попытка $attempt/$max_attempts..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "❌ $service_name не отвечает после $max_attempts попыток"
    return 1
}

# Проверяем, что нужные порты свободны для backend/frontend
echo "🔍 Проверка доступности портов..."
backend_port_free=true
frontend_port_free=true

if ! check_port 8000 "Backend"; then
    backend_port_free=false
fi

if ! check_port 3000 "Frontend"; then
    frontend_port_free=false
fi

# Создаем необходимые конфигурационные файлы
echo "📁 Создание конфигурационных файлов..."

# Создаем prometheus.yml если его нет
mkdir -p monitoring
if [ ! -f monitoring/prometheus.yml ]; then
cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'mobile-proxy-backend'
    static_configs:
      - targets: ['host.docker.internal:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'mobile-proxy-frontend'
    static_configs:
      - targets: ['host.docker.internal:3000']
    metrics_path: '/metrics'
    scrape_interval: 30s
EOF
echo "✅ monitoring/prometheus.yml создан"
fi

# Создаем Grafana datasource
mkdir -p monitoring/grafana/datasources
if [ ! -f monitoring/grafana/datasources/prometheus.yml ]; then
cat > monitoring/grafana/datasources/prometheus.yml << 'EOF'
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
EOF
echo "✅ monitoring/grafana/datasources/prometheus.yml создан"
fi

# Создаем Grafana dashboard provider
mkdir -p monitoring/grafana/dashboards
if [ ! -f monitoring/grafana/dashboards/dashboard.yml ]; then
cat > monitoring/grafana/dashboards/dashboard.yml << 'EOF'
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    editable: true
    options:
      path: /etc/grafana/provisioning/dashboards
EOF
echo "✅ monitoring/grafana/dashboards/dashboard.yml создан"
fi

# Создаем .env файл если его нет
if [ ! -f .env ]; then
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://proxy_user:proxy_password@localhost:5432/mobile_proxy

# Redis
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY=your-secret-key-change-in-production
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production

# Proxy settings
DEFAULT_ROTATION_INTERVAL=600
MAX_DEVICES=50
MAX_REQUESTS_PER_MINUTE=100

# Grafana
GRAFANA_ADMIN_PASSWORD=admin123

# Development
DEBUG=true
RELOAD=true
EOF
echo "✅ .env создан"
fi

# Запуск инфраструктурных сервисов
echo ""
echo "🐳 Запуск инфраструктурных сервисов..."
docker-compose -f docker-compose.yml up -d

# Ожидание готовности сервисов
echo ""
echo "⏳ Ожидание готовности сервисов..."

wait_for_service "http://localhost:5432" "PostgreSQL" &
wait_for_service "http://localhost:6379" "Redis" &
wait_for_service "http://localhost:9090" "Prometheus" &
wait_for_service "http://localhost:3001" "Grafana" &

wait

echo ""
echo "📊 Статус контейнеров:"
docker-compose -f docker-compose.yml ps

echo ""
echo "🔧 Инструкции для запуска Backend и Frontend:"
echo ""

if [ "$backend_port_free" = true ]; then
    echo "📡 Backend (FastAPI):"
    echo "   cd backend"
    echo "   pip install -r requirements.txt"
    echo "   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    echo "   Будет доступен на: http://localhost:8000"
    echo ""
else
    echo "⚠️  Backend порт 8000 занят. Остановите процесс или используйте другой порт."
fi

if [ "$frontend_port_free" = true ]; then
    echo "🌐 Frontend (Vue.js):"
    echo "   cd frontend"
    echo "   npm install"
    echo "   npm run dev"
    echo "   Будет доступен на: http://localhost:3000"
    echo ""
else
    echo "⚠️  Frontend порт 3000 занят. Остановите процесс или используйте другой порт."
fi

echo "🔗 Доступные сервисы:"
echo "   PostgreSQL:  localhost:5432 (proxy_user/proxy_password)"
echo "   Redis:       localhost:6379"
echo "   Prometheus:  http://localhost:9090"
echo "   Grafana:     http://localhost:3001 (admin/admin123)"
echo ""

echo "🛠️  Дополнительные инструменты (опционально):"
echo "   docker-compose -f docker-compose.yml --profile tools up -d"
echo "   Adminer:           http://localhost:8080 (для управления БД)"
echo "   Redis Commander:   http://localhost:8081 (для управления Redis)"
echo ""

echo "🛑 Для остановки сервисов:"
echo "   docker-compose -f docker-compose.yml down"
echo ""

echo "📋 Полезные команды:"
echo "   docker-compose -f docker-compose.yml logs -f        # Логи всех сервисов"
echo "   docker-compose -f docker-compose.yml logs postgres  # Логи PostgreSQL"
echo "   docker-compose -f docker-compose.yml restart        # Перезапуск сервисов"
echo ""

echo "✅ Инфраструктурные сервисы запущены! Теперь запустите Backend и Frontend вручную."

