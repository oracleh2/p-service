#!/bin/bash
# Настройка маршрутизации для прокси через HONOR телефон

set -e

HONOR_DEVICE_ID="AH3SCP4B11207250"
USB_INTERFACE="enx566cf3eaaf4b"
PROXY_PORT="8080"

echo "🔧 Setting up routing for proxy through HONOR phone..."

# 1. Проверяем статус USB интерфейса
echo "1. Checking USB interface status..."
if ! ip link show "$USB_INTERFACE" &>/dev/null; then
    echo "❌ USB interface $USB_INTERFACE not found"
    echo "Available interfaces:"
    ip link show | grep -E "^[0-9]+:" | cut -d: -f2 | tr -d ' '
    echo ""
    echo "Please run setup_honor_usb_tethering.sh first"
    exit 1
fi

USB_IP=$(ip addr show "$USB_INTERFACE" | grep "inet " | awk '{print $2}' | cut -d/ -f1)
if [ -z "$USB_IP" ]; then
    echo "❌ No IP address on USB interface $USB_INTERFACE"
    echo "Please configure USB tethering first"
    exit 1
fi

echo "✅ USB interface $USB_INTERFACE has IP: $USB_IP"

# 2. Создаем отдельную таблицу маршрутизации для HONOR
echo "2. Setting up routing table for HONOR..."
HONOR_TABLE="honor_table"
HONOR_TABLE_ID="200"

# Добавляем таблицу если её нет
if ! grep -q "$HONOR_TABLE" /etc/iproute2/rt_tables 2>/dev/null; then
    echo "$HONOR_TABLE_ID $HONOR_TABLE" | sudo tee -a /etc/iproute2/rt_tables
    echo "Added routing table: $HONOR_TABLE"
fi

# 3. Настраиваем маршруты в отдельной таблице
echo "3. Configuring routes in HONOR table..."

# Получаем gateway от HONOR (обычно это IP +1)
HONOR_GATEWAY=$(ip route show dev "$USB_INTERFACE" | grep default | awk '{print $3}')
if [ -z "$HONOR_GATEWAY" ]; then
    # Пытаемся определить gateway автоматически
    NETWORK_BASE=$(echo "$USB_IP" | cut -d. -f1-3)
    HONOR_GATEWAY="${NETWORK_BASE}.1"
    echo "Gateway not found, trying: $HONOR_GATEWAY"
fi

# Очищаем старые правила для HONOR таблицы
sudo ip route flush table "$HONOR_TABLE" 2>/dev/null || true

# Добавляем маршруты в HONOR таблицу
sudo ip route add default via "$HONOR_GATEWAY" dev "$USB_INTERFACE" table "$HONOR_TABLE"
sudo ip route add "$USB_IP/24" dev "$USB_INTERFACE" scope link table "$HONOR_TABLE"

echo "✅ Routes configured for HONOR table"

# 4. Создаем правила маршрутизации для прокси
echo "4. Setting up routing rules for proxy..."

# Удаляем старые правила если есть
sudo ip rule del from "$USB_IP" table "$HONOR_TABLE" 2>/dev/null || true
sudo ip rule del fwmark 0x1 table "$HONOR_TABLE" 2>/dev/null || true

# Добавляем новые правила
sudo ip rule add from "$USB_IP" table "$HONOR_TABLE"
sudo ip rule add fwmark 0x1 table "$HONOR_TABLE"

# 5. Настраиваем iptables для маркировки трафика
echo "5. Configuring iptables for traffic marking..."

# Создаем цепочку для HONOR если её нет
sudo iptables -t mangle -N HONOR_MARK 2>/dev/null || true
sudo iptables -t mangle -F HONOR_MARK

# Маркируем трафик, идущий через прокси
sudo iptables -t mangle -A OUTPUT -p tcp --sport "$PROXY_PORT" -j MARK --set-mark 0x1
sudo iptables -t mangle -A OUTPUT -o "$USB_INTERFACE" -j MARK --set-mark 0x1

# Добавляем правило в основную цепочку если его нет
if ! sudo iptables -t mangle -C OUTPUT -j HONOR_MARK 2>/dev/null; then
    sudo iptables -t mangle -A OUTPUT -j HONOR_MARK
fi

# 6. Настраиваем NAT для исходящего трафика
echo "6. Configuring NAT..."
sudo iptables -t nat -A POSTROUTING -o "$USB_INTERFACE" -j MASQUERADE

echo "✅ iptables rules configured"

# 7. Применяем изменения
echo "7. Applying changes..."
sudo sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf >/dev/null

# Обновляем кеш маршрутизации
sudo ip route flush cache

# 8. Тестируем соединение через HONOR
echo "8. Testing connection through HONOR..."
echo "Testing external IP via USB interface..."
EXTERNAL_IP=$(curl --interface "$USB_INTERFACE" -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null || echo "Failed")
echo "External IP via HONOR: $EXTERNAL_IP"

# 9. Тестируем маркировку трафика
echo "9. Testing traffic marking..."
# Отправляем тестовый запрос с маркировкой
sudo iptables -t mangle -A OUTPUT -p tcp --dport 80 -d httpbin.org -j MARK --set-mark 0x1
MARKED_IP=$(curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null || echo "Failed")
echo "Request with marking: $MARKED_IP"

# Удаляем тестовое правило
sudo iptables -t mangle -D OUTPUT -p tcp --dport 80 -d httpbin.org -j MARK --set-mark 0x1 2>/dev/null || true

# 10. Выводим информацию о конфигурации
echo ""
echo "============================================"
echo "HONOR Routing Configuration Complete!"
echo "============================================"
echo "USB Interface: $USB_INTERFACE"
echo "USB IP: $USB_IP"
echo "Gateway: $HONOR_GATEWAY"
echo "Routing Table: $HONOR_TABLE (ID: $HONOR_TABLE_ID)"
echo "Proxy Port: $PROXY_PORT"
echo ""
echo "Routing rules:"
ip rule show | grep -E "($HONOR_TABLE|0x1)"
echo ""
echo "HONOR routing table:"
ip route show table "$HONOR_TABLE"
echo ""
echo "Active iptables mangle rules:"
sudo iptables -t mangle -L OUTPUT -n | grep -E "(MARK|$USB_INTERFACE)"

# 11. Создаем скрипт для перезапуска маршрутизации
echo ""
echo "Creating restart script..."
cat > restart_honor_routing.sh << EOF
#!/bin/bash
# Перезапуск маршрутизации HONOR

echo "Restarting HONOR routing..."

# Очистка старых правил
sudo ip rule del from $USB_IP table $HONOR_TABLE 2>/dev/null || true
sudo ip rule del fwmark 0x1 table $HONOR_TABLE 2>/dev/null || true
sudo ip route flush table $HONOR_TABLE 2>/dev/null || true

# Восстановление маршрутов
sudo ip route add default via $HONOR_GATEWAY dev $USB_INTERFACE table $HONOR_TABLE
sudo ip route add $USB_IP/24 dev $USB_INTERFACE scope link table $HONOR_TABLE

# Восстановление правил
sudo ip rule add from $USB_IP table $HONOR_TABLE
sudo ip rule add fwmark 0x1 table $HONOR_TABLE

# Обновление кеша
sudo ip route flush cache

echo "HONOR routing restarted!"
EOF

chmod +x restart_honor_routing.sh

echo "============================================"
echo "Next steps:"
echo "1. Start your proxy service on port $PROXY_PORT"
echo "2. Test proxy with: curl -x http://192.168.1.50:$PROXY_PORT http://httpbin.org/ip"
echo "3. Check that traffic goes through HONOR mobile IP"
echo "4. Use ./restart_honor_routing.sh if routing breaks"
echo ""
echo "For automatic startup, add to /etc/rc.local:"
echo "  $(pwd)/restart_honor_routing.sh"

