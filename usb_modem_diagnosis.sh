#!/bin/bash
# Скрипт диагностики и оптимизации скорости Huawei E3372/E5770s модемов

echo "🔧 Диагностика и оптимизация скорости Huawei модемов"
echo "====================================================="

# Функция для определения IP модема
find_modem_ip() {
    # Типичные IP адреса для Huawei модемов
    local modem_ips=("192.168.8.1" "192.168.1.1" "192.168.43.1" "192.168.0.1")

    for ip in "${modem_ips[@]}"; do
        if ping -c 1 -W 1 "$ip" >/dev/null 2>&1; then
            if curl -s --connect-timeout 3 "http://$ip/api/webserver/SesTokInfo" | grep -q "SesInfo"; then
                echo "$ip"
                return 0
            fi
        fi
    done

    return 1
}

# Функция для получения токена сессии Huawei
get_session_token() {
    local modem_ip=$1
    local token=$(curl -s "http://$modem_ip/api/webserver/SesTokInfo" | grep -o '<SesInfo>[^<]*</SesInfo>' | sed 's/<[^>]*>//g')
    echo "$token"
}

# Функция для выполнения API запросов к Huawei
huawei_api_request() {
    local modem_ip=$1
    local endpoint=$2
    local method=${3:-"GET"}
    local data=${4:-""}
    local token=$(get_session_token "$modem_ip")

    if [ "$method" = "POST" ]; then
        curl -s -X POST \
            -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
            -H "__RequestVerificationToken: $token" \
            -d "$data" \
            "http://$modem_ip$endpoint"
    else
        curl -s "http://$modem_ip$endpoint"
    fi
}

# Функция парсинга XML (простая)
parse_xml_value() {
    local xml_content=$1
    local tag=$2
    echo "$xml_content" | grep -o "<$tag>[^<]*</$tag>" | sed "s/<[^>]*>//g"
}

echo "1. Поиск Huawei модемов в сети..."
MODEM_IP=$(find_modem_ip)

if [ -z "$MODEM_IP" ]; then
    echo "❌ Huawei модем не найден"
    echo "Проверьте:"
    echo "  - Подключен ли модем"
    echo "  - Включен ли модем"
    echo "  - Доступен ли веб-интерфейс модема"
    exit 1
fi

echo "✅ Найден Huawei модем: $MODEM_IP"

echo ""
echo "2. Получение информации о модеме..."

# Получаем основную информацию
DEVICE_INFO=$(huawei_api_request "$MODEM_IP" "/api/device/information")
MODEL=$(parse_xml_value "$DEVICE_INFO" "DeviceName")
HARDWARE_VERSION=$(parse_xml_value "$DEVICE_INFO" "HardwareVersion")
SOFTWARE_VERSION=$(parse_xml_value "$DEVICE_INFO" "SoftwareVersion")

echo "📱 Модель: $MODEL"
echo "🔧 Железо: $HARDWARE_VERSION"
echo "💾 Прошивка: $SOFTWARE_VERSION"

# Получаем статус сигнала
SIGNAL_INFO=$(huawei_api_request "$MODEM_IP" "/api/device/signal")
RSSI=$(parse_xml_value "$SIGNAL_INFO" "rssi")
RSRP=$(parse_xml_value "$SIGNAL_INFO" "rsrp")
RSRQ=$(parse_xml_value "$SIGNAL_INFO" "rsrq")
SINR=$(parse_xml_value "$SIGNAL_INFO" "sinr")

echo ""
echo "📶 Качество сигнала:"
echo "  RSSI: $RSSI dBm"
echo "  RSRP: $RSRP dBm"
echo "  RSRQ: $RSRQ dB"
echo "  SINR: $SINR dB"

# Анализ качества сигнала
if [ ! -z "$RSRP" ] && [ "$RSRP" -lt -110 ]; then
    echo "⚠️  Слабый сигнал! Нужна внешняя антенна или смена расположения"
elif [ ! -z "$RSRP" ] && [ "$RSRP" -lt -100 ]; then
    echo "🟡 Сигнал средний, возможны проблемы со скоростью"
else
    echo "✅ Сигнал хороший"
fi

# Получаем информацию о сети
NETWORK_INFO=$(huawei_api_request "$MODEM_IP" "/api/net/current-network")
NETWORK_TYPE=$(parse_xml_value "$NETWORK_INFO" "CurrentNetworkType")
NETWORK_MODE=$(parse_xml_value "$NETWORK_INFO" "ServiceDomain")
OPERATOR=$(parse_xml_value "$NETWORK_INFO" "FullName")

echo ""
echo "🌐 Информация о сети:"
echo "  Тип сети: $NETWORK_TYPE"
echo "  Режим: $NETWORK_MODE"
echo "  Оператор: $OPERATOR"

# Декодируем тип сети
case "$NETWORK_TYPE" in
    "19") echo "  📡 LTE (4G)" ;;
    "9"|"10"|"11") echo "  📡 3G/HSPA+" ;;
    "3"|"1"|"2") echo "  📡 2G/EDGE" ;;
    *) echo "  📡 Неизвестный тип: $NETWORK_TYPE" ;;
esac

# Получаем информацию о LTE
if [ "$NETWORK_TYPE" = "19" ]; then
    LTE_INFO=$(huawei_api_request "$MODEM_IP" "/api/net/net-mode")
    BAND_INFO=$(parse_xml_value "$LTE_INFO" "LTEBand")

    echo "  📻 LTE Band: $BAND_INFO"

    # Анализ частотных диапазонов
    case "$BAND_INFO" in
        *"B3"*) echo "    🔥 Band 3 (1800 MHz) - отличная скорость в городе" ;;
        *"B7"*) echo "    🔥 Band 7 (2600 MHz) - максимальная скорость" ;;
        *"B20"*) echo "    🐌 Band 20 (800 MHz) - хорошее покрытие, но низкая скорость" ;;
        *"B1"*) echo "    ⚡ Band 1 (2100 MHz) - хорошая скорость" ;;
        *) echo "    ❓ Неизвестный Band: $BAND_INFO" ;;
    esac
fi

echo ""
echo "3. Диагностика настроек модема..."

# Проверяем режим сети
NET_MODE_INFO=$(huawei_api_request "$MODEM_IP" "/api/net/net-mode")
NETWORK_MODE_SETTING=$(parse_xml_value "$NET_MODE_INFO" "NetworkMode")
NETWORK_BAND=$(parse_xml_value "$NET_MODE_INFO" "NetworkBand")

echo "🔧 Текущие настройки сети:"
echo "  Режим: $NETWORK_MODE_SETTING"
echo "  Диапазоны: $NETWORK_BAND"

# Анализ режима сети
case "$NETWORK_MODE_SETTING" in
    "00") echo "  📶 Автовыбор сети (может вызывать переключения)" ;;
    "03") echo "  📶 Только LTE" ;;
    "02") echo "  📶 Только 3G" ;;
    "01") echo "  📶 Только 2G" ;;
    *) echo "  📶 Неизвестный режим: $NETWORK_MODE_SETTING" ;;
esac

# Проверяем статистику трафика
TRAFFIC_INFO=$(huawei_api_request "$MODEM_IP" "/api/monitoring/traffic-statistics")
CURRENT_DOWNLOAD=$(parse_xml_value "$TRAFFIC_INFO" "CurrentDownloadRate")
CURRENT_UPLOAD=$(parse_xml_value "$TRAFFIC_INFO" "CurrentUploadRate")

if [ ! -z "$CURRENT_DOWNLOAD" ] && [ "$CURRENT_DOWNLOAD" -gt 0 ]; then
    DOWNLOAD_MBPS=$((CURRENT_DOWNLOAD * 8 / 1024 / 1024))
    UPLOAD_MBPS=$((CURRENT_UPLOAD * 8 / 1024 / 1024))
    echo ""
    echo "📊 Текущая скорость:"
    echo "  Download: ${DOWNLOAD_MBPS} Mbps"
    echo "  Upload: ${UPLOAD_MBPS} Mbps"
fi

echo ""
echo "4. Рекомендации по оптимизации:"

# Рекомендации на основе анализа
if [ ! -z "$RSRP" ] && [ "$RSRP" -lt -105 ]; then
    echo "📡 КРИТИЧНО: Установите внешнюю MIMO антенну!"
    echo "   Рекомендуемые модели:"
    echo "   - Антенна MIMO 2x2 с усилением 12-15 dBi"
    echo "   - Расположите антенну на высоте 3-5 метров"
    echo "   - Направьте на ближайшую вышку оператора"
fi

if [ "$NETWORK_MODE_SETTING" = "00" ]; then
    echo "⚙️  Зафиксируйте режим сети:"
    echo "   - Если доступен стабильный LTE → режим 'Только LTE'"
    echo "   - Если LTE нестабилен → режим 'Только 3G'"
fi

if [ "$BAND_INFO" = *"B20"* ]; then
    echo "📻 Попробуйте отключить Band 20 (800 MHz):"
    echo "   - Band 20 дает хорошее покрытие, но низкую скорость"
    echo "   - Оставьте только Band 3 (1800) и Band 7 (2600)"
fi

echo ""
echo "5. Автоматическая оптимизация..."

read -p "Применить автоматические оптимизации? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🔧 Применяем оптимизации..."

    # Оптимизация 1: Фиксируем LTE если сигнал хороший
    if [ ! -z "$RSRP" ] && [ "$RSRP" -gt -105 ] && [ "$NETWORK_TYPE" = "19" ]; then
        echo "  ✅ Фиксируем режим 'Только LTE'..."
        huawei_api_request "$MODEM_IP" "/api/net/net-mode" "POST" \
            '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>3FFFFFFF</NetworkBand></request>'
        sleep 2
    fi

    # Оптимизация 2: Отключаем Band 20 если доступны другие
    if [[ "$BAND_INFO" == *"B3"* || "$BAND_INFO" == *"B7"* ]]; then
        echo "  ✅ Оптимизируем частотные диапазоны..."
        # Оставляем только высокоскоростные Band'ы
        huawei_api_request "$MODEM_IP" "/api/net/net-mode" "POST" \
            '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>C5</NetworkBand></request>'
        sleep 2
    fi

    # Оптимизация 3: Перезагружаем модем для применения настроек
    echo "  🔄 Перезагружаем модем..."
    huawei_api_request "$MODEM_IP" "/api/device/control" "POST" \
        '<?xml version="1.0" encoding="UTF-8"?><request><Control>1</Control></request>'

    echo "  ⏳ Ждем перезагрузки модема (30 секунд)..."
    sleep 30

    echo "✅ Оптимизация завершена!"
else
    echo "ℹ️  Оптимизация пропущена"
fi

echo ""
echo "6. Ручные настройки через веб-интерфейс:"
echo "========================================="
echo "Откройте в браузере: http://$MODEM_IP"
echo ""
echo "🔧 Настройки сети (Settings → Mobile Network):"
echo "  1. Network Mode: 'LTE only' (если сигнал > -105 dBm)"
echo "  2. Band Selection: Отключите Band 20, оставьте 3,7,1"
echo "  3. Preferred LTE Band: Band 7 (2600 MHz) или Band 3 (1800 MHz)"
echo ""
echo "📡 Если низкая скорость:"
echo "  1. Попробуйте разные позиции модема"
echo "  2. Установите внешнюю MIMO антенну"
echo "  3. Проверьте тарифный план (нет ли ограничений)"
echo "  4. Смените время тестирования (избегайте часов пик)"
echo ""
echo "🔍 Диагностические команды:"
echo "  speedtest-cli                    # Тест скорости"
echo "  ping -c 10 8.8.8.8             # Тест пинга"
echo "  iperf3 -c speedtest.selectel.ru  # Продвинутый тест"

echo ""
echo "7. Тест скорости..."
if command -v speedtest-cli &> /dev/null; then
    echo "🚀 Запускаем speedtest-cli..."
    speedtest-cli --simple
else
    echo "⚠️  speedtest-cli не установлен"
    echo "Установите: pip install speedtest-cli"
    echo "Или протестируйте вручную: curl -s https://fast.com"
fi

echo ""
echo "📊 Финальная проверка через 1 минуту..."
sleep 60

# Финальная проверка
FINAL_SIGNAL=$(huawei_api_request "$MODEM_IP" "/api/device/signal")
FINAL_RSRP=$(parse_xml_value "$FINAL_SIGNAL" "rsrp")
FINAL_NETWORK=$(huawei_api_request "$MODEM_IP" "/api/net/current-network")
FINAL_TYPE=$(parse_xml_value "$FINAL_NETWORK" "CurrentNetworkType")

echo "📶 Финальный статус:"
echo "  RSRP: $FINAL_RSRP dBm"
echo "  Сеть: $FINAL_TYPE"

if [ "$FINAL_RSRP" -gt -100 ]; then
    echo "✅ Отличный сигнал!"
elif [ "$FINAL_RSRP" -gt -110 ]; then
    echo "🟡 Хороший сигнал"
else
    echo "⚠️  Слабый сигнал - нужна внешняя антенна"
fi

echo ""
echo "🎯 Дополнительные советы для максимальной скорости:"
echo "  1. Используйте модем в режиме 'Stick' (E3372s), а не HiLink"
echo "  2. Подключайте к USB 3.0 порту"
echo "  3. Избегайте USB хабов и удлинителей"
echo "  4. Проверьте, не ограничивает ли оператор скорость на тарифе"
echo "  5. Рассмотрите смену оператора или тарифного плана"

echo ""
echo "🏁 Диагностика завершена!"
echo "Если проблемы остались, проверьте:"
echo "  - Тарифный план оператора"
echo "  - Состояние SIM-карты"
echo "  - Загруженность сети в вашем районе"

