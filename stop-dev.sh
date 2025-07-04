#!/bin/bash
# stop-dev.sh - Остановка инфраструктурных сервисов

echo "🛑 Остановка инфраструктурных сервисов..."

# Остановка контейнеров
docker-compose -f docker-compose-min.yml down

echo ""
echo "📊 Статус после остановки:"
docker-compose -f docker-compose-min.yml ps

echo ""
echo "💡 Backend и Frontend остановите вручную:"
echo "   Ctrl+C в терминалах где они запущены"
echo ""

echo "🧹 Для полной очистки (удаление данных):"
echo "   docker-compose -f docker-compose-min.yml down -v"
echo "   docker system prune -f"
echo ""

echo "✅ Инфраструктурные сервисы остановлены!"
