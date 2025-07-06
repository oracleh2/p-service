#!/bin/bash
# Настройка маршрутизации через HONOR телефон

echo "🔧 Configuring routing through HONOR phone..."

# 1. Включаем USB tethering на HONOR
echo "1. Enabling USB tethering on HONOR..."
adb -s AH3SCP4B11207250 shell svc usb setFunctions rndis

# Подождем немного
sleep 3

# 2. Проверяем появился ли новый интерфейс
echo "2. Checking for new network interface..."
NEW_INTERFACE=$(ip link show | grep -E "(usb|rndis|enp)" | grep -v "lo\|eth0\|wlan0" | head -1 | cut -d: -f2 | tr -d ' ')

if [ -n "$NEW_INTERFACE" ]; then
    echo "Found new interface: $NEW_INTERFACE"

    # 3. Настраиваем интерфейс
    echo "3. Configuring interface $NEW_INTERFACE..."
    sudo dhclient $NEW_INTERFACE

    # 4. Проверяем получили ли IP
    IP_ADDR=$(ip addr show $NEW_INTERFACE | grep "inet " | awk '{print $2}' | cut -d/ -f1)
    echo "Interface $NEW_INTERFACE IP: $IP_ADDR"

    # 5. Проверяем маршрут
    echo "5. Checking route through $NEW_INTERFACE..."
    GATEWAY=$(ip route show dev $NEW_INTERFACE | grep default | awk '{print $3}')
    echo "Gateway: $GATEWAY"

    # 6. Тестируем соединение через новый интерфейс
    if [ -n "$GATEWAY" ]; then
        echo "6. Testing connection through $NEW_INTERFACE..."
        curl --interface $NEW_INTERFACE -s http://httpbin.org/ip
    fi

else
    echo "No new network interface found. Trying to enable USB tethering manually:"
    echo "1. On HONOR phone: Settings → Mobile network → Personal hotspot → USB tethering"
    echo "2. Make sure USB debugging is enabled"
    echo "3. Check USB connection mode - should be 'File transfer' or 'MTP'"
fi

echo ""
echo "7. Current network configuration:"
echo "All interfaces:"
ip addr show | grep -E "(inet |^[0-9]+:)" | head -20
