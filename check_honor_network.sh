#!/bin/bash
# Проверка сетевых настроек HONOR телефона

echo "🔍 Checking HONOR phone network configuration..."

# 1. Проверяем сетевые интерфейсы на телефоне
echo "1. Network interfaces on HONOR phone:"
adb -s AH3SCP4B11207250 shell ip addr show

echo ""
echo "2. Routing table on HONOR phone:"
adb -s AH3SCP4B11207250 shell ip route show

echo ""
echo "3. Check mobile data interface:"
adb -s AH3SCP4B11207250 shell ip route show | grep -E "(mobile|rmnet|ccmni)"

echo ""
echo "4. Check current external IP from HONOR perspective:"
adb -s AH3SCP4B11207250 shell curl -s http://httpbin.org/ip 2>/dev/null || echo "Could not get IP from HONOR"

echo ""
echo "5. Check if USB tethering is enabled:"
adb -s AH3SCP4B11207250 shell dumpsys connectivity | grep -i tether

echo ""
echo "6. Check available network interfaces on server:"
echo "Server network interfaces:"
ip addr show | grep -E "(inet |^[0-9]+:)"

echo ""
echo "7. Check server routing table:"
echo "Server routing table:"
ip route show

echo ""
echo "8. Check if HONOR created a new interface on server:"
ifconfig | grep -E "(usb|rndis|honor|android)" -A 3
