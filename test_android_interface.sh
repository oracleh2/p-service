#!/bin/bash
# Тестирование Android интерфейса enx566cf3eaaf4b

INTERFACE="enx566cf3eaaf4b"
echo "🧪 Тестирование Android интерфейса $INTERFACE"
echo "=============================================="

# 1. Проверка существования интерфейса
echo "1. Проверка интерфейса:"
if ip link show $INTERFACE &>/dev/null; then
    echo "✅ Интерфейс $INTERFACE найден"
    ip addr show $INTERFACE | grep "inet "
else
    echo "❌ Интерфейс $INTERFACE не найден"
    exit 1
fi
echo ""

# 2. Проверка состояния интерфейса
echo "2. Состояние интерфейса:"
STATE=$(ip link show $INTERFACE | grep -o "state [A-Z]*" | cut -d' ' -f2)
echo "Состояние: $STATE"

if [ "$STATE" != "UP" ]; then
    echo "⚠️ Интерфейс не в состоянии UP, попытка поднять..."
    sudo ip link set $INTERFACE up
    sleep 2
fi
echo ""

# 3. Прямой тест через curl
echo "3. Тест запроса через интерфейс:"
echo "Выполняется: curl --interface $INTERFACE http://httpbin.org/ip"

RESULT=$(curl --interface $INTERFACE -s --connect-timeout 10 http://httpbin.org/ip 2>&1)
if [ $? -eq 0 ]; then
    echo "✅ Прямой запрос успешен:"
    echo "$RESULT" | jq . 2>/dev/null || echo "$RESULT"

    # Извлекаем IP
    EXTERNAL_IP=$(echo "$RESULT" | jq -r '.origin' 2>/dev/null || echo "unknown")
    echo "🌐 Внешний IP через интерфейс: $EXTERNAL_IP"
else
    echo "❌ Прямой запрос неудачен:"
    echo "$RESULT"
fi
echo ""

# 4. Тест через прокси
echo "4. Тест запроса через прокси:"
echo "Выполняется: curl -x http://192.168.1.50:8080 http://httpbin.org/ip"

PROXY_RESULT=$(curl -x http://192.168.1.50:8080 -s --connect-timeout 10 http://httpbin.org/ip 2>&1)
if [ $? -eq 0 ]; then
    echo "✅ Прокси запрос успешен:"
    echo "$PROXY_RESULT" | jq . 2>/dev/null || echo "$PROXY_RESULT"

    # Извлекаем IP
    PROXY_IP=$(echo "$PROXY_RESULT" | jq -r '.origin' 2>/dev/null || echo "unknown")
    echo "🌐 Внешний IP через прокси: $PROXY_IP"

    # Сравниваем IP
    if [ "$EXTERNAL_IP" = "$PROXY_IP" ] && [ "$EXTERNAL_IP" != "unknown" ]; then
        echo "🎉 УСПЕХ! Прокси использует Android интерфейс"
    elif [ "$PROXY_IP" = "178.178.91.162" ]; then
        echo "❌ ПРОБЛЕМА! Прокси использует основной интерфейс сервера"
        echo "   Нужно исправить конфигурацию прокси-сервера"
    else
        echo "⚠️ IP адреса различаются:"
        echo "   Интерфейс: $EXTERNAL_IP"
        echo "   Прокси: $PROXY_IP"
    fi
else
    echo "❌ Прокси запрос неудачен:"
    echo "$PROXY_RESULT"
fi
echo ""

# 5. Проверка статуса прокси
echo "5. Статус прокси-сервера:"
PROXY_STATUS=$(curl -s http://192.168.1.50:8080/status 2>&1)
if [ $? -eq 0 ]; then
    echo "$PROXY_STATUS" | jq '.device_interfaces[] | select(.interface == "'$INTERFACE'")' 2>/dev/null || echo "Интерфейс не найден в статусе"
else
    echo "❌ Не удалось получить статус прокси"
fi
echo ""

# 6. Информация о маршрутизации
echo "6. Маршрутизация через интерфейс:"
ip route show dev $INTERFACE
echo ""

echo "=============================================="
echo "Тестирование завершено"

# Выводим заключение
if [ "$EXTERNAL_IP" = "$PROXY_IP" ] && [ "$EXTERNAL_IP" != "unknown" ]; then
    echo "🎉 СТАТУС: ВСЕ РАБОТАЕТ ПРАВИЛЬНО"
    echo "   Прокси корректно использует Android интерфейс"
else
    echo "❌ СТАТУС: ТРЕБУЕТСЯ ИСПРАВЛЕНИЕ"
    echo "   Прокси НЕ использует Android интерфейс"
    echo ""
    echo "Возможные причины:"
    echo "1. Код прокси-сервера не обновлен"
    echo "2. Прокси-сервер не перезапущен после изменений"
    echo "3. Ошибка в логике выбора интерфейса"
    echo ""
    echo "Проверьте логи backend для диагностики"
fi


# Диагностика backend и проверка логов

echo "🔍 Диагностика проблемы с прокси-сервером"
echo "=========================================="

# 1. Проверяем запущен ли backend
echo "1. Проверка процессов backend:"
ps aux | grep -E "(python.*app\.main|uvicorn|fastapi)" | grep -v grep
echo ""

# 2. Проверяем порты
echo "2. Проверка портов:"
netstat -tlnp | grep -E ":(8000|8080)"
echo ""

# 3. Проверяем доступность API
echo "3. Проверка API backend:"
curl -s http://192.168.1.50:8000/health | head -5
echo ""

# 4. Проверяем список устройств
echo "4. Проверка списка устройств:"
curl -s http://192.168.1.50:8000/admin/modems | jq '.[] | {id, type, interface, status}' 2>/dev/null || echo "Ошибка получения списка устройств"
echo ""

# 5. Тестируем прокси с диагностикой
echo "5. Тест прокси с заголовками диагностики:"
curl -x http://192.168.1.50:8080 -H "X-Proxy-Device-ID: android_AH3SCP4B11207250" -v http://httpbin.org/ip 2>&1 | head -20
echo ""

# 6. Проверяем статус прокси-сервера
echo "6. Статус прокси-сервера:"
curl -s http://192.168.1.50:8080/status | jq . 2>/dev/null || curl -s http://192.168.1.50:8080/status
echo ""

# 7. Проверяем корневой путь прокси
echo "7. Информация о прокси:"
curl -s http://192.168.1.50:8080/ | jq . 2>/dev/null || curl -s http://192.168.1.50:8080/
echo ""

# 8. Поиск логов
echo "8. Поиск файлов логов:"
find /var/www/p-service -name "*.log" -o -name "backend.log" 2>/dev/null
find /tmp -name "*proxy*" -o -name "*backend*" 2>/dev/null | head -5
find . -name "*.log" 2>/dev/null

echo ""
echo "=========================================="
echo "Для диагностики запустите backend в режиме отладки:"
echo "cd /var/www/p-service/backend"
echo "python -m app.main"
echo "И отследите логи при выполнении тестового запроса"


