#!/bin/bash
# Универсальный скрипт диагностики и настройки мобильных модемов
# Автоматически определяет интерфейсы и настраивает маршрутизацию

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Глобальные переменные
declare -A MODEM_INTERFACES
declare -A MODEM_IPS
declare -A MODEM_GATEWAYS
declare -A MODEM_NETWORKS
declare -a AVAILABLE_INTERFACES

echo -e "${BLUE}🔧 Универсальная диагностика и настройка модемов${NC}"
echo "========================================================"
echo ""

# Функция для определения всех USB сетевых интерфейсов
detect_usb_interfaces() {
    echo -e "${CYAN}1. 🔍 Поиск USB сетевых интерфейсов...${NC}"
    echo "============================================"

    AVAILABLE_INTERFACES=()

    # Поиск всех USB интерфейсов (enx*, usb*, wwan*)
    for interface in $(ip link show | grep -E "enx[0-9a-f]+|usb[0-9]+|wwan[0-9]+" | cut -d: -f2 | tr -d ' '); do
        # Проверяем что интерфейс активен или может быть активирован
        state=$(ip link show "$interface" | grep -o "state [A-Z]*" | cut -d' ' -f2)

        echo -n "  📡 $interface (состояние: $state)... "

        # Пытаемся поднять интерфейс если он DOWN
        if [ "$state" = "DOWN" ]; then
            sudo ip link set "$interface" up >/dev/null 2>&1
            sleep 1
            state=$(ip link show "$interface" | grep -o "state [A-Z]*" | cut -d' ' -f2)
        fi

        if [ "$state" = "UP" ] || [ "$state" = "UNKNOWN" ]; then
            # Получаем текущий IP
            current_ip=$(ip addr show "$interface" | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | head -1)

            if [ -n "$current_ip" ]; then
                echo -e "${GREEN}✅ IP: $current_ip${NC}"
                AVAILABLE_INTERFACES+=("$interface")
                MODEM_IPS["$interface"]="$current_ip"

                # Определяем сеть и возможный шлюз
                network=$(ip route show dev "$interface" | grep "proto kernel" | awk '{print $1}' | head -1)
                if [ -n "$network" ]; then
                    MODEM_NETWORKS["$interface"]="$network"
                    # Вычисляем IP шлюза (обычно .1 в сети)
                    gateway=$(echo "$network" | sed 's/0\/24/1/' | sed 's/\.0\//\.1\//' | cut -d/ -f1)
                    MODEM_GATEWAYS["$interface"]="$gateway"
                fi
            else
                echo -e "${YELLOW}⚠️ Нет IP${NC}"
                AVAILABLE_INTERFACES+=("$interface")
                MODEM_IPS["$interface"]="no_ip"
            fi
        else
            echo -e "${RED}❌ Недоступен${NC}"
        fi
    done

    echo ""

    if [ ${#AVAILABLE_INTERFACES[@]} -eq 0 ]; then
        echo -e "${RED}❌ USB сетевые интерфейсы не найдены${NC}"
        echo ""
        echo "🔧 Возможные решения:"
        echo "1. Убедитесь что USB модемы подключены"
        echo "2. Проверьте что модемы переключены в режим модема (не mass storage)"
        echo "3. Попробуйте команду: sudo ./setup_e3372.sh"
        exit 1
    fi

    echo -e "${GREEN}✅ Найдено USB интерфейсов: ${#AVAILABLE_INTERFACES[@]}${NC}"
}

# Функция проверки модема по IP
check_modem_web_interface() {
    local gateway_ip="$1"
    local interface="$2"

    echo -n "    🌐 Веб-интерфейс $gateway_ip... "

    # Проверяем пинг
    if ! timeout 3 ping -c 1 -W 1 "$gateway_ip" >/dev/null 2>&1; then
        echo -e "${RED}❌ Не отвечает на пинг${NC}"
        return 1
    fi

    # Проверяем HTTP
    web_response=$(timeout 5 curl -s "http://$gateway_ip" 2>/dev/null)
    if [ -n "$web_response" ]; then
        # Ищем признаки Huawei модема
        if echo "$web_response" | grep -qi "huawei\|hilink\|mobile.*wifi\|lte\|4g"; then
            echo -e "${GREEN}✅ Huawei модем${NC}"

            # Проверяем API
            echo -n "    📡 API... "
            api_response=$(timeout 5 curl -s "http://$gateway_ip/api/webserver/SesTokInfo" 2>/dev/null)
            if [ -n "$api_response" ] && echo "$api_response" | grep -q "SesInfo"; then
                echo -e "${GREEN}✅ Работает${NC}"
            else
                echo -e "${YELLOW}⚠️ Недоступен${NC}"
            fi
            return 0
        else
            echo -e "${YELLOW}⚠️ Не Huawei${NC}"
            return 1
        fi
    else
        echo -e "${RED}❌ HTTP недоступен${NC}"
        return 1
    fi
}

# Функция получения IP через DHCP
get_ip_via_dhcp() {
    local interface="$1"

    echo "    🌐 Получение IP через DHCP..."

    # Останавливаем существующие процессы dhclient
    sudo pkill -f "dhclient.*$interface" 2>/dev/null || true

    # Очищаем существующие IP
    sudo ip addr flush dev "$interface" 2>/dev/null || true

    # Поднимаем интерфейс
    sudo ip link set "$interface" up
    sleep 2

    # Запускаем dhclient с таймаутом
    echo "    ⏳ Ожидание DHCP ответа (15 секунд)..."
    timeout 15 sudo dhclient -v "$interface" >/dev/null 2>&1 &
    local dhcp_pid=$!

    # Ждем получения IP
    for i in {1..15}; do
        if ip addr show "$interface" | grep -q "inet "; then
            local new_ip=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | cut -d/ -f1 | head -1)
            echo -e "    ${GREEN}✅ IP получен: $new_ip${NC}"
            MODEM_IPS["$interface"]="$new_ip"

            # Определяем сеть и шлюз
            local network=$(ip route show dev "$interface" | grep "proto kernel" | awk '{print $1}' | head -1)
            if [ -n "$network" ]; then
                MODEM_NETWORKS["$interface"]="$network"
                local gateway=$(echo "$network" | sed 's/0\/24/1/' | sed 's/\.0\//\.1\//' | cut -d/ -f1)
                MODEM_GATEWAYS["$interface"]="$gateway"
            fi

            kill $dhcp_pid 2>/dev/null || true
            return 0
        fi
        sleep 1
    done

    kill $dhcp_pid 2>/dev/null || true
    echo -e "    ${RED}❌ IP не получен${NC}"
    return 1
}

# Функция анализа интерфейса
analyze_interface() {
    local interface="$1"

    echo ""
    echo -e "${CYAN}🔍 Анализ интерфейса: $interface${NC}"
    echo "========================================"

    # Проверяем состояние интерфейса
    local state=$(ip link show "$interface" | grep -o "state [A-Z]*" | cut -d' ' -f2)
    echo "  📡 Состояние интерфейса: $state"

    # Поднимаем если нужно
    if [ "$state" = "DOWN" ]; then
        echo "  🔧 Поднимаем интерфейс..."
        sudo ip link set "$interface" up
        sleep 2
    fi

    # Проверяем IP
    local current_ip="${MODEM_IPS[$interface]}"
    if [ "$current_ip" = "no_ip" ] || [ -z "$current_ip" ]; then
        echo "  ⚠️ IP адрес отсутствует, попытка получения..."
        if get_ip_via_dhcp "$interface"; then
            current_ip="${MODEM_IPS[$interface]}"
        else
            echo -e "  ${RED}❌ Не удалось получить IP адрес${NC}"
            return 1
        fi
    else
        echo -e "  ${GREEN}✅ IP адрес: $current_ip${NC}"
    fi

    # Определяем шлюз модема
    local gateway="${MODEM_GATEWAYS[$interface]}"
    local network="${MODEM_NETWORKS[$interface]}"

    echo "  🌐 Сеть: $network"
    echo "  🚪 Предполагаемый шлюз: $gateway"

    # Проверяем модем
    if check_modem_web_interface "$gateway" "$interface"; then
        MODEM_INTERFACES["$interface"]="verified"
    else
        MODEM_INTERFACES["$interface"]="unverified"
    fi

    # Проверяем маршрутизацию
    echo "  📍 Текущие маршруты:"
    local routes=$(ip route show dev "$interface")
    if [ -n "$routes" ]; then
        echo "$routes" | sed 's/^/    /'
    else
        echo "    Нет маршрутов"
    fi

    # Проверяем шлюз по умолчанию
    local default_gw=$(ip route show default | grep "$interface" | awk '{print $3}' | head -1)
    if [ -n "$default_gw" ]; then
        echo -e "  ${GREEN}✅ Шлюз по умолчанию: $default_gw${NC}"
    else
        echo -e "  ${YELLOW}⚠️ Шлюз по умолчанию не настроен${NC}"
    fi

    return 0
}

# Функция настройки маршрутизации
setup_routing() {
    local interface="$1"
    local current_ip="${MODEM_IPS[$interface]}"
    local gateway="${MODEM_GATEWAYS[$interface]}"
    local network="${MODEM_NETWORKS[$interface]}"

    echo ""
    echo -e "${PURPLE}🛣️ Настройка маршрутизации для $interface${NC}"
    echo "=================================================="

    echo "  📊 Параметры:"
    echo "    Интерфейс: $interface"
    echo "    IP: $current_ip"
    echo "    Сеть: $network"
    echo "    Шлюз: $gateway"
    echo ""

    # Проверяем доступность шлюза
    echo -n "  🔍 Проверка доступности шлюза... "
    if timeout 3 ping -c 1 -W 1 "$gateway" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Доступен${NC}"
    else
        echo -e "${RED}❌ Недоступен${NC}"
        echo "  ⚠️ Маршрутизация может не работать"
    fi

    # Удаляем старые маршруты для этой сети
    echo "  🧹 Очистка старых маршрутов..."
    sudo ip route del "$network" dev "$interface" 2>/dev/null || true
    sudo ip route del default via "$gateway" dev "$interface" 2>/dev/null || true

    # Добавляем маршрут к сети
    echo "  ➕ Добавление маршрута к сети..."
    if sudo ip route add "$network" dev "$interface" 2>/dev/null; then
        echo -e "    ${GREEN}✅ Маршрут к сети добавлен${NC}"
    else
        echo -e "    ${YELLOW}⚠️ Маршрут к сети уже существует${NC}"
    fi

    # Добавляем шлюз по умолчанию с метрикой
    echo "  ➕ Добавление шлюза по умолчанию..."

    # Используем разные метрики для разных интерфейсов
    local metric=600
    case "$interface" in
        *enx*) metric=600 ;;
        *usb*) metric=700 ;;
        *wwan*) metric=800 ;;
    esac

    if sudo ip route add default via "$gateway" dev "$interface" metric $metric 2>/dev/null; then
        echo -e "    ${GREEN}✅ Шлюз по умолчанию добавлен (метрика: $metric)${NC}"
    else
        echo -e "    ${YELLOW}⚠️ Шлюз по умолчанию уже существует${NC}"
    fi

    # Проверяем результат
    echo "  📋 Итоговые маршруты:"
    ip route show dev "$interface" | sed 's/^/    /'

    return 0
}

# Функция тестирования интернета
test_internet() {
    local interface="$1"

    echo ""
    echo -e "${CYAN}🌐 Тестирование интернета через $interface${NC}"
    echo "================================================="

    # Тест 1: Пинг DNS
    echo -n "  📡 Ping Google DNS (8.8.8.8)... "
    if timeout 5 ping -I "$interface" -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Работает${NC}"
    else
        echo -e "${RED}❌ Не работает${NC}"
    fi

    # Тест 2: DNS разрешение
    echo -n "  🔍 DNS разрешение... "
    if timeout 5 nslookup google.com >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Работает${NC}"
    else
        echo -e "${RED}❌ Не работает${NC}"
    fi

    # Тест 3: HTTP запрос
    echo -n "  🌐 HTTP запрос (определение внешнего IP)... "
    local http_result=$(timeout 10 curl --interface "$interface" -s http://httpbin.org/ip 2>/dev/null)
    if [ -n "$http_result" ] && echo "$http_result" | grep -q "origin"; then
        local external_ip=$(echo "$http_result" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
        echo -e "${GREEN}✅ Работает${NC}"
        echo -e "    ${CYAN}🌍 Внешний IP: $external_ip${NC}"
        return 0
    else
        echo -e "${RED}❌ Не работает${NC}"
        return 1
    fi
}

# Функция сохранения конфигурации
save_config() {
    local interface="$1"
    local current_ip="${MODEM_IPS[$interface]}"
    local gateway="${MODEM_GATEWAYS[$interface]}"
    local network="${MODEM_NETWORKS[$interface]}"

    local config_file="${interface}_config.json"

    # Проверяем интернет для определения внешнего IP
    local external_ip="unknown"
    local internet_working="false"
    local http_result=$(timeout 10 curl --interface "$interface" -s http://httpbin.org/ip 2>/dev/null)
    if [ -n "$http_result" ] && echo "$http_result" | grep -q "origin"; then
        external_ip=$(echo "$http_result" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
        internet_working="true"
    fi

    cat > "$config_file" << EOF
{
  "device_type": "huawei_modem",
  "interface": "$interface",
  "connection": {
    "local_ip": "$current_ip",
    "gateway_ip": "$gateway",
    "network": "$network"
  },
  "status": {
    "interface_up": true,
    "ip_assigned": true,
    "gateway_accessible": true,
    "internet_working": $internet_working
  },
  "external_ip": "$external_ip",
  "api_endpoints": {
    "base_url": "http://$gateway",
    "session_token": "/api/webserver/SesTokInfo",
    "device_info": "/api/device/information",
    "signal_status": "/api/device/signal"
  },
  "integration": {
    "detection_method": "dhcp_interface",
    "monitoring_interval": 60,
    "rotation_method": "api_calls"
  },
  "routing": {
    "metric": 600,
    "auto_default_route": true,
    "priority": "normal"
  }
}
EOF

    echo -e "  ${GREEN}✅ Конфигурация сохранена: $config_file${NC}"
}

# Функция диалога выбора
show_interface_dialog() {
    echo ""
    echo -e "${BLUE}📋 Выберите интерфейс для настройки:${NC}"
    echo "======================================="
    echo ""

    local i=1
    for interface in "${AVAILABLE_INTERFACES[@]}"; do
        local ip="${MODEM_IPS[$interface]}"
        local status=""

        if [ "$ip" != "no_ip" ] && [ -n "$ip" ]; then
            if [ "${MODEM_INTERFACES[$interface]}" = "verified" ]; then
                status="${GREEN}✅ Готов (IP: $ip)${NC}"
            else
                status="${YELLOW}⚠️ Требует настройки (IP: $ip)${NC}"
            fi
        else
            status="${RED}❌ Нет IP адреса${NC}"
        fi

        echo -e "  $i) $interface - $status"
        i=$((i + 1))
    done

    echo ""
    echo -e "  0) ${CYAN}🔧 Настроить ВСЕ интерфейсы${NC}"
    echo -e "  q) ${RED}❌ Выход${NC}"
    echo ""

    while true; do
        read -p "Ваш выбор: " choice

        case "$choice" in
            0)
                return 0  # Настроить все
                ;;
            q|Q)
                echo "Выход..."
                exit 0
                ;;
            [1-9]*)
                if [ "$choice" -le "${#AVAILABLE_INTERFACES[@]}" ] && [ "$choice" -gt 0 ]; then
                    return $choice  # Номер интерфейса
                else
                    echo -e "${RED}❌ Неверный выбор. Попробуйте снова.${NC}"
                fi
                ;;
            *)
                echo -e "${RED}❌ Неверный ввод. Введите число от 0 до ${#AVAILABLE_INTERFACES[@]} или 'q'.${NC}"
                ;;
        esac
    done
}

# Функция настройки одного интерфейса
configure_interface() {
    local interface="$1"

    echo ""
    echo -e "${PURPLE}⚙️ НАСТРОЙКА ИНТЕРФЕЙСА: $interface${NC}"
    echo "======================================================="

    # Анализ
    if ! analyze_interface "$interface"; then
        echo -e "${RED}❌ Анализ интерфейса $interface не удался${NC}"
        return 1
    fi

    # Настройка маршрутизации
    setup_routing "$interface"

    # Тестирование
    if test_internet "$interface"; then
        echo -e "${GREEN}✅ Интерфейс $interface успешно настроен и работает${NC}"
        save_config "$interface"
        return 0
    else
        echo -e "${RED}❌ Интерфейс $interface настроен, но интернет не работает${NC}"
        save_config "$interface"
        return 1
    fi
}

# Функция настройки всех интерфейсов
configure_all_interfaces() {
    echo ""
    echo -e "${PURPLE}⚙️ НАСТРОЙКА ВСЕХ ИНТЕРФЕЙСОВ${NC}"
    echo "======================================="

    local success_count=0
    local total_count=${#AVAILABLE_INTERFACES[@]}

    for interface in "${AVAILABLE_INTERFACES[@]}"; do
        if configure_interface "$interface"; then
            success_count=$((success_count + 1))
        fi
        echo ""
    done

    echo -e "${BLUE}📊 ИТОГОВЫЙ РЕЗУЛЬТАТ:${NC}"
    echo "================================="
    echo -e "  Всего интерфейсов: $total_count"
    echo -e "  ${GREEN}Успешно настроено: $success_count${NC}"
    echo -e "  ${RED}С ошибками: $((total_count - success_count))${NC}"

    if [ $success_count -eq $total_count ]; then
        echo -e "  ${GREEN}🎉 ВСЕ ИНТЕРФЕЙСЫ РАБОТАЮТ!${NC}"
    elif [ $success_count -gt 0 ]; then
        echo -e "  ${YELLOW}⚠️ Часть интерфейсов работает${NC}"
    else
        echo -e "  ${RED}❌ НИ ОДИН ИНТЕРФЕЙС НЕ РАБОТАЕТ${NC}"
    fi
}

# Основная логика
main() {
    # Проверка прав
    if [ "$EUID" -eq 0 ]; then
        echo -e "${RED}❌ Не запускайте скрипт от root. Используйте sudo только для отдельных команд.${NC}"
        exit 1
    fi

    # Поиск интерфейсов
    detect_usb_interfaces

    # Анализ всех найденных интерфейсов
    echo ""
    echo -e "${CYAN}2. 🔍 Анализ найденных интерфейсов...${NC}"
    echo "============================================"

    for interface in "${AVAILABLE_INTERFACES[@]}"; do
        analyze_interface "$interface" >/dev/null 2>&1
    done

    # Диалог выбора
    show_interface_dialog
    local choice=$?

    if [ $choice -eq 0 ]; then
        # Настроить все интерфейсы
        configure_all_interfaces
    else
        # Настроить выбранный интерфейс
        local selected_interface="${AVAILABLE_INTERFACES[$((choice - 1))]}"
        configure_interface "$selected_interface"
    fi

    echo ""
    echo -e "${BLUE}🏁 Диагностика и настройка завершена!${NC}"
    echo "============================================"
    echo ""
    echo -e "${CYAN}💡 Полезные команды для проверки:${NC}"
    echo "  ip route show                    # Показать все маршруты"
    echo "  ip addr show                     # Показать все IP адреса"
    echo "  curl --interface <интерфейс> http://httpbin.org/ip  # Тест через интерфейс"
    echo ""
    echo -e "${CYAN}🚀 Следующие шаги:${NC}"
    echo "1. Интегрируйте рабочие интерфейсы в Mobile Proxy Service"
    echo "2. Настройте автоматическую ротацию IP"
    echo "3. Добавьте мониторинг состояния модемов"
}

# Запуск
main "$@"

