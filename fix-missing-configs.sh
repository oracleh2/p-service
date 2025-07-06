#!/bin/bash
# fix-missing-configs.sh - Создание недостающих конфигурационных файлов

set -e

echo "📁 Создание недостающих конфигурационных файлов..."
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

# Создание prometheus.yml
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

# Создание Grafana datasource
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

# Создание Grafana dashboard provider
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

# Создание nginx.conf если его нет
mkdir -p nginx
if [ ! -f nginx/nginx.conf ]; then
cat > nginx/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;

    # Upstream for backend API
    upstream backend_api {
        server backend:8000;
    }

    # Upstream for frontend
    upstream frontend_app {
        server frontend:3000;
    }

    # Main server block
    server {
        listen 80;
        server_name localhost;

        # Proxy for API requests
        location /api/ {
            proxy_pass http://backend_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Proxy for frontend
        location / {
            proxy_pass http://frontend_app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }

    # Proxy server for mobile traffic
    server {
        listen 8080;
        server_name localhost;

        location / {
            proxy_pass http://backend_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
EOF
echo "✅ nginx/nginx.conf создан"
fi

echo ""
echo "✅ Конфигурационные файлы созданы!"
echo ""
echo "📁 Созданные файлы:"
echo "  - monitoring/prometheus.yml"
echo "  - monitoring/grafana/datasources/prometheus.yml"
echo "  - monitoring/grafana/dashboards/dashboard.yml"
echo "  - nginx/nginx.conf (если не существовал)"
echo ""
echo "🚀 Теперь можно запустить Docker Compose:"
echo "  $DOCKER_COMPOSE_CMD up -d"
echo ""
echo "💡 Используемая команда Docker Compose: $DOCKER_COMPOSE_CMD"
