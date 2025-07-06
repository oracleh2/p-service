#!/bin/bash
# remove-systemd-services.sh - Удаление SystemD сервисов

set -e

echo "🗑️  Удаление SystemD сервисов Mobile Proxy Service"
echo ""

# Остановка сервисов
echo "🛑 Остановка сервисов..."
sudo systemctl stop mobile-proxy-backend.service 2>/dev/null || echo "Backend сервис уже остановлен"
sudo systemctl stop mobile-proxy-frontend.service 2>/dev/null || echo "Frontend сервис уже остановлен"
echo "✅ Сервисы остановлены"
echo ""

# Отключение автозапуска
echo "❌ Отключение автозапуска..."
sudo systemctl disable mobile-proxy-backend.service 2>/dev/null || echo "Backend автозапуск уже отключен"
sudo systemctl disable mobile-proxy-frontend.service 2>/dev/null || echo "Frontend автозапуск уже отключен"
echo "✅ Автозапуск отключен"
echo ""

# Удаление файлов сервисов
echo "🗂️  Удаление файлов сервисов..."
sudo rm -f /etc/systemd/system/mobile-proxy-backend.service
sudo rm -f /etc/systemd/system/mobile-proxy-frontend.service
echo "✅ Файлы сервисов удалены"
echo ""

# Перезагрузка systemd
echo "🔄 Перезагрузка systemd..."
sudo systemctl daemon-reload
echo "✅ SystemD перезагружен"
echo ""

echo "✅ SystemD сервисы успешно удалены!"
echo ""
echo "📋 Для запуска приложений вручную используйте:"
echo ""
echo "Backend:"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "Frontend:"
echo "  cd frontend"
echo "  npm run dev"
