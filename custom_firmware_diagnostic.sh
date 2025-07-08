#!/bin/bash
# Специальная диагностика для модемов с кастомной прошивкой
# Анализирует структуру и возможности модема без стандартных предположений

echo "🔧 Диагностика модема с кастомной прошивкой"
echo "============================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# IP адрес модема (из ваших данных)
MODEM_IP="192.168.107.1"
INTERFACE="enx0c5b8f279a64"  # Из вашего ip a

echo "🎯 Целевой модем: $MODEM_IP"
echo "🌐 Интерфейс: $INTERFACE"
echo ""

# Функция для безопасного curl с таймаутом
safe_curl() {
    local url=$1
    local additional_args=${2:-""}
    timeout 5 curl -s --connect-timeout 3 $additional_args "$url" 2>/dev/null
}

# Функция для проверки доступности
check_connectivity() {
    echo -e "${BLUE}1. Проверка базовой доступности${NC}"
    echo "================================================"

    echo -n "🌐 Ping тест... "
    if timeout 3 ping -c 1 -W 1 "$MODEM_IP" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Доступен${NC}"
    else
        echo -e "${RED}❌ Недоступен${NC}"
        exit 1
    fi

    echo -n "🔌 HTTP тест... "
    if safe_curl "http://$MODEM_IP" >/dev/null; then
        echo -e "${GREEN}✅ HTTP работает${NC}"
    else
        echo -e "${RED}❌ HTTP недоступен${NC}"
        exit 1
    fi

    echo -n "🔒 HTTPS тест... "
    if safe_curl "https://$MODEM_IP" >/dev/null; then
        echo -e "${GREEN}✅ HTTPS работает${NC}"
    else
        echo -e "${YELLOW}⚠️ HTTPS недоступен${NC}"
    fi
    echo ""
}

# Анализ главной страницы
analyze_homepage() {
    echo -e "${BLUE}2. Анализ главной страницы${NC}"
    echo "================================================"

    local homepage=$(safe_curl "http://$MODEM_IP")

    if [ -z "$homepage" ]; then
        echo -e "${RED}❌ Не удалось получить главную страницу${NC}"
        return 1
    fi

    echo "📄 Размер ответа: $(echo "$homepage" | wc -c) байт"
    echo "📝 Первые 200 символов:"
    echo "$homepage" | head -c 200
    echo ""

    # Анализ содержимого
    echo "🔍 Поиск ключевых элементов:"

    # Поиск различных признаков роутера/модема
    patterns=(
        "huawei|HUAWEI"
        "router|Router|ROUTER"
        "modem|Modem|MODEM"
        "4g|4G|LTE|lte"
        "hilink|HiLink|HILINK"
        "admin|Admin|ADMIN"
        "login|Login|LOGIN"
        "password|Password|PASSWORD"
        "api|API"
        "device|Device|DEVICE"
        "status|Status|STATUS"
        "signal|Signal|SIGNAL"
        "network|Network|NETWORK"
        "wifi|WiFi|WIFI"
        "mobile|Mobile|MOBILE"
    )

    for pattern in "${patterns[@]}"; do
        if echo "$homepage" | grep -qi "$pattern"; then
            echo -e "  ✅ Найдено: ${GREEN}$pattern${NC}"
        fi
    done

    echo ""
    echo "🏷️ HTML теги и мета-информация:"
    echo "$homepage" | grep -i "<title>" | head -1
    echo "$homepage" | grep -i "generator\|author\|description" | head -3
    echo ""
}

# Сканирование возможных путей
scan_endpoints() {
    echo -e "${BLUE}3. Сканирование API endpoints${NC}"
    echo "================================================"

    # Стандартные Huawei пути
    local huawei_paths=(
        "/api/device/information"
        "/api/device/signal"
        "/api/monitoring/status"
        "/api/webserver/SesTokInfo"
        "/api/net/current-network"
        "/api/net/net-mode"
        "/api/device/control"
        "/api/wlan/basic-settings"
        "/api/monitoring/traffic-statistics"
    )

    # Альтернативные пути для кастомных прошивок
    local custom_paths=(
        "/status"
        "/info"
        "/device"
        "/api"
        "/cgi-bin/luci"
        "/cgi-bin/api"
        "/admin"
        "/config"
        "/system"
        "/modem"
        "/mobile"
        "/lte"
        "/4g"
        "/json"
        "/xml"
        "/data"
        "/stats"
        "/signal"
        "/network"
    )

    # OpenWrt пути (часто используются в кастомных прошивках)
    local openwrt_paths=(
        "/cgi-bin/luci/rpc/uci"
        "/cgi-bin/luci/rpc/sys"
        "/ubus"
        "/cgi-bin/status"
        "/cgi-bin/config"
    )

    echo "🔍 Проверка стандартных Huawei API:"
    for path in "${huawei_paths[@]}"; do
        local response=$(safe_curl "http://$MODEM_IP$path")
        if [ -n "$response" ] && ! echo "$response" | grep -qi "not found\|404\|error"; then
            echo -e "  ✅ ${GREEN}$path${NC} - работает"
            echo "     $(echo "$response" | head -c 100 | tr '\n' ' ')..."
        else
            echo -e "  ❌ $path - недоступен"
        fi
    done

    echo ""
    echo "🔍 Проверка альтернативных путей:"
    for path in "${custom_paths[@]}"; do
        local response=$(safe_curl "http://$MODEM_IP$path")
        if [ -n "$response" ] && ! echo "$response" | grep -qi "not found\|404\|error"; then
            echo -e "  ✅ ${GREEN}$path${NC} - найден!"
            echo "     $(echo "$response" | head -c 100 | tr '\n' ' ')..."
        fi
    done

    echo ""
    echo "🔍 Проверка OpenWrt/LEDE путей:"
    for path in "${openwrt_paths[@]}"; do
        local response=$(safe_curl "http://$MODEM_IP$path")
        if [ -n "$response" ] && ! echo "$response" | grep -qi "not found\|404\|error"; then
            echo -e "  ✅ ${GREEN}$path${NC} - найден!"
            echo "     $(echo "$response" | head -c 100 | tr '\n' ' ')..."
        fi
    done
    echo ""
}

# Попытка авторизации
try_authentication() {
    echo -e "${BLUE}4. Проверка авторизации${NC}"
    echo "================================================"

    # Стандартные логины/пароли для Huawei
    local credentials=(
        "admin:admin"
        "admin:password"
        "admin:"
        "root:admin"
        "user:user"
        "admin:12345"
        "admin:1234"
        "admin:root"
    )

    echo "🔑 Попытка авторизации с стандартными данными:"

    for cred in "${credentials[@]}"; do
        local login=$(echo $cred | cut -d: -f1)
        local pass=$(echo $cred | cut -d: -f2)

        echo -n "  Пробуем $login:$pass... "

        # Попытка Basic Auth
        local auth_response=$(safe_curl "http://$MODEM_IP/api/device/information" "-u $login:$pass")

        if [ -n "$auth_response" ] && echo "$auth_response" | grep -qi "devicename\|imei\|hardware"; then
            echo -e "${GREEN}✅ Успех!${NC}"
            echo "     Ответ: $(echo "$auth_response" | head -c 150)..."
            return 0
        else
            echo -e "${RED}❌${NC}"
        fi
    done

    echo ""
    echo "🔍 Проверка наличия формы авторизации:"
    local login_page=$(safe_curl "http://$MODEM_IP/login")
    if [ -n "$login_page" ]; then
        echo "✅ Найдена страница логина: /login"
    fi

    local admin_page=$(safe_curl "http://$MODEM_IP/admin")
    if [ -n "$admin_page" ]; then
        echo "✅ Найдена админ страница: /admin"
    fi
    echo ""
}

# Анализ сетевых возможностей
analyze_network() {
    echo -e "${BLUE}5. Анализ сетевых возможностей${NC}"
    echo "================================================"

    echo "🌐 Тест интернет-соединения через интерфейс:"

    if [ -n "$INTERFACE" ]; then
        echo "  Интерфейс: $INTERFACE"
        echo "  IP адрес: $(ip addr show $INTERFACE 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)"

        echo -n "  Тест HTTP через интерфейс... "
        local external_test=$(timeout 10 curl --interface "$INTERFACE" -s http://httpbin.org/ip 2>/dev/null)

        if [ -n "$external_test" ]; then
            local external_ip=$(echo "$external_test" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
            echo -e "${GREEN}✅ Работает${NC}"
            echo "  Внешний IP: $external_ip"
        else
            echo -e "${RED}❌ Не работает${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️ Интерфейс не определен${NC}"
    fi

    echo ""
    echo "📊 Информация о маршрутизации:"
    echo "  Маршруты через модем:"
    ip route show | grep "192.168.107" | head -3
    echo ""
}

# Попытка определения типа прошивки
detect_firmware_type() {
    echo -e "${BLUE}6. Определение типа прошивки${NC}"
    echo "================================================"

    local homepage=$(safe_curl "http://$MODEM_IP")
    local api_response=$(safe_curl "http://$MODEM_IP/api")
    local status_response=$(safe_curl "http://$MODEM_IP/status")
    local info_response=$(safe_curl "http://$MODEM_IP/info")

    echo "🔍 Анализ признаков прошивки:"

    # OpenWrt/LEDE
    if echo "$homepage" | grep -qi "openwrt\|lede\|luci"; then
        echo -e "  🎯 ${GREEN}OpenWrt/LEDE обнаружен${NC}"
        echo "    Веб-интерфейс: LuCI"
        echo "    Путь управления: /cgi-bin/luci"
    fi

    # RouterOS
    if echo "$homepage" | grep -qi "mikrotik\|routeros"; then
        echo -e "  🎯 ${GREEN}MikroTik RouterOS обнаружен${NC}"
    fi

    # DD-WRT
    if echo "$homepage" | grep -qi "dd-wrt"; then
        echo -e "  🎯 ${GREEN}DD-WRT обнаружен${NC}"
    fi

    # Кастомная на базе PHP/HTML
    if echo "$homepage" | grep -qi "php\|<\?php"; then
        echo -e "  🎯 ${GREEN}PHP-based интерфейс${NC}"
    fi

    # JSON API
    if echo "$api_response$status_response$info_response" | grep -qi '^\s*{.*}'; then
        echo -e "  🎯 ${GREEN}JSON API доступен${NC}"
        echo "    Проверьте пути: /api, /status, /info"
    fi

    # RESTful API
    if safe_curl "http://$MODEM_IP/api/v1" | grep -qi "json\|api"; then
        echo -e "  🎯 ${GREEN}RESTful API v1 найден${NC}"
    fi

    echo ""
    echo "💡 Рекомендации для интеграции:"

    if echo "$homepage$api_response" | grep -qi "json"; then
        echo "  ✅ Используйте JSON API для получения данных"
        echo "  📖 Изучите структуру ответов /api, /status, /info"
    fi

    if echo "$homepage" | grep -qi "luci"; then
        echo "  ✅ Используйте LuCI RPC для управления"
        echo "  📖 Документация: /cgi-bin/luci/rpc/uci"
    fi

    echo "  🔧 Для ротации IP попробуйте:"
    echo "    - /api/network/restart"
    echo "    - /api/modem/restart"
    echo "    - /cgi-bin/luci/rpc/sys?method=reboot"
    echo "    - AT команды через telnet/ssh"
    echo ""
}

# Тестирование возможностей ротации
test_rotation_capabilities() {
    echo -e "${BLUE}7. Тестирование возможностей ротации IP${NC}"
    echo "================================================"

    # Возможные endpoints для ротации
    local rotation_paths=(
        "/api/device/control"
        "/api/device/reboot"
        "/api/network/restart"
        "/api/modem/restart"
        "/restart"
        "/reboot"
        "/api/system/reboot"
        "/cgi-bin/luci/rpc/sys?method=reboot"
    )

    echo "🔄 Поиск endpoints для ротации IP:"

    for path in "${rotation_paths[@]}"; do
        local response=$(safe_curl "http://$MODEM_IP$path" "-X POST")
        if [ -n "$response" ] && ! echo "$response" | grep -qi "not found\|404\|error\|forbidden"; then
            echo -e "  ✅ ${GREEN}$path${NC} - доступен для POST"
            echo "     $(echo "$response" | head -c 100 | tr '\n' ' ')..."
        fi
    done

    echo ""
    echo "🔌 Проверка доступности SSH/Telnet:"

    echo -n "  SSH (порт 22)... "
    if timeout 3 nc -z "$MODEM_IP" 22 2>/dev/null; then
        echo -e "${GREEN}✅ Доступен${NC}"
        echo "    Попробуйте: ssh root@$MODEM_IP"
    else
        echo -e "${RED}❌ Закрыт${NC}"
    fi

    echo -n "  Telnet (порт 23)... "
    if timeout 3 nc -z "$MODEM_IP" 23 2>/dev/null; then
        echo -e "${GREEN}✅ Доступен${NC}"
        echo "    Попробуйте: telnet $MODEM_IP"
    else
        echo -e "${RED}❌ Закрыт${NC}"
    fi

    echo -n "  HTTP альтернативный (порт 8080)... "
    if timeout 3 nc -z "$MODEM_IP" 8080 2>/dev/null; then
        echo -e "${GREEN}✅ Доступен${NC}"
    else
        echo -e "${RED}❌ Закрыт${NC}"
    fi
    echo ""
}

# Создание рабочего профиля
create_integration_profile() {
    echo -e "${BLUE}8. Создание профиля интеграции${NC}"
    echo "================================================"

    echo "📝 Создаю файл конфигурации для интеграции..."

    cat > "modem_${MODEM_IP//\./_}_profile.json" << EOF
{
  "modem_info": {
    "ip": "$MODEM_IP",
    "interface": "$INTERFACE",
    "detected_firmware": "custom",
    "scan_date": "$(date -Iseconds)"
  },
  "working_endpoints": [
EOF

    # Проверяем рабочие endpoints
    local endpoints_found=false
    local test_paths=("/api/device/information" "/api" "/status" "/info" "/cgi-bin/luci")

    for path in "${test_paths[@]}"; do
        local response=$(safe_curl "http://$MODEM_IP$path")
        if [ -n "$response" ] && ! echo "$response" | grep -qi "not found\|404\|error"; then
            if [ "$endpoints_found" = true ]; then
                echo "," >> "modem_${MODEM_IP//\./_}_profile.json"
            fi
            echo "    {\"path\": \"$path\", \"working\": true}" >> "modem_${MODEM_IP//\./_}_profile.json"
            endpoints_found=true
        fi
    done

    cat >> "modem_${MODEM_IP//\./_}_profile.json" << EOF
  ],
  "integration_recommendations": {
    "api_type": "custom",
    "auth_required": false,
    "rotation_method": "unknown",
    "monitoring_endpoint": "/status"
  }
}
EOF

    echo "✅ Профиль сохранен: modem_${MODEM_IP//\./_}_profile.json"
    echo ""
    echo "🔧 Следующие шаги для интеграции:"
    echo "1. Изучите рабочие endpoints в профиле"
    echo "2. Определите API для получения статуса сигнала"
    echo "3. Найдите способ ротации IP (API/SSH/AT-команды)"
    echo "4. Адаптируйте ваш скрипт диагностики под найденные endpoints"
    echo ""
}

# Главная функция
main() {
    echo "🚀 Начинаю полную диагностику модема с кастомной прошивкой..."
    echo ""

    check_connectivity
    analyze_homepage
    scan_endpoints
    try_authentication
    analyze_network
    detect_firmware_type
    test_rotation_capabilities
    create_integration_profile

    echo -e "${GREEN}🏁 Диагностика завершена!${NC}"
    echo ""
    echo "📋 Сводка:"
    echo "  - IP модема: $MODEM_IP"
    echo "  - Интерфейс: $INTERFACE"
    echo "  - Профиль: modem_${MODEM_IP//\./_}_profile.json"
    echo ""
    echo "💡 Для интеграции с вашим проектом используйте найденные endpoints"
    echo "   и адаптируйте код в backend/app/core/device_manager.py"
}

# Проверка зависимостей
if ! command -v curl &> /dev/null; then
    echo -e "${RED}❌ curl не установлен. Установите: sudo apt install curl${NC}"
    exit 1
fi

if ! command -v nc &> /dev/null; then
    echo -e "${YELLOW}⚠️ netcat не установлен. Установите: sudo apt install netcat${NC}"
fi

# Запуск
main "$@"
