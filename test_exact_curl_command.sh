#!/bin/bash
# Тестирование точной curl команды из логов backend

INTERFACE="enx566cf3eaaf4b"
echo "🧪 Тестирование точной curl команды из логов backend"
echo "=================================================="

# 1. Точная команда из логов
echo "1. Точная команда из логов backend:"
echo "curl --interface $INTERFACE --silent --show-error --fail-with-body --max-time 30 --connect-timeout 10 --location --compressed --header 'Accept: application/json, text/plain, */*' --header 'User-Agent: Mobile-Proxy-Interface/1.0' --write-out '\\nHTTPSTATUS:%{http_code}\\nTIME:%{time_total}\\n' http://httpbin.org/ip"

echo ""
echo "🔧 Выполнение..."
RESULT=$(curl --interface $INTERFACE --silent --show-error --fail-with-body --max-time 30 --connect-timeout 10 --location --compressed --header "Accept: application/json, text/plain, */*" --header "User-Agent: Mobile-Proxy-Interface/1.0" --write-out "\nHTTPSTATUS:%{http_code}\nTIME:%{time_total}\n" http://httpbin.org/ip 2>&1)
EXIT_CODE=$?

echo "Exit code: $EXIT_CODE"
echo "Full result:"
echo "$RESULT"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Команда выполнилась успешно"

    # Парсим результат как в Python коде
    echo ""
    echo "📋 Парсинг результата (как в Python):"

    # Ищем HTTP статус
    if echo "$RESULT" | grep -q "HTTPSTATUS:"; then
        STATUS=$(echo "$RESULT" | grep "HTTPSTATUS:" | cut -d: -f2)
        echo "HTTP Status: $STATUS"
    fi

    # Ищем время
    if echo "$RESULT" | grep -q "TIME:"; then
        TIME=$(echo "$RESULT" | grep "TIME:" | cut -d: -f2)
        echo "Time: ${TIME}s"
    fi

    # Извлекаем JSON (убираем строки с метаданными)
    JSON_BODY=$(echo "$RESULT" | grep -v "HTTPSTATUS:" | grep -v "TIME:" | grep -v "^$")
    echo "JSON Body: $JSON_BODY"

    # Проверяем валидность JSON
    if echo "$JSON_BODY" | jq . >/dev/null 2>&1; then
        echo "✅ JSON валиден"
        IP=$(echo "$JSON_BODY" | jq -r '.origin')
        echo "🌐 IP адрес: $IP"

        if [ "$IP" = "176.59.214.25" ]; then
            echo "🎉 ОТЛИЧНО! Получен правильный мобильный IP"
        else
            echo "⚠️ Неожиданный IP: $IP"
        fi
    else
        echo "❌ JSON невалиден"
    fi

else
    echo "❌ Команда завершилась с ошибкой"
    echo "Вероятная причина ошибки:"

    if echo "$RESULT" | grep -q "Network is unreachable"; then
        echo "  - Сеть недоступна через интерфейс"
    elif echo "$RESULT" | grep -q "Could not resolve host"; then
        echo "  - Проблема с DNS через интерфейс"
    elif echo "$RESULT" | grep -q "Connection timed out"; then
        echo "  - Таймаут подключения"
    elif echo "$RESULT" | grep -q "No route to host"; then
        echo "  - Нет маршрута к хосту"
    else
        echo "  - Другая ошибка"
    fi
fi

echo ""
echo "=================================================="
echo "2. Упрощенная версия для сравнения:"
echo "curl --interface $INTERFACE -s --max-time 10 http://httpbin.org/ip"

echo ""
echo "🔧 Выполнение упрощенной версии..."
SIMPLE_RESULT=$(curl --interface $INTERFACE -s --max-time 10 http://httpbin.org/ip 2>&1)
SIMPLE_EXIT=$?

echo "Exit code: $SIMPLE_EXIT"
echo "Result: $SIMPLE_RESULT"

if [ $SIMPLE_EXIT -eq 0 ]; then
    echo "✅ Упрощенная команда работает"
    SIMPLE_IP=$(echo "$SIMPLE_RESULT" | jq -r '.origin' 2>/dev/null)
    echo "🌐 IP: $SIMPLE_IP"
else
    echo "❌ Упрощенная команда тоже не работает"
fi

echo ""
echo "=================================================="
echo "💡 ДИАГНОСТИКА ИНТЕРФЕЙСА:"

echo ""
echo "📊 Информация об интерфейсе:"
ip addr show $INTERFACE

echo ""
echo "🛣️ Маршруты через интерфейс:"
ip route show dev $INTERFACE

echo ""
echo "🌐 Попытка ping через интерфейс:"
ping -I $INTERFACE -c 2 -W 5 8.8.8.8

echo ""
echo "🔍 DNS тест через интерфейс:"
nslookup httpbin.org

echo ""
echo "=================================================="
echo "🎯 ЗАКЛЮЧЕНИЕ:"

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ curl команда из backend работает правильно"
    echo "   ПРОБЛЕМА В PYTHON КОДЕ - обработка результата curl"
    echo ""
    echo "🔧 Что нужно исправить в Python:"
    echo "1. Проверить обработку stdout в asyncio.subprocess"
    echo "2. Убедиться что process.communicate() не теряет данные"
    echo "3. Добавить больше логирования в Python код"
else
    echo "❌ curl команда НЕ работает"
    echo "   ПРОБЛЕМА В СЕТЕВОЙ КОНФИГУРАЦИИ"
    echo ""
    echo "🔧 Что нужно исправить:"
    echo "1. Проверить маршрутизацию интерфейса"
    echo "2. Проверить DNS через интерфейс"
    echo "3. Возможно нужно добавить default route для интерфейса"
fi


