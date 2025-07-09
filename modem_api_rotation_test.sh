#!/bin/bash

# Тест ротации IP через API модема Huawei
INTERFACE="enx0c5b8f279a64"
MODEM_IP="192.168.108.1"
DEVICE_ID="12d1:14dc"  # Huawei E3372 HiLink

echo "🌐 Тест ротации IP через API модема Huawei"
echo "=========================================="

# Функция получения внешнего IP
get_external_ip() {
    local ip=$(timeout 10 curl --interface "$INTERFACE" -s https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"' || echo "unknown")
    echo "$ip"
}

# Функция получения токена сессии
get_session_token() {
    local response=$(curl -s -m 5 "http://$MODEM_IP/api/webserver/SesTokInfo" 2>/dev/null)
    if [ -n "$response" ]; then
        local token=$(echo "$response" | grep -o '<SesInfo>[^<]*</SesInfo>' | sed 's/<[^>]*>//g')
        if [ -n "$token" ]; then
            echo "$token"
            return 0
        fi
    fi
    return 1
}

# Функция выполнения API запроса с токеном
api_request() {
    local endpoint="$1"
    local method="$2"
    local data="$3"
    local token="$4"

    if [ "$method" = "GET" ]; then
        curl -s -m 10 \
            -H "Cookie: SessionID=$token" \
            -H "__RequestVerificationToken: $token" \
            "http://$MODEM_IP/api/$endpoint" 2>/dev/null
    elif [ "$method" = "POST" ]; then
        curl -s -m 10 \
            -H "Cookie: SessionID=$token" \
            -H "__RequestVerificationToken: $token" \
            -H "Content-Type: application/xml" \
            -d "$data" \
            "http://$MODEM_IP/api/$endpoint" 2>/dev/null
    fi
}

# Получаем начальный IP
echo ""
echo "📊 Проверка начального состояния"
echo "================================"

INITIAL_IP=$(get_external_ip)
echo "🌐 Начальный внешний IP: $INITIAL_IP"

# Проверяем доступность API модема
echo "🔍 Проверка доступности API модема..."
if ping -c 1 -W 2 "$MODEM_IP" >/dev/null 2>&1; then
    echo "✅ Модем доступен по IP: $MODEM_IP"
else
    echo "❌ Модем недоступен по IP: $MODEM_IP"
    exit 1
fi

# Получаем информацию о модеме
echo ""
echo "📱 Информация о модеме"
echo "===================="

device_info=$(curl -s -m 5 "http://$MODEM_IP/api/device/information" 2>/dev/null)
if [ -n "$device_info" ]; then
    echo "✅ API device/information доступен"

    device_name=$(echo "$device_info" | grep -o '<DeviceName>[^<]*</DeviceName>' | sed 's/<[^>]*>//g')
    model=$(echo "$device_info" | grep -o '<ProductFamily>[^<]*</ProductFamily>' | sed 's/<[^>]*>//g')
    version=$(echo "$device_info" | grep -o '<SoftwareVersion>[^<]*</SoftwareVersion>' | sed 's/<[^>]*>//g')

    echo "  Устройство: $device_name"
    echo "  Модель: $model"
    echo "  Версия ПО: $version"
else
    echo "❌ API device/information недоступен"
fi

echo ""
echo "🔄 Метод 1: Переподключение через dialup API"
echo "==========================================="

# Получаем токен сессии
echo "🔐 Получение токена сессии..."
SESSION_TOKEN=$(get_session_token)

if [ -n "$SESSION_TOKEN" ]; then
    echo "✅ Токен получен: ${SESSION_TOKEN:0:20}..."

    # Получаем статус соединения
    echo "📋 Проверка статуса соединения..."
    connection_status=$(api_request "dialup/connection" "GET" "" "$SESSION_TOKEN")

    if [ -n "$connection_status" ]; then
        echo "✅ Статус соединения получен"
        current_state=$(echo "$connection_status" | grep -o '<State>[^<]*</State>' | sed 's/<[^>]*>//g')
        echo "  Текущее состояние: $current_state"

        # Отключаем соединение
        echo "🔧 Отключение соединения..."
        disconnect_xml='<?xml version="1.0" encoding="UTF-8"?><request><Action>0</Action></request>'
        disconnect_result=$(api_request "dialup/dialup" "POST" "$disconnect_xml" "$SESSION_TOKEN")

        if [ -n "$disconnect_result" ]; then
            echo "✅ Команда отключения отправлена"
            echo "⏳ Ожидание отключения (10 секунд)..."
            sleep 10

            # Подключаем обратно
            echo "🔧 Подключение обратно..."
            connect_xml='<?xml version="1.0" encoding="UTF-8"?><request><Action>1</Action></request>'
            connect_result=$(api_request "dialup/dialup" "POST" "$connect_xml" "$SESSION_TOKEN")

            if [ -n "$connect_result" ]; then
                echo "✅ Команда подключения отправлена"
                echo "⏳ Ожидание подключения (20 секунд)..."
                sleep 20
            else
                echo "❌ Не удалось отправить команду подключения"
            fi
        else
            echo "❌ Не удалось отправить команду отключения"
        fi
    else
        echo "❌ Не удалось получить статус соединения"
    fi
else
    echo "❌ Не удалось получить токен сессии"
fi

echo ""
echo "🔄 Метод 2: Перезагрузка модема через API"
echo "======================================="

# Обновляем токен
SESSION_TOKEN=$(get_session_token)

if [ -n "$SESSION_TOKEN" ]; then
    echo "🔐 Токен обновлён"

    # Отправляем команду перезагрузки
    echo "🔧 Отправка команды перезагрузки..."
    reboot_xml='<?xml version="1.0" encoding="UTF-8"?><request><Control>1</Control></request>'
    reboot_result=$(api_request "device/control" "POST" "$reboot_xml" "$SESSION_TOKEN")

    if [ -n "$reboot_result" ]; then
        echo "✅ Команда перезагрузки отправлена"
        echo "⏳ Ожидание перезагрузки (60 секунд)..."
        sleep 60

        # Ждём, пока модем снова станет доступен
        echo "⏳ Ожидание восстановления модема..."
        for i in {1..30}; do
            if ping -c 1 -W 2 "$MODEM_IP" >/dev/null 2>&1; then
                echo "✅ Модем восстановлен после перезагрузки"
                break
            fi
            echo "  Попытка $i/30..."
            sleep 2
        done
    else
        echo "❌ Не удалось отправить команду перезагрузки"
    fi
fi

echo ""
echo "🔄 Метод 3: Сброс сетевых настроек через API"
echo "=========================================="

# Обновляем токен
SESSION_TOKEN=$(get_session_token)

if [ -n "$SESSION_TOKEN" ]; then
    echo "🔐 Токен обновлён"

    # Пытаемся сбросить сетевые настройки
    echo "🔧 Попытка сброса сетевых настроек..."

    # Разные варианты reset API
    reset_endpoints=(
        "device/reset"
        "device/factory_reset"
        "system/reset"
        "management/reset"
        "net/reset"
    )

    for endpoint in "${reset_endpoints[@]}"; do
        echo "  Пробуем $endpoint..."
        reset_xml='<?xml version="1.0" encoding="UTF-8"?><request><Reset>1</Reset></request>'
        reset_result=$(api_request "$endpoint" "POST" "$reset_xml" "$SESSION_TOKEN")

        if [ -n "$reset_result" ] && ! echo "$reset_result" | grep -q "error"; then
            echo "  ✅ Команда принята через $endpoint"
            echo "  ⏳ Ожидание применения настроек (30 секунд)..."
            sleep 30
            break
        else
            echo "  ❌ $endpoint не сработал"
        fi
    done
fi

echo ""
echo "🔄 Метод 4: Управление PLMN (сотовые сети)"
echo "========================================"

# Обновляем токен
SESSION_TOKEN=$(get_session_token)

if [ -n "$SESSION_TOKEN" ]; then
    echo "🔐 Токен обновлён"

    # Получаем текущие настройки PLMN
    echo "📋 Получение текущих настроек PLMN..."
    plmn_info=$(api_request "net/plmn" "GET" "" "$SESSION_TOKEN")

    if [ -n "$plmn_info" ]; then
        echo "✅ Настройки PLMN получены"

        # Переключаем в ручной режим и обратно в автоматический
        echo "🔧 Переключение в ручной режим выбора сети..."
        manual_xml='<?xml version="1.0" encoding="UTF-8"?><request><State>1</State></request>'
        manual_result=$(api_request "net/plmn" "POST" "$manual_xml" "$SESSION_TOKEN")

        if [ -n "$manual_result" ]; then
            echo "✅ Переключено в ручной режим"
            sleep 10

            echo "🔧 Переключение обратно в автоматический режим..."
            auto_xml='<?xml version="1.0" encoding="UTF-8"?><request><State>0</State></request>'
            auto_result=$(api_request "net/plmn" "POST" "$auto_xml" "$SESSION_TOKEN")

            if [ -n "$auto_result" ]; then
                echo "✅ Переключено в автоматический режим"
                echo "⏳ Ожидание переподключения к сети (30 секунд)..."
                sleep 30
            fi
        fi
    else
        echo "❌ Не удалось получить настройки PLMN"
    fi
fi

echo ""
echo "🔄 Метод 5: Управление режимом сети"
echo "================================="

# Обновляем токен
SESSION_TOKEN=$(get_session_token)

if [ -n "$SESSION_TOKEN" ]; then
    echo "🔐 Токен обновлён"

    # Получаем текущий режим сети
    echo "📋 Получение текущего режима сети..."
    net_mode=$(api_request "net/net-mode" "GET" "" "$SESSION_TOKEN")

    if [ -n "$net_mode" ]; then
        echo "✅ Режим сети получен"
        current_mode=$(echo "$net_mode" | grep -o '<NetworkMode>[^<]*</NetworkMode>' | sed 's/<[^>]*>//g')
        echo "  Текущий режим: $current_mode"

        # Переключаем режим сети (например, с авто на 4G only и обратно)
        echo "🔧 Переключение режима сети..."

        # Пробуем разные режимы
        modes=("03" "01" "00")  # 03=4G only, 01=3G only, 00=Auto

        for mode in "${modes[@]}"; do
            if [ "$mode" != "$current_mode" ]; then
                echo "  Переключение в режим $mode..."
                mode_xml="<?xml version=\"1.0\" encoding=\"UTF-8\"?><request><NetworkMode>$mode</NetworkMode><NetworkBand>3FFFFFFF</NetworkBand><LTEBand>7FFFFFFFFFFFFFFF</LTEBand></request>"
                mode_result=$(api_request "net/net-mode" "POST" "$mode_xml" "$SESSION_TOKEN")

                if [ -n "$mode_result" ]; then
                    echo "  ✅ Режим $mode установлен"
                    sleep 15
                    break
                fi
            fi
        done

        # Возвращаем авто режим
        echo "🔧 Возвращение в автоматический режим..."
        auto_mode_xml='<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>00</NetworkMode><NetworkBand>3FFFFFFF</NetworkBand><LTEBand>7FFFFFFFFFFFFFFF</LTEBand></request>'
        auto_mode_result=$(api_request "net/net-mode" "POST" "$auto_mode_xml" "$SESSION_TOKEN")

        if [ -n "$auto_mode_result" ]; then
            echo "✅ Возвращён автоматический режим"
            echo "⏳ Ожидание переподключения (30 секунд)..."
            sleep 30
        fi
    else
        echo "❌ Не удалось получить режим сети"
    fi
fi

echo ""
echo "📊 Проверка результатов всех методов"
echo "==================================="

# Проверяем, что интерфейс всё ещё работает
if ip addr show "$INTERFACE" | grep -q "inet "; then
    echo "✅ Интерфейс $INTERFACE активен"

    # Получаем финальный IP
    echo "🌐 Получение финального внешнего IP..."
    FINAL_IP=$(get_external_ip)

    echo ""
    echo "📋 Результаты ротации через API:"
    echo "  Начальный IP: $INITIAL_IP"
    echo "  Финальный IP: $FINAL_IP"

    if [ "$INITIAL_IP" != "$FINAL_IP" ] && [ "$FINAL_IP" != "unknown" ] && [ -n "$FINAL_IP" ]; then
        echo "  ✅ IP успешно изменился через API!"
        echo ""
        echo "🎉 API методы модема РАБОТАЮТ для ротации IP!"
        echo ""
        echo "🚀 Рекомендуемые методы для интеграции:"
        echo "1. dialup/dialup - отключение и подключение соединения"
        echo "2. device/control - перезагрузка модема"
        echo "3. net/plmn - переключение режима выбора сети"
        echo "4. net/net-mode - переключение режима сети"
    else
        echo "  ⚠️ IP не изменился через API методы"
        echo ""
        echo "❌ API методы модема НЕ РАБОТАЮТ для ротации IP"
    fi

    # Дополнительная диагностика
    echo ""
    echo "📊 Дополнительная диагностика:"

    # Проверяем статус соединения
    final_status=$(curl -s -m 5 "http://$MODEM_IP/api/dialup/connection" 2>/dev/null)
    if [ -n "$final_status" ]; then
        connection_state=$(echo "$final_status" | grep -o '<State>[^<]*</State>' | sed 's/<[^>]*>//g')
        echo "  Состояние соединения: $connection_state"
    fi

    # Проверяем информацию о сигнале
    signal_info=$(curl -s -m 5 "http://$MODEM_IP/api/device/signal" 2>/dev/null)
    if [ -n "$signal_info" ]; then
        signal_strength=$(echo "$signal_info" | grep -o '<rssi>[^<]*</rssi>' | sed 's/<[^>]*>//g')
        echo "  Сила сигнала: $signal_strength"
    fi

else
    echo "❌ Интерфейс $INTERFACE не активен"
    echo "❌ Тест не удался - интерфейс потерян"
fi

echo ""
echo "🏁 Тест API методов завершён"
echo "==========================="

# Итоговые рекомендации
echo ""
echo "💡 Общие рекомендации:"
echo "1. Комбинируйте API методы с переключением режимов"
echo "2. Используйте таймауты для стабилизации соединения"
echo "3. Реализуйте проверку доступности API перед вызовом"
echo "4. Добавьте fallback на другие методы ротации"
echo "5. Логируйте все API запросы для отладки"

if [ "$INITIAL_IP" != "$FINAL_IP" ] && [ "$FINAL_IP" != "unknown" ] && [ -n "$FINAL_IP" ]; then
    echo ""
    echo "✅ ИТОГ: API методы эффективны для ротации IP!"
    echo "   Интегрируйте их в RotationManager как основные методы"
else
    echo ""
    echo "⚠️ ИТОГ: API методы требуют дополнительной настройки"
    echo "   Рассмотрите комбинацию с другими методами ротации"
fi

