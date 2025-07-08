#!/bin/bash
# Универсальная диагностика работающих USB модемов
# Автоматически находит все работающие модемы и их параметры

echo "🔧 Универсальная диагностика работающих USB модемов"
echo "=================================================="

# Функции для работы с Huawei API
get_session_token() {
    local ip=$1
    curl -s --connect-timeout 2 "http://$ip/api/webserver/SesTokInfo" 2>/dev/null | grep -o '<SesInfo>[^<]*</SesInfo>' | sed 's/<[^>]*>//g'
}

api_request() {
    local ip=$1
    local endpoint=$2
    curl -s --connect-timeout 3 "http://$ip$endpoint" 2>/dev/null
}

parse_xml() {
    local xml=$1
    local tag=$2
    echo "$xml" | grep -o "<$tag>[^<]*</$tag>" | sed 's/<[^>]*>//g'
}

send_api_command() {
    local ip=$1
    local endpoint=$2
    local data=$3
    local token=$(get_session_token "$ip")

    if [ -n "$token" ]; then
        curl -s -X POST \
            -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
            -H "__RequestVerificationToken: $token" \
            -d "$data" \
            "http://$ip$endpoint" 2>/dev/null
    fi
}

# Поиск всех USB сетевых интерфейсов
echo "1. Поиск активных USB сетевых интерфейсов..."

USB_INTERFACES=()
for interface in $(ip link show | grep -E "enx|usb" | cut -d: -f2 | tr -d ' '); do
    if ip addr show "$interface" | grep -q "inet "; then
        USB_INTERFACES+=("$interface")
        ip_addr=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
        state=$(ip link show "$interface" | grep -o "state [A-Z]*" | cut -d' ' -f2)
        echo "✅ Найден: $interface ($ip_addr, состояние: $state)"
    fi
done

if [ ${#USB_INTERFACES[@]} -eq 0 ]; then
    echo "❌ Активные USB сетевые интерфейсы не найдены"
    echo ""
    echo "💡 Возможные причины:"
    echo "  - USB модемы не подключены"
    echo "  - Интерфейсы не настроены"
    echo "  - Требуется активация модемов"
    exit 1
fi

echo ""
echo "📊 Найдено активных USB интерфейсов: ${#USB_INTERFACES[@]}"

# Определение веб-интерфейсов для каждого USB интерфейса
echo ""
echo "2. Поиск веб-интерфейсов модемов..."

declare -A INTERFACE_WEB_MAP
declare -A WEB_INTERFACE_INFO

for interface in "${USB_INTERFACES[@]}"; do
    echo ""
    echo "🔍 Анализ интерфейса $interface..."

    # Получаем IP подсети интерфейса
    ip_with_mask=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
    network_ip=$(echo "$ip_with_mask" | cut -d'/' -f1)
    network_base=$(echo "$network_ip" | cut -d'.' -f1-3)

    echo "  📍 IP интерфейса: $network_ip"
    echo "  🔍 Поиск веб-интерфейса в подсети $network_base.x..."

    # Список возможных IP для веб-интерфейса в этой подсети
    possible_web_ips=(
        "${network_base}.1"
        "${network_base}.254"
        "${network_base}.100"
        "${network_base}.200"
    )

    web_found=false
    for web_ip in "${possible_web_ips[@]}"; do
        echo -n "    Проверяем $web_ip... "

        if ping -c 1 -W 1 "$web_ip" >/dev/null 2>&1; then
            if curl -s --connect-timeout 2 "http://$web_ip" | grep -qi "huawei\|mobile.*wifi\|lte\|4g\|modem"; then
                echo "✅ Найден"
                INTERFACE_WEB_MAP["$interface"]="$web_ip"
                web_found=true

                # Получаем информацию о модеме
                device_info=$(api_request "$web_ip" "/api/device/information")
                if [ -n "$device_info" ]; then
                    model=$(parse_xml "$device_info" "DeviceName")
                    imei=$(parse_xml "$device_info" "Imei")
                    WEB_INTERFACE_INFO["${web_ip}_model"]="${model:-"Unknown"}"
                    WEB_INTERFACE_INFO["${web_ip}_imei"]="$imei"
                    echo "      📱 Модель: ${model:-"Unknown"}"
                fi
                break
            else
                echo "❌ Не модем"
            fi
        else
            echo "❌ Недоступен"
        fi
    done

    if [ "$web_found" = false ]; then
        echo "  ⚠️  Веб-интерфейс не найден для $interface"
        echo "  💡 Возможно, модем в режиме Stick или использует нестандартный IP"
    fi
done

# Диагностика каждого найденного модема
echo ""
echo "3. Диагностика найденных модемов..."

counter=1
for interface in "${USB_INTERFACES[@]}"; do
    echo ""
    echo "[$counter/${#USB_INTERFACES[@]}] 📋 Диагностика интерфейса: $interface"
    echo "============================================="

    # Основная информация об интерфейсе
    ip_addr=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
    gateway=$(ip route show dev "$interface" | grep default | awk '{print $3}' | head -1)

    echo "🌐 Сетевая информация:"
    echo "  IP: $ip_addr"
    echo "  Шлюз: ${gateway:-"не найден"}"

    # Тест интернета
    echo ""
    echo "🌍 Тест интернет-соединения:"
    if timeout 10 curl -s --interface "$interface" http://httpbin.org/ip >/dev/null 2>&1; then
        external_ip=$(timeout 10 curl -s --interface "$interface" http://httpbin.org/ip 2>/dev/null | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
        echo "  ✅ Интернет работает!"
        echo "  📍 Внешний IP: ${external_ip:-"неопределен"}"

        # Тест скорости (простой)
        echo -n "  ⚡ Тест скорости... "
        start_time=$(date +%s%N)
        curl -s --interface "$interface" --max-time 5 http://httpbin.org/bytes/1048576 >/dev/null 2>&1
        end_time=$(date +%s%N)
        duration=$(( (end_time - start_time) / 1000000 ))

        if [ $duration -gt 0 ] && [ $duration -lt 10000 ]; then
            speed=$(( 8 * 1048576 / duration ))  # бит/мс = Мбит/с
            echo "${speed} Мбит/с (приблизительно)"
        else
            echo "не удалось измерить"
        fi
    else
        echo "  ❌ Интернет не работает"
    fi

    # Тест пинга
    echo ""
    echo "📡 Тест задержки:"
    ping_result=$(ping -I "$interface" -c 3 8.8.8.8 2>/dev/null | grep "time=" | tail -1)
    if [ -n "$ping_result" ]; then
        ping_time=$(echo "$ping_result" | grep -o "time=[0-9.]*" | cut -d= -f2)
        avg_ping=$(ping -I "$interface" -c 3 8.8.8.8 2>/dev/null | grep "avg" | cut -d'/' -f5)
        echo "  ⚡ Пинг: ${ping_time}ms"
        echo "  📊 Средний пинг: ${avg_ping:-"N/A"}ms"
    else
        echo "  ❌ Пинг не проходит"
    fi

    # Диагностика веб-интерфейса (если найден)
    web_ip="${INTERFACE_WEB_MAP[$interface]}"
    if [ -n "$web_ip" ]; then
        echo ""
        echo "🌐 Диагностика веб-интерфейса ($web_ip):"

        model="${WEB_INTERFACE_INFO[${web_ip}_model]}"
        imei="${WEB_INTERFACE_INFO[${web_ip}_imei]}"

        echo "  📱 Модель: $model"
        if [ -n "$imei" ]; then
            echo "  🆔 IMEI: ${imei:0:8}****${imei:12}"
        fi

        # Получаем статус сигнала
        signal_info=$(api_request "$web_ip" "/api/device/signal")
        if [ -n "$signal_info" ]; then
            rssi=$(parse_xml "$signal_info" "rssi")
            rsrp=$(parse_xml "$signal_info" "rsrp")
            rsrq=$(parse_xml "$signal_info" "rsrq")
            sinr=$(parse_xml "$signal_info" "sinr")

            echo "  📶 Качество сигнала:"
            echo "    RSSI: ${rssi:-"N/A"} dBm"
            echo "    RSRP: ${rsrp:-"N/A"} dBm"
            echo "    RSRQ: ${rsrq:-"N/A"} dB"
            echo "    SINR: ${sinr:-"N/A"} dB"

            # Оценка качества сигнала
            if [ -n "$rsrp" ] && [ "$rsrp" -gt -100 ]; then
                echo "    ✅ Отличный сигнал"
            elif [ -n "$rsrp" ] && [ "$rsrp" -gt -110 ]; then
                echo "    🟡 Хороший сигнал"
            elif [ -n "$rsrp" ]; then
                echo "    ⚠️  Слабый сигнал"
            fi
        fi

        # Получаем информацию о сети
        network_info=$(api_request "$web_ip" "/api/net/current-network")
        if [ -n "$network_info" ]; then
            network_type=$(parse_xml "$network_info" "CurrentNetworkType")
            operator=$(parse_xml "$network_info" "FullName")

            echo "  🏢 Оператор: ${operator:-"N/A"}"

            case "$network_type" in
                "19") echo "  📡 Тип сети: LTE (4G)" ;;
                "9"|"10"|"11") echo "  📡 Тип сети: 3G/HSPA+" ;;
                "3"|"1"|"2") echo "  📡 Тип сети: 2G/EDGE" ;;
                *) echo "  📡 Тип сети: неизвестен ($network_type)" ;;
            esac
        fi

        # Получаем статус подключения
        status_info=$(api_request "$web_ip" "/api/monitoring/status")
        if [ -n "$status_info" ]; then
            connection_status=$(parse_xml "$status_info" "ConnectionStatus")
            case "$connection_status" in
                "901") echo "  🔗 Статус: Подключено" ;;
                "902") echo "  🔗 Статус: Отключено" ;;
                "903") echo "  🔗 Статус: Отключение..." ;;
                "904") echo "  🔗 Статус: Подключение..." ;;
                *) echo "  🔗 Статус: $connection_status" ;;
            esac
        fi

        echo "  🌐 Веб-панель: http://$web_ip"
    else
        echo ""
        echo "⚠️  Веб-интерфейс не найден для этого интерфейса"
    fi

    counter=$((counter + 1))
done

# Опции оптимизации
echo ""
echo "4. Опции оптимизации..."

available_optimizations=0
for interface in "${USB_INTERFACES[@]}"; do
    web_ip="${INTERFACE_WEB_MAP[$interface]}"
    if [ -n "$web_ip" ]; then
        available_optimizations=$((available_optimizations + 1))
    fi
done

if [ $available_optimizations -gt 0 ]; then
    echo "🔧 Доступна оптимизация для $available_optimizations модема(ов)"
    echo ""
    read -p "Хотите запустить оптимизацию? (y/N): " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "⚡ Запуск оптимизации..."

        for interface in "${USB_INTERFACES[@]}"; do
            web_ip="${INTERFACE_WEB_MAP[$interface]}"
            if [ -n "$web_ip" ]; then
                echo ""
                echo "🔧 Оптимизация модема на $web_ip..."

                # Получаем текущую информацию
                signal_info=$(api_request "$web_ip" "/api/device/signal")
                rsrp=$(parse_xml "$signal_info" "rsrp")

                optimizations_applied=0

                # Оптимизация 1: Фиксация LTE режима (если сигнал хороший)
                if [ -n "$rsrp" ] && [ "$rsrp" -gt -105 ]; then
                    echo "  ✅ Фиксируем LTE режим..."
                    send_api_command "$web_ip" "/api/net/net-mode" \
                        '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>3FFFFFFF</NetworkBand></request>'
                    optimizations_applied=$((optimizations_applied + 1))
                fi

                # Оптимизация 2: Оптимизация частотных диапазонов
                lte_info=$(api_request "$web_ip" "/api/net/net-mode")
                if echo "$lte_info" | grep -q "B3\|B7"; then
                    echo "  ✅ Оптимизируем частотные диапазоны..."
                    send_api_command "$web_ip" "/api/net/net-mode" \
                        '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>C5</NetworkBand></request>'
                    optimizations_applied=$((optimizations_applied + 1))
                fi

                if [ $optimizations_applied -gt 0 ]; then
                    echo "  📊 Применено оптимизаций: $optimizations_applied"
                    echo "  ⏳ Ожидание применения настроек..."
                    sleep 5
                else
                    echo "  ℹ️  Оптимизация не требуется"
                fi
            fi
        done

        echo ""
        echo "✅ Оптимизация завершена!"
    fi
else
    echo "⚠️  Оптимизация недоступна (веб-интерфейсы не найдены)"
fi

# Итоговая статистика
echo ""
echo "📊 Итоговая статистика:"
echo "======================="
echo "🔧 Всего USB интерфейсов: ${#USB_INTERFACES[@]}"
echo "🌐 Веб-интерфейсов найдено: $available_optimizations"

working_internet=0
for interface in "${USB_INTERFACES[@]}"; do
    if timeout 5 curl -s --interface "$interface" http://httpbin.org/ip >/dev/null 2>&1; then
        working_internet=$((working_internet + 1))
    fi
done

echo "🌍 Интерфейсов с интернетом: $working_internet"

if [ $working_internet -eq ${#USB_INTERFACES[@]} ]; then
    echo ""
    echo "🎉 Все модемы работают отлично!"
elif [ $working_internet -gt 0 ]; then
    echo ""
    echo "✅ Частично работающая конфигурация"
else
    echo ""
    echo "⚠️  Требуется дополнительная настройка"
fi

echo ""
echo "🚀 Модемы готовы для интеграции в Mobile Proxy Service!"
