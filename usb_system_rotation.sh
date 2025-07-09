#!/bin/bash

# Программная ротация IP через USB/системный уровень
INTERFACE="enx0c5b8f279a64"
DEVICE_ID="12d1:1f01"  # Huawei E3372h

echo "🔌 Программная ротация IP через USB/системный уровень"
echo "===================================================="

# Метод 1: Программное отключение/подключение USB устройства
echo ""
echo "1. Метод: Программное отключение USB устройства"
echo "=============================================="

# Находим USB устройство
USB_DEVICE=$(lsusb | grep "$DEVICE_ID" | head -1)
if [ -n "$USB_DEVICE" ]; then
    BUS=$(echo "$USB_DEVICE" | awk '{print $2}')
    DEV=$(echo "$USB_DEVICE" | awk '{print $4}' | tr -d ':')

    echo "📋 Найден USB модем: Bus $BUS Device $DEV"

    # Попытка отключения через authorized
    echo "🔧 Отключение USB устройства..."
    USB_PATH="/sys/bus/usb/devices/$BUS-*"
    for path in $USB_PATH; do
        if [ -d "$path" ]; then
            echo "  Проверка: $path"
            if [ -f "$path/authorized" ]; then
                echo "0" | sudo tee "$path/authorized" > /dev/null
                echo "  ✅ Отключено: $path"
            fi
        fi
    done

    sleep 5

    # Включение обратно
    echo "🔧 Включение USB устройства..."
    for path in $USB_PATH; do
        if [ -d "$path" ]; then
            if [ -f "$path/authorized" ]; then
                echo "1" | sudo tee "$path/authorized" > /dev/null
                echo "  ✅ Включено: $path"
            fi
        fi
    done

    sleep 10

    # Проверка результата
    echo "📋 Проверка после USB переподключения:"
    if ip addr show "$INTERFACE" | grep -q "inet "; then
        NEW_IP=$(curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"')
        echo "  IP после USB reset: $NEW_IP"
    else
        echo "  ❌ Интерфейс не активен"
    fi
fi

# Метод 2: Программное отключение/подключение сетевого интерфейса
echo ""
echo "2. Метод: Программное управление сетевым интерфейсом"
echo "=================================================="

echo "🔧 Отключение интерфейса $INTERFACE..."
sudo ip link set "$INTERFACE" down
sleep 3

echo "🔧 Сброс настроек интерфейса..."
sudo ip addr flush dev "$INTERFACE"
sleep 2

echo "🔧 Включение интерфейса..."
sudo ip link set "$INTERFACE" up
sleep 5

echo "🔧 Запуск DHCP клиента..."
sudo dhclient -r "$INTERFACE" 2>/dev/null
sleep 2
sudo dhclient "$INTERFACE"
sleep 10

echo "📋 Проверка после интерфейс reset:"
if ip addr show "$INTERFACE" | grep -q "inet "; then
    NEW_IP=$(curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"')
    echo "  IP после interface reset: $NEW_IP"
else
    echo "  ❌ Интерфейс не получил IP"
fi

# Метод 3: Перезагрузка USB драйвера
echo ""
echo "3. Метод: Перезагрузка USB драйвера"
echo "=================================="

echo "🔧 Выгрузка USB драйвера..."
sudo modprobe -r cdc_ether
sleep 2
sudo modprobe -r usbnet
sleep 2

echo "🔧 Загрузка USB драйвера..."
sudo modprobe usbnet
sleep 2
sudo modprobe cdc_ether
sleep 10

echo "📋 Проверка после driver reload:"
if ip addr show "$INTERFACE" | grep -q "inet "; then
    NEW_IP=$(curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"')
    echo "  IP после driver reload: $NEW_IP"
else
    echo "  ❌ Интерфейс не активен после перезагрузки драйвера"
fi

# Метод 4: usb_modeswitch reset
echo ""
echo "4. Метод: usb_modeswitch reset"
echo "============================="

echo "🔧 Reset через usb_modeswitch..."
sudo usb_modeswitch -v 12d1 -p 1f01 -R
sleep 15

echo "📋 Проверка после modeswitch reset:"
if ip addr show "$INTERFACE" | grep -q "inet "; then
    NEW_IP=$(curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"')
    echo "  IP после modeswitch reset: $NEW_IP"
else
    echo "  ❌ Интерфейс не активен после modeswitch"
fi

echo ""
echo "📊 Резюме методов USB/системного уровня:"
echo "========================================"
echo "1. USB authorized reset - мягкое отключение"
echo "2. Network interface reset - сброс сетевых настроек"
echo "3. Driver reload - перезагрузка драйвера"
echo "4. usb_modeswitch reset - сброс режима модема"

