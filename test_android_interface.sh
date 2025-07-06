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
