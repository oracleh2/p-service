#!/bin/bash
# Отладка прокси с PM2 управлением

echo "🔍 Отладка прокси через PM2"
echo "============================"

# 1. Показываем текущий статус PM2
echo "1. Текущий статус PM2:"
pm2 status

echo ""
echo "2. Перезапуск backend для применения изменений..."
pm2 restart mobile-proxy-backend

# Ждем перезапуска
echo "Ожидание загрузки backend..."
sleep 8

# 2. Проверяем что backend запустился
echo ""
echo "3. Проверка запуска backend:"
pm2 list | grep mobile-proxy-backend

# 3. Мониторинг логов PM2 в фоне
echo ""
echo "4. Запуск мониторинга логов PM2..."
pm2 logs mobile-proxy-backend --lines 0 > /tmp/pm2_debug.log 2>&1 &
LOGS_PID=$!

# Также следим за логами в реальном времени
tail -f /var/www/p-service/logs/backend.log | grep -E "(PROXY|curl|interface|subprocess|SUCCESS|ERROR|FORCING)" &
TAIL_PID=$!

echo "Мониторинг запущен..."
sleep 3

# 4. Выполняем тестовый запрос
echo ""
echo "🚀 Выполнение тестового запроса..."
echo "Команда: curl -x http://192.168.1.50:8080 -H 'X-Proxy-Device-ID: android_AH3SCP4B11207250' http://httpbin.org/ip"
echo ""

RESULT=$(curl -x http://192.168.1.50:8080 -H "X-Proxy-Device-ID: android_AH3SCP4B11207250" -s --connect-timeout 15 http://httpbin.org/ip 2>&1)

echo "📤 Результат прокси-запроса:"
echo "$RESULT"

# Анализ результата
if echo "$RESULT" | jq . >/dev/null 2>&1; then
    IP=$(echo "$RESULT" | jq -r '.origin' 2>/dev/null)
    echo ""
    if [ "$IP" = "176.59.214.25" ]; then
        echo "🎉 УСПЕХ! Получен мобильный IP: $IP"
        echo "✅ Прокси корректно использует Android интерфейс"
    elif [ "$IP" = "178.178.91.162" ]; then
        echo "❌ ПРОБЛЕМА! Получен IP сервера: $IP"
        echo "   Прокси НЕ использует Android интерфейс"
    else
        echo "⚠️ Неожиданный IP: $IP"
    fi
else
    echo "❌ Некорректный ответ от прокси"
fi

# Останавливаем мониторинг
sleep 3
kill $LOGS_PID 2>/dev/null || true
kill $TAIL_PID 2>/dev/null || true

echo ""
echo "============================"
echo "5. Анализ логов PM2:"

# Показываем последние логи из PM2
echo ""
echo "📋 Последние логи backend (PM2):"
pm2 logs mobile-proxy-backend --lines 30 --nostream | tail -20

echo ""
echo "📋 Последние логи из файла:"
tail -30 /var/www/p-service/logs/backend.log | grep -E "(PROXY|curl|interface|subprocess|SUCCESS|ERROR|FORCING|android|Device)" | tail -15

echo ""
echo "============================"
echo "6. Диагностика:"

# Проверяем ключевые моменты в логах
LOG_FILE="/var/www/p-service/logs/backend-0.log"

if tail -50 "$LOG_FILE" | grep -q "PROXY REQUEST"; then
    echo "✅ Прокси получает запросы"
else
    echo "❌ Прокси НЕ получает запросы"
fi

if tail -50 "$LOG_FILE" | grep -q "SELECTED DEVICE"; then
    echo "✅ Устройство выбирается"

    SELECTED_DEVICE=$(tail -50 "$LOG_FILE" | grep "SELECTED DEVICE" | tail -1)
    echo "   $SELECTED_DEVICE"
else
    echo "❌ Устройство НЕ выбирается"
fi

if tail -50 "$LOG_FILE" | grep -q "ANDROID INTERFACE"; then
    echo "✅ Android интерфейс обнаружен"
else
    echo "❌ Android интерфейс НЕ обнаружен"
fi

if tail -50 "$LOG_FILE" | grep -q "FORCING CURL"; then
    echo "✅ curl команда запускается"

    if tail -50 "$LOG_FILE" | grep -q "curl SUCCESS"; then
        echo "✅ curl выполняется успешно"
    else
        echo "❌ curl НЕ выполняется успешно"
    fi
else
    echo "❌ curl команда НЕ запускается"
fi

if tail -50 "$LOG_FILE" | grep -q "FALLBACK"; then
    echo "⚠️ Используется fallback routing"
else
    echo "✅ Fallback НЕ используется"
fi

echo ""
echo "============================"
echo "7. Полезные команды:"
echo "   Мониторинг логов: pm2 logs mobile-proxy-backend"
echo "   Рестарт backend: pm2 restart mobile-proxy-backend"
echo "   Статус PM2: pm2 status"
echo "   Логи файл: tail -f /var/www/p-service/logs/backend.log"

echo ""
echo "🔧 Если проблема не решена, попробуйте:"
echo "1. pm2 restart mobile-proxy-backend"
echo "2. Проверьте что изменения в proxy_server.py применились"
echo "3. Убедитесь что метод force_curl_via_interface правильно работает"

# Дополнительная проверка - тестируем curl напрямую
echo ""
echo "============================"
echo "8. Контрольная проверка curl:"
echo "Выполняется: curl --interface enx566cf3eaaf4b -s http://httpbin.org/ip"

DIRECT_RESULT=$(curl --interface enx566cf3eaaf4b -s --connect-timeout 10 http://httpbin.org/ip 2>&1)
if echo "$DIRECT_RESULT" | jq . >/dev/null 2>&1; then
    DIRECT_IP=$(echo "$DIRECT_RESULT" | jq -r '.origin' 2>/dev/null)
    echo "✅ Прямой curl работает: $DIRECT_IP"

    if [ "$DIRECT_IP" = "$IP" ]; then
        echo "✅ IP совпадают - проблема решена!"
    else
        echo "❌ IP не совпадают - проблема в Python коде"
    fi
else
    echo "❌ Прямой curl не работает"
fi
