#!/bin/bash

# Исследование доступных команд в Android системе модема
MODEM_IP="192.168.108.1"

echo "🔍 Исследование команд в Android системе модема"
echo "=============================================="

# Функция для выполнения команд через telnet
execute_telnet_command() {
    local command="$1"
    echo "Выполнение: $command"

    {
        sleep 1
        echo "$command"
        sleep 3
        echo "exit"
    } | timeout 15 telnet "$MODEM_IP" 2>/dev/null | grep -v "Trying\|Connected\|Escape\|Connection closed"
}

echo "1. Исследование доступных команд..."
echo "======================================"

# Проверяем что есть в /bin, /sbin, /system/bin
echo "📂 Содержимое /bin:"
execute_telnet_command "ls -la /bin"

echo ""
echo "📂 Содержимое /sbin:"
execute_telnet_command "ls -la /sbin"

echo ""
echo "📂 Содержимое /system/bin:"
execute_telnet_command "ls -la /system/bin | head -20"

echo ""
echo "📂 Содержимое /system/xbin:"
execute_telnet_command "ls -la /system/xbin"

echo ""
echo "2. Поиск сетевых команд..."
echo "=========================="

# Ищем сетевые команды
echo "🔍 Поиск ifconfig:"
execute_telnet_command "find /system -name \"*ifconfig*\" 2>/dev/null"

echo ""
echo "🔍 Поиск ip:"
execute_telnet_command "find /system -name \"ip\" 2>/dev/null"

echo ""
echo "🔍 Поиск netcfg:"
execute_telnet_command "find /system -name \"*netcfg*\" 2>/dev/null"

echo ""
echo "🔍 Поиск iptables:"
execute_telnet_command "find /system -name \"*iptables*\" 2>/dev/null"

echo ""
echo "3. Проверка доступных сетевых команд..."
echo "======================================="

# Проверяем какие команды работают
commands=("ifconfig" "netcfg" "ip" "iptables" "route" "ping")

for cmd in "${commands[@]}"; do
    echo "🔧 Тестирование $cmd:"
    execute_telnet_command "$cmd --help 2>/dev/null || $cmd 2>/dev/null || echo 'Команда не найдена'"
    echo ""
done

echo ""
echo "4. Поиск Android-специфичных команд..."
echo "======================================"

# Android специфичные команды
android_commands=("am" "pm" "svc" "dumpsys" "getprop" "setprop")

for cmd in "${android_commands[@]}"; do
    echo "📱 Тестирование $cmd:"
    execute_telnet_command "$cmd --help 2>/dev/null || $cmd 2>/dev/null || echo 'Команда не найдена'"
    echo ""
done

echo ""
echo "5. Исследование системных свойств..."
echo "==================================="

echo "🔍 Получение системных свойств:"
execute_telnet_command "getprop | grep -E '(net|radio|ril|mobile|data)' | head -20"

echo ""
echo "6. Поиск AT команд и модемных утилит..."
echo "======================================="

# Поиск AT команд
echo "🔍 Поиск AT команд:"
execute_telnet_command "find /system -name \"*at*\" 2>/dev/null | head -10"

echo ""
echo "🔍 Поиск модемных утилит:"
execute_telnet_command "find /system -name \"*modem*\" 2>/dev/null | head -10"

echo ""
echo "🔍 Поиск RIL (Radio Interface Layer):"
execute_telnet_command "find /system -name \"*ril*\" 2>/dev/null | head -10"

echo ""
echo "7. Проверка сетевых интерфейсов..."
echo "=================================="

echo "🌐 Проверка /proc/net/dev:"
execute_telnet_command "cat /proc/net/dev"

echo ""
echo "🌐 Проверка /sys/class/net:"
execute_telnet_command "ls -la /sys/class/net/"

echo ""
echo "8. Поиск скриптов управления сетью..."
echo "===================================="

echo "🔍 Поиск init скриптов:"
execute_telnet_command "find /system -name \"*init*\" -type f 2>/dev/null | head -10"

echo ""
echo "🔍 Поиск сетевых скриптов:"
execute_telnet_command "find /system -name \"*network*\" -type f 2>/dev/null | head -10"

echo ""
echo "9. Проверка процессов..."
echo "======================="

echo "🔍 Активные процессы:"
execute_telnet_command "ps | grep -E '(net|radio|ril|dhcp|ppp)'"

echo ""
echo "📋 РЕЗЮМЕ ИССЛЕДОВАНИЯ:"
echo "======================="
echo "Модем работает на Android системе с ограниченным набором команд."
echo "Нужно найти Android-специфичные команды для управления сетью."
echo "Возможные подходы:"
echo "1. Использовать 'svc' команды для управления радио"
echo "2. Найти AT команды для прямого управления модемом"
echo "3. Использовать системные свойства (getprop/setprop)"
echo "4. Поиск специфичных для данной прошивки команд"

