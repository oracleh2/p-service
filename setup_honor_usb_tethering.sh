#!/bin/bash
# Настройка HONOR телефона как USB модема

set -e

HONOR_DEVICE_ID="AH3SCP4B11207250"
USB_INTERFACE="enx7a859934e22a"

echo "🔧 Setting up HONOR phone USB tethering..."

# 1. Проверяем подключение к HONOR через ADB
echo "1. Checking ADB connection to HONOR..."
if ! adb devices | grep -q "$HONOR_DEVICE_ID"; then
    echo "❌ HONOR device not found via ADB"
    echo "Please enable USB debugging on HONOR phone:"
    echo "  - Settings → About phone → Build number (tap 7 times)"
    echo "  - Settings → System → Developer options → USB debugging"
    exit 1
fi

echo "✅ HONOR device connected via ADB"

# 2. Включаем USB tethering на HONOR через настройки
echo "2. Enabling USB tethering on HONOR..."

# Проверяем текущий статус USB tethering
TETHER_STATUS=$(adb -s "$HONOR_DEVICE_ID" shell dumpsys connectivity | grep -i "tethering" | head -1)
echo "Current tethering status: $TETHER_STATUS"

# Включаем USB tethering через системные настройки
adb -s "$HONOR_DEVICE_ID" shell am start -a android.intent.action.MAIN -n com.android.settings/.TetherSettings

echo "Please manually enable USB tethering on HONOR phone:"
echo "  - In opened settings, enable 'USB tethering'"
echo "  - Wait for the interface to appear on server"

# Ждем появления USB интерфейса
echo "3. Waiting for USB interface to appear..."
for i in {1..10}; do
    if ip link show "$USB_INTERFACE" 2>/dev/null | grep -q "UP"; then
        echo "✅ USB interface $USB_INTERFACE is UP"
        break
    elif ip link show "$USB_INTERFACE" 2>/dev/null; then
        echo "📱 USB interface $USB_INTERFACE found but DOWN, bringing it UP..."
        sudo ip link set "$USB_INTERFACE" up
        break
    else
        echo "⏳ Waiting for USB interface... ($i/10)"
        sleep 2
    fi
done

# 4. Настраиваем USB интерфейс на сервере
if ip link show "$USB_INTERFACE" 2>/dev/null; then
    echo "4. Configuring USB interface $USB_INTERFACE..."

    # Поднимаем интерфейс
    sudo ip link set "$USB_INTERFACE" up

    # Пытаемся получить IP через DHCP
    echo "Getting IP address via DHCP..."
    if command -v dhclient &> /dev/null; then
        sudo dhclient "$USB_INTERFACE" 2>/dev/null || true
    elif command -v dhcpcd &> /dev/null; then
        sudo dhcpcd "$USB_INTERFACE" 2>/dev/null || true
    else
        echo "⚠️  No DHCP client found. You may need to install dhclient or dhcpcd"
        echo "For Ubuntu/Debian: sudo apt install isc-dhcp-client"
    fi

    # Проверяем получили ли IP
    sleep 3
    IP_ADDR=$(ip addr show "$USB_INTERFACE" | grep "inet " | awk '{print $2}' | cut -d/ -f1)

    if [ -n "$IP_ADDR" ]; then
        echo "✅ USB interface $USB_INTERFACE configured with IP: $IP_ADDR"

        # Проверяем маршрут
        GATEWAY=$(ip route show dev "$USB_INTERFACE" | grep default | awk '{print $3}')
        if [ -n "$GATEWAY" ]; then
            echo "✅ Default gateway via $USB_INTERFACE: $GATEWAY"
        else
            echo "⚠️  No default gateway found via $USB_INTERFACE"
            # Пытаемся добавить маршрут автоматически
            NETWORK=$(echo "$IP_ADDR" | cut -d. -f1-3).1
            echo "Trying to add default route via $NETWORK..."
            sudo ip route add default via "$NETWORK" dev "$USB_INTERFACE" metric 100 2>/dev/null || true
        fi
    else
        echo "⚠️  No IP address assigned to $USB_INTERFACE"
        echo "Trying manual configuration..."
        # Пробуем назначить IP вручную (обычный диапазон для USB tethering)
        sudo ip addr add 192.168.42.100/24 dev "$USB_INTERFACE" 2>/dev/null || true
        sudo ip route add default via 192.168.42.129 dev "$USB_INTERFACE" metric 100 2>/dev/null || true

        IP_ADDR=$(ip addr show "$USB_INTERFACE" | grep "inet " | awk '{print $2}' | cut -d/ -f1)
        if [ -n "$IP_ADDR" ]; then
            echo "✅ Manual IP configuration: $IP_ADDR"
        fi
    fi
else
    echo "❌ USB interface $USB_INTERFACE not found"
    echo "Available interfaces:"
    ip link show | grep -E "^[0-9]+:" | cut -d: -f2 | tr -d ' '
    exit 1
fi

# 5. Тестируем соединение через HONOR
echo "5. Testing internet connection through HONOR..."
if [ -n "$IP_ADDR" ]; then
    echo "Testing external IP through $USB_INTERFACE..."
    EXTERNAL_IP=$(curl --interface "$USB_INTERFACE" -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null || echo "Failed")
    echo "External IP via HONOR: $EXTERNAL_IP"

    if [ "$EXTERNAL_IP" != "Failed" ]; then
        echo "✅ Internet connection through HONOR is working!"
    else
        echo "❌ Internet connection through HONOR failed"
        echo "Checking route table..."
        ip route show dev "$USB_INTERFACE"
    fi
else
    echo "❌ Cannot test - no IP address on USB interface"
fi

# 6. Проверяем общую конфигурацию сети
echo ""
echo "6. Current network configuration:"
echo "============================================"
echo "All interfaces:"
ip addr show | grep -E "(inet |^[0-9]+:)" | head -20

echo ""
echo "Routing table:"
ip route show

echo ""
echo "============================================"
echo "Setup complete! Next steps:"
echo "1. Update your proxy service to use interface: $USB_INTERFACE"
echo "2. Configure IP rotation via ADB commands to HONOR"
echo "3. Test proxy routing through HONOR mobile IP"

# 7. Выводим полезную информацию для настройки прокси
echo ""
echo "For proxy configuration, use:"
echo "  Interface: $USB_INTERFACE"
echo "  Device ID: $HONOR_DEVICE_ID"
echo "  Rotation method: adb_data_toggle"

# 8. Дополнительная диагностика
echo ""
echo "8. Additional diagnostics:"
echo "HONOR mobile data status:"
adb -s "$HONOR_DEVICE_ID" shell settings get global mobile_data

echo ""
echo "HONOR network info:"
adb -s "$HONOR_DEVICE_ID" shell dumpsys connectivity | grep -A 5 -B 5 "Mobile"
