#!/bin/bash
# Универсальная диагностика и оптимизация Huawei USB модемов
# Поддерживает множественные модемы с интерактивным выбором

echo "🔧 Универсальная диагностика и оптимизация USB модемов"
echo "======================================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Список поддерживаемых модемов Huawei
HUAWEI_MODEMS=(
    "12d1:14dc"  # E3372 HiLink
    "12d1:1f01"  # E3372 Stick
    "12d1:157d"  # E3372h
    "12d1:14db"  # E3372s
    "12d1:1506"  # E5770s
    "12d1:1573"  # E5770
    "12d1:15ca"  # E8372
    "12d1:1442"  # E5573
    "12d1:14fe"  # E5577
)

# Ассоциативный массив названий модемов
declare -A MODEM_NAMES=(
    ["12d1:14dc"]="E3372 HiLink"
    ["12d1:1f01"]="E3372 Stick"
    ["12d1:157d"]="E3372h"
    ["12d1:14db"]="E3372s"
    ["12d1:1506"]="E5770s"
    ["12d1:1573"]="E5770"
    ["12d1:15ca"]="E8372"
    ["12d1:1442"]="E5573"
    ["12d1:14fe"]="E5577"
)

# Глобальные массивы для хранения информации о модемах
declare -A MODEM_WEB_IPS
declare -A MODEM_INTERFACES
declare -A MODEM_DETAILS

# Функции для работы с Huawei API
get_session_token() {
    local modem_ip=$1
    curl -s "http://$modem_ip/api/webserver/SesTokInfo" 2>/dev/null | grep -o '<SesInfo>[^<]*</SesInfo>' | sed 's/<[^>]*>//g'
}

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
            "http://$modem_ip$endpoint" 2>/dev/null
    else
        curl -s "http://$modem_ip$endpoint" 2>/dev/null
    fi
}

parse_xml_value() {
    local xml_content=$1
    local tag=$2
    echo "$xml_content" | grep -o "<$tag>[^<]*</$tag>" | sed "s/<[^>]*>//g"
}

# ИСПРАВЛЕННАЯ функция определения Huawei устройства (для кастомных прошивок)
is_huawei_device() {
    local ip=$1

    echo -n "    Проверяем доступность... "

    # 1. Проверяем ping
    if ! timeout 3 ping -c 1 -W 1 "$ip" >/dev/null 2>&1; then
        echo -e "${RED}❌ Ping недоступен${NC}"
        return 1
    fi

    echo -n "ping OK, "

    # 2. Проверяем HTTP доступность
    local http_response=""
    http_response=$(timeout 5 curl -s --connect-timeout 3 "http://$ip" 2>/dev/null)

    if [ -z "$http_response" ]; then
        echo -e "${RED}❌ HTTP недоступен${NC}"
        return 1
    fi

    echo -n "HTTP OK, "

    # 3. КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Проверяем специфичный endpoint для кастомных прошивок
    echo -n "проверяем SesTokInfo... "

    local sesinfo_check=""
    sesinfo_check=$(timeout 3 curl -s "http://$ip/api/webserver/SesTokInfo" 2>/dev/null)

    if [ -n "$sesinfo_check" ] && echo "$sesinfo_check" | grep -qi "SesInfo"; then
        echo -e "${GREEN}✅ Huawei кастомная прошивка обнаружена${NC}"
        return 0
    fi

    # 4. Стандартная проверка для обычных прошивок
    if echo "$http_response" | grep -qi -E "(huawei|mobile.*wifi|4g.*router|lte.*modem|hilink|copyright.*huawei|deviceinformation|webserver)"; then
        echo -e "${GREEN}✅ Huawei стандартная прошивка${NC}"
        return 0
    fi

    # 5. Проверка других Huawei API
    local api_check=""
    api_check=$(timeout 3 curl -s "http://$ip/api/device/information" 2>/dev/null)

    if [ -n "$api_check" ] && echo "$api_check" | grep -qi -E "(devicename|hardwareversion|softwareversion|imei)"; then
        echo -e "${GREEN}✅ Huawei API обнаружен${NC}"
        return 0
    fi

    echo -e "${RED}❌ Не Huawei или недоступен${NC}"
    return 1
}

# Функция поиска всех веб-интерфейсов модемов
discover_modem_web_interfaces() {
    echo -e "${BLUE}🔍 Поиск веб-интерфейсов модемов...${NC}"

    # РАСШИРЕННЫЙ список возможных IP адресов
    local web_ips=(
        "192.168.8.1"     # Стандартный Huawei
        "192.168.1.1"     # Альтернативный
        "192.168.43.1"    # Точка доступа
        "192.168.0.1"     # Роутер режим
        "192.168.107.1"   # ВАШ МОДЕМ!
        "192.168.100.1"   # Пользовательский
        "10.0.0.1"        # Альтернативная сеть
        "192.168.2.1"     # Дополнительный
        "192.168.7.1"     # Дополнительный
        "192.168.108.1"   # Дополнительный
        "192.168.9.1"     # Дополнительный
        "192.168.10.1"    # Дополнительный
        "192.168.15.1"    # Дополнительный
        "192.168.20.1"    # Дополнительный
        "192.168.50.1"    # Дополнительный
        "192.168.99.1"    # Дополнительный
        "10.0.0.138"      # Альтернативный
        "172.16.1.1"      # Другая подсеть
    )

    # АВТОМАТИЧЕСКОЕ определение возможных IP из сетевых интерфейсов
    echo "  Автоматический поиск Gateway IP..."
    local auto_gateways=($(ip route | grep default | awk '{print $3}' | sort -u))
    for gw in "${auto_gateways[@]}"; do
        if [[ "$gw" =~ ^192\.168\.|^10\.|^172\. ]]; then
            web_ips+=("$gw")
        fi
    done

    # Поиск IP из активных интерфейсов
    echo "  Поиск IP из активных интерфейсов..."
    local interface_ips=($(ip addr show | grep 'inet ' | grep -E '192\.168\.|10\.|172\.' | awk '{print $2}' | cut -d/ -f1 | sed 's/\.[0-9]*$/.1/'))
    for ip in "${interface_ips[@]}"; do
        web_ips+=("$ip")
    done

    # Убираем дубликаты
    local unique_ips=($(printf '%s\n' "${web_ips[@]}" | sort -u))

    local found_count=0

    for ip in "${unique_ips[@]}"; do
        echo -ne "  Проверяем $ip..."

        if is_huawei_device "$ip"; then
            # Получаем информацию о модеме
            local device_info=$(huawei_api_request "$ip" "/api/device/information")
            local model=$(parse_xml_value "$device_info" "DeviceName")
            local imei=$(parse_xml_value "$device_info" "Imei")

            if [ -z "$model" ]; then
                model="Unknown Huawei Model"
            fi

            MODEM_WEB_IPS["$ip"]="$model"
            MODEM_DETAILS["${ip}_imei"]="$imei"

            # Ищем соответствующий сетевой интерфейс
            local interface=""
            for iface in $(ip link show | grep -E "enx|usb|eth|wlan" | cut -d: -f2 | tr -d ' '); do
                if ip addr show "$iface" 2>/dev/null | grep -q "$(echo $ip | sed 's/\.1$//')."; then
                    interface="$iface"
                    break
                fi
            done

            MODEM_INTERFACES["$ip"]="$interface"
            found_count=$((found_count + 1))

            echo "    📱 Модель: $model"
            if [ -n "$imei" ]; then
                echo "    🆔 IMEI: $imei"
            fi
            if [ -n "$interface" ]; then
                echo "    🌐 Интерфейс: $interface"
            fi
        fi
    done

    echo ""
    if [ $found_count -eq 0 ]; then
        echo -e "${RED}❌ Модемы с веб-интерфейсом не найдены${NC}"
        echo ""
        echo -e "${YELLOW}💡 Возможные причины:${NC}"
        echo "  - Модемы в режиме Stick (не HiLink)"
        echo "  - SIM-карты не вставлены или заблокированы"
        echo "  - Модемы не подключены к сети"
        echo "  - Нестандартные IP адреса веб-интерфейсов"
        echo ""
        echo -e "${CYAN}🔧 Попробуйте:${NC}"
        echo "  1. Проверить: curl -s http://192.168.107.1/api/device/information"
        echo "  2. Проверить браузером: http://192.168.107.1"
        echo "  3. Запустить: ip route show"
        return 1
    else
        echo -e "${GREEN}✅ Найдено модемов: $found_count${NC}"
        return 0
    fi
}

# Функция отображения меню выбора модема
show_modem_selection_menu() {
    local action=$1  # "diagnose" или "optimize"
    local action_name=""
    local action_emoji=""

    case $action in
        "diagnose")
            action_name="диагностики"
            action_emoji="🔍"
            ;;
        "optimize")
            action_name="оптимизации"
            action_emoji="⚡"
            ;;
    esac

    echo ""
    echo -e "${CYAN}📋 Выберите модем для ${action_name}:${NC}"
    echo "======================================="

    local counter=1
    local menu_options=()

    # Добавляем опции для всех устройств
    echo -e "${PURPLE}$counter)${NC} ${action_emoji} Все устройства"
    menu_options+=("ALL")
    counter=$((counter + 1))

    echo ""

    # Добавляем каждый найденный модем
    for ip in "${!MODEM_WEB_IPS[@]}"; do
        local model="${MODEM_WEB_IPS[$ip]}"
        local interface="${MODEM_INTERFACES[$ip]}"
        local imei="${MODEM_DETAILS[${ip}_imei]}"

        echo -e "${PURPLE}$counter)${NC} 📱 $model"
        echo "     🌐 IP: $ip"
        if [ -n "$interface" ]; then
            echo "     🔗 Интерфейс: $interface"
        fi
        if [ -n "$imei" ]; then
            echo "     🆔 IMEI: ${imei:0:8}****${imei:12}"
        fi
        echo ""

        menu_options+=("$ip")
        counter=$((counter + 1))
    done

    echo -e "${PURPLE}0)${NC} 🚪 Выход"
    echo ""

    while true; do
        read -p "Введите номер (0-$((counter-1))): " choice

        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 0 ] && [ "$choice" -lt "$counter" ]; then
            if [ "$choice" -eq 0 ]; then
                echo -e "${YELLOW}👋 Выход из программы${NC}"
                exit 0
            else
                selected_option="${menu_options[$((choice-1))]}"
                return 0
            fi
        else
            echo -e "${RED}❌ Неверный выбор. Введите число от 0 до $((counter-1))${NC}"
        fi
    done
}

# Функция диагностики одного модема (остается как есть)
diagnose_single_modem() {
    local modem_ip=$1
    local model="${MODEM_WEB_IPS[$modem_ip]}"

    echo ""
    echo -e "${CYAN}🔍 Диагностика модема: $model ($modem_ip)${NC}"
    echo "==============================================="

    # Получаем основную информацию
    local device_info=$(huawei_api_request "$modem_ip" "/api/device/information")
    local hardware_version=$(parse_xml_value "$device_info" "HardwareVersion")
    local software_version=$(parse_xml_value "$device_info" "SoftwareVersion")

    echo "📱 Модель: $model"
    echo "🔧 Железо: $hardware_version"
    echo "💾 Прошивка: $software_version"

    # Получаем статус сигнала
    local signal_info=$(huawei_api_request "$modem_ip" "/api/device/signal")
    local rssi=$(parse_xml_value "$signal_info" "rssi")
    local rsrp=$(parse_xml_value "$signal_info" "rsrp")
    local rsrq=$(parse_xml_value "$signal_info" "rsrq")
    local sinr=$(parse_xml_value "$signal_info" "sinr")

    echo ""
    echo "📶 Качество сигнала:"
    echo "  RSSI: ${rssi:-"N/A"} dBm"
    echo "  RSRP: ${rsrp:-"N/A"} dBm"
    echo "  RSRQ: ${rsrq:-"N/A"} dB"
    echo "  SINR: ${sinr:-"N/A"} dB"

    # Анализ качества сигнала
    if [ -n "$rsrp" ] && [ "$rsrp" -lt -110 ]; then
        echo -e "${RED}⚠️  Слабый сигнал! Нужна внешняя антенна${NC}"
    elif [ -n "$rsrp" ] && [ "$rsrp" -lt -100 ]; then
        echo -e "${YELLOW}🟡 Сигнал средний, возможны проблемы со скоростью${NC}"
    else
        echo -e "${GREEN}✅ Сигнал хороший${NC}"
    fi

    # Получаем информацию о сети
    local network_info=$(huawei_api_request "$modem_ip" "/api/net/current-network")
    local network_type=$(parse_xml_value "$network_info" "CurrentNetworkType")
    local operator=$(parse_xml_value "$network_info" "FullName")

    echo ""
    echo "🌐 Информация о сети:"
    echo "  Оператор: ${operator:-"N/A"}"

    # Декодируем тип сети
    case "$network_type" in
        "19") echo -e "  📡 ${GREEN}LTE (4G)${NC}" ;;
        "9"|"10"|"11") echo -e "  📡 ${YELLOW}3G/HSPA+${NC}" ;;
        "3"|"1"|"2") echo -e "  📡 ${RED}2G/EDGE${NC}" ;;
        *) echo "  📡 Неизвестный тип: $network_type" ;;
    esac

    # Получаем информацию о LTE Band
    if [ "$network_type" = "19" ]; then
        local lte_info=$(huawei_api_request "$modem_ip" "/api/net/net-mode")
        local band_info=$(parse_xml_value "$lte_info" "LTEBand")

        echo "  📻 LTE Band: ${band_info:-"N/A"}"

        # Анализ частотных диапазонов
        case "$band_info" in
            *"B3"*) echo -e "    ${GREEN}🔥 Band 3 (1800 MHz) - отличная скорость${NC}" ;;
            *"B7"*) echo -e "    ${GREEN}🔥 Band 7 (2600 MHz) - максимальная скорость${NC}" ;;
            *"B20"*) echo -e "    ${YELLOW}🐌 Band 20 (800 MHz) - покрытие хорошее, скорость низкая${NC}" ;;
            *"B1"*) echo -e "    ${GREEN}⚡ Band 1 (2100 MHz) - хорошая скорость${NC}" ;;
        esac
    fi

    # Проверяем режим сети
    local net_mode_info=$(huawei_api_request "$modem_ip" "/api/net/net-mode")
    local network_mode_setting=$(parse_xml_value "$net_mode_info" "NetworkMode")

    echo ""
    echo "🔧 Настройки сети:"
    case "$network_mode_setting" in
        "00") echo -e "  📶 ${YELLOW}Автовыбор сети (может вызывать переключения)${NC}" ;;
        "03") echo -e "  📶 ${GREEN}Только LTE${NC}" ;;
        "02") echo "  📶 Только 3G" ;;
        "01") echo "  📶 Только 2G" ;;
        *) echo "  📶 Неизвестный режим: $network_mode_setting" ;;
    esac

    # Тест скорости интерфейса
    local interface="${MODEM_INTERFACES[$modem_ip]}"
    if [ -n "$interface" ]; then
        echo ""
        echo "🌐 Тест соединения через $interface:"
        echo -n "  Проверка интернета... "

        if timeout 10 curl -s --interface "$interface" http://httpbin.org/ip >/dev/null 2>&1; then
            local external_ip=$(timeout 10 curl -s --interface "$interface" http://httpbin.org/ip 2>/dev/null | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
            echo -e "${GREEN}✅ Работает${NC}"
            echo "  Внешний IP: ${external_ip:-"N/A"}"
        else
            echo -e "${RED}❌ Не работает${NC}"
        fi
    fi

    # Рекомендации
    echo ""
    echo -e "${CYAN}💡 Рекомендации:${NC}"

    if [ -n "$rsrp" ] && [ "$rsrp" -lt -105 ]; then
        echo -e "${RED}📡 КРИТИЧНО: Установите внешнюю MIMO антенну!${NC}"
    fi

    if [ "$network_mode_setting" = "00" ]; then
        echo -e "${YELLOW}⚙️  Рекомендуется зафиксировать режим сети${NC}"
    fi

    if [[ "$band_info" == *"B20"* ]] && [[ "$band_info" == *"B3"* || "$band_info" == *"B7"* ]]; then
        echo -e "${YELLOW}📻 Рекомендуется отключить Band 20 для увеличения скорости${NC}"
    fi

    echo ""
    echo -e "${BLUE}🌐 Веб-интерфейс: http://$modem_ip${NC}"
}

# Функция оптимизации одного модема (остается как есть)
optimize_single_modem() {
    local modem_ip=$1
    local model="${MODEM_WEB_IPS[$modem_ip]}"

    echo ""
    echo -e "${CYAN}⚡ Оптимизация модема: $model ($modem_ip)${NC}"
    echo "============================================="

    # Получаем текущее состояние
    local signal_info=$(huawei_api_request "$modem_ip" "/api/device/signal")
    local rsrp=$(parse_xml_value "$signal_info" "rsrp")
    local network_info=$(huawei_api_request "$modem_ip" "/api/net/current-network")
    local network_type=$(parse_xml_value "$network_info" "CurrentNetworkType")

    echo "🔍 Анализ текущего состояния..."
    echo "  RSRP: ${rsrp:-"N/A"} dBm"
    echo "  Тип сети: $network_type"

    local optimizations_applied=0

    # Оптимизация 1: Фиксируем LTE если сигнал хороший
    if [ -n "$rsrp" ] && [ "$rsrp" -gt -105 ] && [ "$network_type" = "19" ]; then
        echo ""
        echo "🔧 Применяем оптимизацию 1: Фиксируем режим LTE..."
        huawei_api_request "$modem_ip" "/api/net/net-mode" "POST" \
            '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>3FFFFFFF</NetworkBand></request>' >/dev/null
        echo -e "${GREEN}✅ Режим LTE зафиксирован${NC}"
        optimizations_applied=$((optimizations_applied + 1))
        sleep 2
    fi

    # Оптимизация 2: Оптимизируем частотные диапазоны
    local lte_info=$(huawei_api_request "$modem_ip" "/api/net/net-mode")
    local band_info=$(parse_xml_value "$lte_info" "LTEBand")

    if [[ "$band_info" == *"B3"* || "$band_info" == *"B7"* ]]; then
        echo ""
        echo "🔧 Применяем оптимизацию 2: Оптимизируем частотные диапазоны..."
        # Оставляем только высокоскоростные Band'ы (3,7,1)
        huawei_api_request "$modem_ip" "/api/net/net-mode" "POST" \
            '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>C5</NetworkBand></request>' >/dev/null
        echo -e "${GREEN}✅ Частотные диапазоны оптимизированы${NC}"
        optimizations_applied=$((optimizations_applied + 1))
        sleep 2
    fi

    # Оптимизация 3: Перезагрузка для применения настроек
    if [ $optimizations_applied -gt 0 ]; then
        echo ""
        echo "🔄 Перезагружаем модем для применения настроек..."
        huawei_api_request "$modem_ip" "/api/device/control" "POST" \
            '<?xml version="1.0" encoding="UTF-8"?><request><Control>1</Control></request>' >/dev/null

        echo "⏳ Ждем перезагрузки (20 секунд)..."
        sleep 20

        echo -e "${GREEN}✅ Оптимизация завершена!${NC}"
        echo "📊 Применено оптимизаций: $optimizations_applied"
    else
        echo ""
        echo -e "${YELLOW}ℹ️  Оптимизация не требуется или невозможна${NC}"
        echo "💡 Возможные причины:"
        echo "  - Слабый сигнал (нужна антенна)"
        echo "  - Модем не в LTE сети"
        echo "  - Настройки уже оптимальны"
    fi
}

# Основная функция диагностики
run_diagnostics() {
    local target=$1

    if [ "$target" = "ALL" ]; then
        echo -e "${CYAN}🔍 Диагностика всех найденных модемов${NC}"
        echo "====================================="

        local counter=1
        for ip in "${!MODEM_WEB_IPS[@]}"; do
            echo ""
            echo -e "${PURPLE}[$counter/${#MODEM_WEB_IPS[@]}]${NC}"
            diagnose_single_modem "$ip"
            counter=$((counter + 1))

            if [ $counter -le ${#MODEM_WEB_IPS[@]} ]; then
                echo ""
                read -p "Нажмите Enter для продолжения..." -r
            fi
        done
    else
        diagnose_single_modem "$target"
    fi

    echo ""
    echo -e "${GREEN}🏁 Диагностика завершена!${NC}"
}

# Основная функция оптимизации
run_optimization() {
    local target=$1

    if [ "$target" = "ALL" ]; then
        echo -e "${CYAN}⚡ Оптимизация всех найденных модемов${NC}"
        echo "===================================="

        echo -e "${YELLOW}⚠️  Внимание: Будут оптимизированы все модемы!${NC}"
        echo "Это может временно прервать интернет-соединения."
        echo ""
        read -p "Продолжить? (y/N): " -n 1 -r
        echo ""

        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}❌ Оптимизация отменена${NC}"
            return
        fi

        local counter=1
        for ip in "${!MODEM_WEB_IPS[@]}"; do
            echo ""
            echo -e "${PURPLE}[$counter/${#MODEM_WEB_IPS[@]}]${NC}"
            optimize_single_modem "$ip"
            counter=$((counter + 1))

            if [ $counter -le ${#MODEM_WEB_IPS[@]} ]; then
                echo ""
                echo "⏳ Пауза между оптимизациями (5 секунд)..."
                sleep 5
            fi
        done
    else
        echo -e "${YELLOW}⚠️  Внимание: Модем будет перезагружен!${NC}"
        echo "Это может временно прервать интернет-соединение."
        echo ""
        read -p "Продолжить оптимизацию? (y/N): " -n 1 -r
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            optimize_single_modem "$target"
        else
            echo -e "${YELLOW}❌ Оптимизация отменена${NC}"
        fi
    fi

    echo ""
    echo -e "${GREEN}🏁 Оптимизация завершена!${NC}"
}

# Главное меню
show_main_menu() {
    while true; do
        echo ""
        echo -e "${CYAN}🔧 Главное меню${NC}"
        echo "=============="
        echo -e "${PURPLE}1)${NC} 🔍 Диагностика модемов"
        echo -e "${PURPLE}2)${NC} ⚡ Оптимизация модемов"
        echo -e "${PURPLE}3)${NC} 🔄 Обновить список модемов"
        echo -e "${PURPLE}0)${NC} 🚪 Выход"
        echo ""

        read -p "Выберите действие (0-3): " choice

        case $choice in
            1)
                if [ ${#MODEM_WEB_IPS[@]} -eq 0 ]; then
                    echo -e "${RED}❌ Нет доступных модемов для диагностики${NC}"
                    continue
                fi
                show_modem_selection_menu "diagnose"
                run_diagnostics "$selected_option"
                ;;
            2)
                if [ ${#MODEM_WEB_IPS[@]} -eq 0 ]; then
                    echo -e "${RED}❌ Нет доступных модемов для оптимизации${NC}"
                    continue
                fi
                show_modem_selection_menu "optimize"
                run_optimization "$selected_option"
                ;;
            3)
                echo -e "${BLUE}🔄 Обновление списка модемов...${NC}"
                unset MODEM_WEB_IPS
                unset MODEM_INTERFACES
                unset MODEM_DETAILS
                declare -A MODEM_WEB_IPS
                declare -A MODEM_INTERFACES
                declare -A MODEM_DETAILS
                discover_modem_web_interfaces
                ;;
            0)
                echo -e "${GREEN}👋 До свидания!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}❌ Неверный выбор. Введите число от 0 до 3${NC}"
                ;;
        esac
    done
}

# Проверка зависимостей
check_dependencies() {
    local missing_deps=()

    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi

    if ! command -v ping &> /dev/null; then
        missing_deps+=("ping")
    fi

    if ! command -v timeout &> /dev/null; then
        missing_deps+=("timeout")
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo -e "${RED}❌ Отсутствуют зависимости: ${missing_deps[*]}${NC}"
        echo "Установите их командой:"
        echo "sudo apt install ${missing_deps[*]}"
        exit 1
    fi
}

# Главная функция
main() {
    echo ""
    echo -e "${GREEN}Проверка зависимостей...${NC}"
    check_dependencies

    echo ""
    echo -e "${GREEN}Поиск USB модемов в системе...${NC}"

    # Проверяем наличие Huawei устройств
    local found_usb_modems=false
    for modem_id in "${HUAWEI_MODEMS[@]}"; do
        if lsusb | grep -q "$modem_id"; then
            found_usb_modems=true
            echo -e "${GREEN}✅ Найден USB модем: ${MODEM_NAMES[$modem_id]} ($modem_id)${NC}"
        fi
    done

    if [ "$found_usb_modems" = false ]; then
        echo -e "${RED}❌ USB модемы Huawei не найдены${NC}"
        echo ""
        echo -e "${YELLOW}💡 Убедитесь, что:${NC}"
        echo "  - Модемы подключены к USB портам"
        echo "  - Модемы включены и инициализированы"
        echo "  - SIM-карты вставлены"
        echo ""
        echo -e "${CYAN}🔧 Попробуйте поиск веб-интерфейсов без проверки USB...${NC}"
        read -p "Продолжить поиск веб-интерфейсов? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    echo ""
    if ! discover_modem_web_interfaces; then
        echo -e "${YELLOW}⚠️  Веб-интерфейсы не найдены автоматически${NC}"
        echo ""
        echo -e "${CYAN}🔧 Ручная проверка:${NC}"
        echo "1. Откройте браузер и попробуйте: http://192.168.107.1"
        echo "2. Выполните: curl -s http://192.168.107.1/api/device/information"
        echo "3. Проверьте маршруты: ip route show"
        echo "4. Проверьте интерфейсы: ip addr show"
        exit 1
    fi

    show_main_menu
}

# Запуск программы
main "$@"

