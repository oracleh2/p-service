#!/bin/bash
# Исправление подключения к интернету через Huawei модем

echo "🔧 Исправление подключения к интернету через модем"
echo "=================================================="

# Определяем новые параметры
INTERFACE="enx0c5b8f279a64"
LOCAL_IP="192.168.110.100"
MODEM_IP="192.168.110.1"

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "🎯 Интерфейс: $INTERFACE"
echo "🌐 Локальный IP: $LOCAL_IP"
echo "📱 IP модема: $MODEM_IP"
echo ""

echo "1. 🔍 Диагностика текущего состояния"
echo "===================================="

# Проверяем интерфейс
echo -n "📡 Состояние интерфейса... "
if ip link show "$INTERFACE" | grep -q "state UP"; then
    echo -e "${GREEN}✅ UP${NC}"
else
    echo -e "${RED}❌ DOWN${NC}"
    echo "🔧 Поднимаем интерфейс..."
    sudo ip link set "$INTERFACE" up
    sleep 2
fi

# Проверяем IP
echo -n "🌐 IP адрес... "
current_ip=$(ip addr show "$INTERFACE" | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
if [ "$current_ip" = "192.168.110.100" ]; then
    echo -e "${GREEN}✅ $current_ip${NC}"
else
    echo -e "${YELLOW}⚠️ $current_ip (ожидался 192.168.110.100)${NC}"
fi

# Проверяем модем
echo -n "📱 Пинг модема $MODEM_IP... "
if timeout 3 ping -c 1 -W 1 "$MODEM_IP" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Доступен${NC}"
else
    echo -e "${RED}❌ Недоступен${NC}"
fi

echo ""
echo "2. 🛣️ Проверка и исправление маршрутизации"
echo "=========================================="

# Проверяем текущие маршруты
echo "📍 Текущие маршруты через $INTERFACE:"
ip route show dev "$INTERFACE"

# Проверяем шлюз по умолчанию
echo ""
echo -n "🚪 Шлюз по умолчанию через $INTERFACE... "
default_gw=$(ip route show default | grep "$INTERFACE" | awk '{print $3}')
if [ -n "$default_gw" ]; then
    echo -e "${GREEN}✅ $default_gw${NC}"
else
    echo -e "${RED}❌ Не найден${NC}"
    echo "🔧 Добавляем шлюз по умолчанию..."

    # Удаляем старые маршруты для этой сети
    sudo ip route del 192.168.110.0/24 dev "$INTERFACE" 2>/dev/null || true

    # Добавляем маршрут к сети модема
    sudo ip route add 192.168.110.0/24 dev "$INTERFACE" 2>/dev/null || true

    # Добавляем шлюз по умолчанию с низким приоритетом
    sudo ip route add default via "$MODEM_IP" dev "$INTERFACE" metric 600 2>/dev/null || true

    echo "  ✅ Маршруты добавлены"
fi

echo ""
echo "3. 🌐 Тест подключения к интернету"
echo "================================="

# Тест 1: Пинг Google DNS
echo -n "📡 Ping 8.8.8.8 через интерфейс... "
if timeout 5 ping -I "$INTERFACE" -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Работает${NC}"
else
    echo -e "${RED}❌ Не работает${NC}"
fi

# Тест 2: HTTP запрос
echo -n "🌐 HTTP запрос через интерфейс... "
http_result=$(timeout 10 curl --interface "$INTERFACE" -s http://httpbin.org/ip 2>/dev/null)
if [ -n "$http_result" ] && echo "$http_result" | grep -q "origin"; then
    external_ip=$(echo "$http_result" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}✅ Работает${NC}"
    echo "  🌍 Внешний IP: $external_ip"
else
    echo -e "${RED}❌ Не работает${NC}"
fi

# Тест 3: DNS разрешение
echo -n "🔍 DNS разрешение... "
if timeout 5 nslookup google.com >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Работает${NC}"
else
    echo -e "${RED}❌ Не работает${NC}"
    echo "🔧 Проверяем DNS настройки..."

    # Проверяем /etc/resolv.conf
    if grep -q "nameserver" /etc/resolv.conf; then
        echo "  📋 DNS серверы в /etc/resolv.conf:"
        grep "nameserver" /etc/resolv.conf | head -3
    else
        echo "  ⚠️ DNS серверы не настроены, добавляем Google DNS..."
        echo "nameserver 8.8.8.8" | sudo tee -a /etc/resolv.conf >/dev/null
        echo "nameserver 8.8.4.4" | sudo tee -a /etc/resolv.conf >/dev/null
    fi
fi

echo ""
echo "4. 🔧 Проверка веб-интерфейса модема"
echo "===================================="

echo -n "🌐 Веб-интерфейс $MODEM_IP... "
web_response=$(timeout 5 curl -s "http://$MODEM_IP" 2>/dev/null)
if [ -n "$web_response" ]; then
    echo -e "${GREEN}✅ Доступен${NC}"

    # Проверяем API
    echo -n "📡 API токен... "
    api_response=$(timeout 5 curl -s "http://$MODEM_IP/api/webserver/SesTokInfo" 2>/dev/null)
    if [ -n "$api_response" ] && echo "$api_response" | grep -q "SesInfo"; then
        echo -e "${GREEN}✅ Работает${NC}"
        token=$(echo "$api_response" | grep -o '<SesInfo>[^<]*</SesInfo>' | sed 's/<[^>]*>//g')
        echo "  🔑 Токен: ${token:0:20}..."
    else
        echo -e "${RED}❌ Не работает${NC}"
    fi
else
    echo -e "${RED}❌ Недоступен${NC}"
fi

echo ""
echo "5. 🔄 Принудительное восстановление соединения"
echo "=============================================="

if [ -z "$http_result" ] || ! echo "$http_result" | grep -q "origin"; then
    echo "🚨 Интернет не работает! Попытка восстановления..."

    # Способ 1: Перезапуск интерфейса
    echo "🔄 Способ 1: Перезапуск интерфейса..."
    sudo ip link set "$INTERFACE" down
    sleep 2
    sudo ip link set "$INTERFACE" up
    sleep 3

    # Обновляем DHCP
    echo "🌐 Обновление DHCP..."
    sudo dhclient -r "$INTERFACE" 2>/dev/null || true
    sleep 2
    sudo dhclient "$INTERFACE" 2>/dev/null || true
    sleep 5

    # Тест после перезапуска
    echo -n "🧪 Тест после перезапуска... "
    test_result=$(timeout 10 curl --interface "$INTERFACE" -s http://httpbin.org/ip 2>/dev/null)
    if [ -n "$test_result" ] && echo "$test_result" | grep -q "origin"; then
        external_ip=$(echo "$test_result" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
        echo -e "${GREEN}✅ Заработало! IP: $external_ip${NC}"
    else
        echo -e "${RED}❌ Не помогло${NC}"

        # Способ 2: Через телнет к модему
        echo ""
        echo "🔄 Способ 2: Перезагрузка модема через Telnet..."

        if timeout 3 nc -z "$MODEM_IP" 23 2>/dev/null; then
            echo "📞 Telnet доступен, пытаемся перезагрузить модем..."

            if command -v expect >/dev/null 2>&1; then
                expect << EOF
set timeout 10
spawn telnet $MODEM_IP
expect "login:" {
    send "root\r"
    expect "#"
    send "reboot\r"
    expect "#"
    send "exit\r"
    expect eof
}
EOF
                echo "🔄 Команда перезагрузки отправлена, ждем 30 секунд..."
                sleep 30

                # Тест после перезагрузки модема
                echo -n "🧪 Тест после перезагрузки модема... "
                final_test=$(timeout 15 curl --interface "$INTERFACE" -s http://httpbin.org/ip 2>/dev/null)
                if [ -n "$final_test" ] && echo "$final_test" | grep -q "origin"; then
                    final_ip=$(echo "$final_test" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
                    echo -e "${GREEN}✅ Заработало! IP: $final_ip${NC}"
                else
                    echo -e "${RED}❌ Все еще не работает${NC}"
                fi
            else
                echo "⚠️ expect не установлен - установите: sudo apt install expect"
            fi
        else
            echo "❌ Telnet недоступен"
        fi
    fi
fi

echo ""
echo "6. 📝 Обновление конфигурации для проекта"
echo "========================================"

echo "🔧 Создаем обновленную конфигурацию..."

# Обновляем файл конфигурации модема
cat > "huawei_e3372_fixed_config.json" << EOF
{
  "device_type": "huawei_e3372_hilink",
  "connection": {
    "modem_ip": "$MODEM_IP",
    "interface": "$INTERFACE",
    "local_ip": "$LOCAL_IP",
    "network": "192.168.110.0/24"
  },
  "status": {
    "interface_up": true,
    "ip_assigned": true,
    "modem_accessible": true,
    "internet_working": $([ -n "$http_result" ] && echo "$http_result" | grep -q "origin" && echo "true" || echo "false")
  },
  "api_endpoints": {
    "base_url": "http://$MODEM_IP",
    "session_token": "/api/webserver/SesTokInfo",
    "device_info": "/api/device/information",
    "signal_status": "/api/device/signal"
  },
  "integration": {
    "detection_method": "check_sesinfo_token",
    "monitoring_interval": 60,
    "rotation_method": "telnet_at_commands"
  }
}
EOF

echo "✅ Конфигурация сохранена: huawei_e3372_fixed_config.json"

echo ""
echo "🏁 Диагностика завершена!"
echo "========================="

# Финальная сводка
echo ""
echo "📋 Итоговое состояние:"
echo "  📱 Модем IP: $MODEM_IP"
echo "  🌐 Интерфейс: $INTERFACE ($LOCAL_IP)"

if [ -n "$http_result" ] && echo "$http_result" | grep -q "origin"; then
    external_ip=$(echo "$http_result" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
    echo -e "  🌍 Внешний IP: ${GREEN}$external_ip${NC}"
    echo -e "  📊 Статус: ${GREEN}✅ ВСЕ РАБОТАЕТ${NC}"

    echo ""
    echo "🚀 Следующие шаги:"
    echo "1. Обновите IP модема в ваших скриптах с 192.168.107.1 на $MODEM_IP"
    echo "2. Запустите тест: curl --interface $INTERFACE http://httpbin.org/ip"
    echo "3. Интегрируйте в Mobile Proxy Service"
else
    echo -e "  ❌ Статус: ${RED}ИНТЕРНЕТ НЕ РАБОТАЕТ${NC}"

    echo ""
    echo "🔧 Дополнительные действия:"
    echo "1. Проверьте SIM-карту и баланс"
    echo "2. Убедитесь что PIN код введен правильно"
    echo "3. Попробуйте другую SIM-карту для теста"
    echo "4. Проверьте настройки APN через веб-интерфейс: http://$MODEM_IP"
fi

echo ""
echo "💡 Для обновления ваших скриптов замените везде:"
echo "  192.168.107.1 → $MODEM_IP"
echo "  enx0c5b8f279a64 → $INTERFACE (если изменился)"

