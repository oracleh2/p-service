#!/bin/bash
# fix-missing-configs.sh - Исправление отсутствующих конфигураций

echo "🔧 Создание отсутствующих конфигурационных файлов..."

# Остановка контейнеров
docker-compose down

# Создание директорий
mkdir -p monitoring/grafana/dashboards
mkdir -p monitoring/grafana/datasources
mkdir -p nginx/ssl
mkdir -p logs

# Создание конфигурации Prometheus
cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  # - "first_rules.yml"
  # - "second_rules.yml"

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'mobile-proxy-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'mobile-proxy-nginx'
    static_configs:
      - targets: ['nginx:80']
    metrics_path: '/metrics'
    scrape_interval: 30s
EOF

# Создание конфигурации источника данных Grafana
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

# Создание базового дашборда Grafana
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

# Создание основной конфигурации nginx если её нет
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
fi

echo "✅ Конфигурационные файлы созданы!"
echo ""
echo "📁 Созданные файлы:"
echo "  - monitoring/prometheus.yml"
echo "  - monitoring/grafana/datasources/prometheus.yml"
echo "  - monitoring/grafana/dashboards/dashboard.yml"
echo "  - nginx/nginx.conf (если не существовал)"
echo ""
echo "🚀 Теперь можно запустить Docker Compose:"
echo "  docker-compose up -d"
