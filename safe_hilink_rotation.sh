#!/bin/bash

# БЕЗОПАСНАЯ РОТАЦИЯ IP ЧЕРЕЗ HILINK API
# Этот метод НЕ использует AT команды и не ломает сетевую конфигурацию

MODEM_IP="192.168.108.1"
INTERFACE="enx0c5b8f279a64"

echo "🔒 БЕЗОПАСНАЯ РОТАЦИЯ IP ЧЕРЕЗ HILINK API"
echo "========================================"
echo "⚠️  Не используем AT команды - только веб-API!"

# Функция для HiLink API запросов
hilink_api_request() {
    local url="$1"
    local method="$2"
    local data="$3"

    if [ "$method" = "GET" ]; then
        curl -s -m 10 "http://$MODEM_IP$url" 2>/dev/null
    else
        curl -s -m 10 -X "$method" -d "$data" "http://$MODEM_IP$url" 2>/dev/null
    fi
}

# Функция получения внешнего IP
get_external_ip() {
    curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"'
}

# Функция получения токена сессии
get_session_token() {
    local response=$(hilink_api_request "/api/webserver/SesTokInfo" "GET")

    if [ -n "$response" ]; then
        local session_id=$(echo "$response" | grep -o '<SesInfo>[^<]*</SesInfo>' | sed 's/<[^>]*>//g')
        local token=$(echo "$response" | grep -o '<TokInfo>[^<]*</TokInfo>' | sed 's/<[^>]*>//g')

        if [ -n "$session_id" ] && [ -n "$token" ]; then
            echo "$session_id|$token"
            return 0
        fi
    fi

    return 1
}

echo ""
echo "1. Сначала восстанавливаем модем физически"
echo "=========================================="
echo "🔌 ПЕРЕД ПРОДОЛЖЕНИЕМ:"
echo "1. Выдерни USB модем из порта"
echo "2. Подожди 5 секунд"
echo "3. Вставь модем обратно"
echo "4. Подожди 30 секунд пока модем загрузится"
echo ""

read -p "Модем переподключен и готов? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Переподключи модем и запусти скрипт заново"
    exit 1
fi

echo ""
echo "2. Проверка доступности модема"
echo "=============================="

# Проверяем доступность веб-интерфейса
echo "🔍 Проверка веб-интерфейса..."
if ! curl -s -m 5 "http://$MODEM_IP" >/dev/null 2>&1; then
    echo "❌ Веб-интерфейс модема недоступен"
    echo "🔧 Проверь:"
    echo "   - Модем правильно подключен"
    echo "   - Интерфейс $INTERFACE активен"
    echo "   - IP адрес 192.168.108.1 доступен"
    exit 1
fi

echo "✅ Веб-интерфейс доступен"

# Проверяем интернет
echo "🌐 Проверка интернета..."
CURRENT_IP=$(get_external_ip)
if [ -z "$CURRENT_IP" ]; then
    echo "❌ Интернет недоступен через модем"
    echo "🔧 Подожди еще немного пока модем полностью загрузится"
    exit 1
fi

echo "✅ Интернет работает, текущий IP: $CURRENT_IP"

echo ""
echo "3. Безопасная ротация IP через HiLink API"
echo "========================================"

# Получаем токен сессии
echo "🔑 Получение токена сессии..."
SESSION_TOKEN=$(get_session_token)

if [ -z "$SESSION_TOKEN" ]; then
    echo "❌ Не удалось получить токен сессии"
    echo "🔧 Возможно, модем не поддерживает API или требует авторизацию"
    exit 1
fi

IFS='|' read -r SESSION_ID TOKEN <<< "$SESSION_TOKEN"
echo "✅ Токен получен"

# Метод 1: Отключение/подключение через dial API
echo ""
echo "🔄 Метод 1: Отключение/подключение соединения"
echo "=============================================="

echo "📤 Отключение соединения..."
disconnect_response=$(curl -s -m 10 -X POST \
    -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
    -H "Cookie: SessionID=$SESSION_ID" \
    -H "__RequestVerificationToken: $TOKEN" \
    -d '<?xml version="1.0" encoding="UTF-8"?><request><Action>0</Action></request>' \
    "http://$MODEM_IP/api/dialup/dial" 2>/dev/null)

echo "📋 Результат отключения:"
echo "$disconnect_response"

echo "⏳ Ожидание 10 секунд..."
sleep 10

echo "📤 Подключение соединения..."
connect_response=$(curl -s -m 10 -X POST \
    -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
    -H "Cookie: SessionID=$SESSION_ID" \
    -H "__RequestVerificationToken: $TOKEN" \
    -d '<?xml version="1.0" encoding="UTF-8"?><request><Action>1</Action></request>' \
    "http://$MODEM_IP/api/dialup/dial" 2>/dev/null)

echo "📋 Результат подключения:"
echo "$connect_response"

echo "⏳ Ожидание восстановления соединения (20 секунд)..."
sleep 20

# Проверяем новый IP
echo "🔍 Проверка нового IP..."
NEW_IP_1=$(get_external_ip)
echo "📋 IP после метода 1: $NEW_IP_1"

if [ "$NEW_IP_1" != "$CURRENT_IP" ] && [ -n "$NEW_IP_1" ]; then
    echo "🎉 УСПЕХ! IP изменился: $CURRENT_IP → $NEW_IP_1"
    echo "✅ Метод HiLink API работает!"

    # Сохраняем рабочий метод
    echo ""
    echo "💾 Сохранение рабочего метода..."
    cat > hilink_rotation_method.txt << EOF
РАБОЧИЙ МЕТОД РОТАЦИИ IP:
========================
Метод: HiLink API dial
URL: http://$MODEM_IP/api/dialup/dial
Отключение: Action=0
Подключение: Action=1
Токен: Требуется получать каждый раз
Время ожидания: 10 сек между операциями + 20 сек на восстановление
Результат: IP изменился с $CURRENT_IP на $NEW_IP_1

КОМАНДЫ ДЛЯ PYTHON:
==================
1. GET /api/webserver/SesTokInfo → получить токен
2. POST /api/dialup/dial + Action=0 → отключить
3. sleep(10)
4. POST /api/dialup/dial + Action=1 → подключить
5. sleep(20)
6. Проверить новый IP
EOF

    echo "✅ Метод сохранен в hilink_rotation_method.txt"

else
    echo "⚠️ IP не изменился или не получен"
    echo "🔧 Попробуем альтернативный метод..."

    # Метод 2: Перезагрузка модема через API
    echo ""
    echo "🔄 Метод 2: Перезагрузка модема через API"
    echo "========================================"

    echo "🔄 Отправка команды перезагрузки..."
    reboot_response=$(curl -s -m 10 -X POST \
        -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
        -H "Cookie: SessionID=$SESSION_ID" \
        -H "__RequestVerificationToken: $TOKEN" \
        -d '<?xml version="1.0" encoding="UTF-8"?><request><Control>1</Control></request>' \
        "http://$MODEM_IP/api/device/control" 2>/dev/null)

    echo "📋 Результат перезагрузки:"
    echo "$reboot_response"

    echo "⏳ Ожидание перезагрузки модема (45 секунд)..."
    sleep 45

    # Проверяем IP после перезагрузки
    echo "🔍 Проверка IP после перезагрузки..."
    NEW_IP_2=$(get_external_ip)
    echo "📋 IP после метода 2: $NEW_IP_2"

    if [ "$NEW_IP_2" != "$CURRENT_IP" ] && [ -n "$NEW_IP_2" ]; then
        echo "🎉 УСПЕХ! IP изменился после перезагрузки: $CURRENT_IP → $NEW_IP_2"
        echo "✅ Метод перезагрузки работает!"
    else
        echo "⚠️ IP не изменился даже после перезагрузки"
        echo "🔧 Возможные причины:"
        echo "   - Оператор не меняет IP при переподключении"
        echo "   - Модем получает тот же IP от DHCP сервера оператора"
        echo "   - Нужно больше времени"
    fi
fi

echo ""
echo "📊 ФИНАЛЬНЫЙ РЕЗУЛЬТАТ:"
echo "======================"
echo "Исходный IP:           $CURRENT_IP"
echo "После HiLink API:      $NEW_IP_1"
echo "После перезагрузки:    $NEW_IP_2"

echo ""
echo "🔐 ВАЖНЫЕ ПРИНЦИПЫ БЕЗОПАСНОСТИ:"
echo "==============================="
echo "✅ ИСПОЛЬЗУЙ ТОЛЬКО:"
echo "   - HiLink веб-API"
echo "   - Команды через веб-интерфейс"
echo "   - Физическое переподключение"
echo ""
echo "❌ НИКОГДА НЕ ИСПОЛЬЗУЙ:"
echo "   - AT команды (AT+CFUN, AT+CGACT, etc.)"
echo "   - Прямые команды в телнет/ADB"
echo "   - Эксперименты с сетевыми настройками"
echo ""
echo "🎯 РЕКОМЕНДАЦИЯ:"
echo "Если HiLink API не меняет IP, то скорее всего"
echo "твой оператор не выдает новый IP при переподключении."
echo "Это нормально для многих операторов."
