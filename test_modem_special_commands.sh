#!/bin/bash

# Тестирование специальных команд модема
MODEM_IP="192.168.108.1"

echo "🔍 Тестирование специальных команд модема"
echo "=========================================="

# Функция для выполнения команд через telnet
execute_telnet_command() {
    local command="$1"
    echo "▶️ Выполнение: $command"

    {
        sleep 1
        echo "$command"
        sleep 5
        echo "exit"
    } | timeout 15 telnet "$MODEM_IP" 2>/dev/null | grep -v "Trying\|Connected\|Escape\|Connection closed"
}

echo ""
echo "1. Тестирование AT команд через /sbin/atc"
echo "========================================="

# Проверяем atc скрипт
echo "📋 Справка по atc:"
execute_telnet_command "atc --help"

echo ""
echo "📋 Информация о модеме:"
execute_telnet_command "atc AT+CGMI"  # Производитель
execute_telnet_command "atc AT+CGMM"  # Модель
execute_telnet_command "atc AT+CGMR"  # Версия прошивки

echo ""
echo "📋 Информация о сети:"
execute_telnet_command "atc AT+COPS?"  # Оператор
execute_telnet_command "atc AT+CREG?"  # Регистрация в сети
execute_telnet_command "atc AT+CGDCONT?"  # Настройки APN

echo ""
echo "2. Тестирование управления соединением"
echo "======================================"

echo "📋 Статус соединения:"
execute_telnet_command "atc AT+CGACT?"  # Статус PDP контекста

echo ""
echo "📋 Попытка отключения соединения:"
execute_telnet_command "atc AT+CGACT=0,1"  # Отключаем PDP контекст

echo ""
echo "⏳ Ожидание 10 секунд..."
sleep 10

echo ""
echo "📋 Попытка включения соединения:"
execute_telnet_command "atc AT+CGACT=1,1"  # Включаем PDP контекст

echo ""
echo "⏳ Ожидание 15 секунд..."
sleep 15

echo ""
echo "📋 Проверка нового статуса:"
execute_telnet_command "atc AT+CGACT?"

echo ""
echo "3. Альтернативные методы управления"
echo "==================================="

echo "📋 Управление радио модулем:"
execute_telnet_command "atc AT+CFUN?"  # Текущий режим функциональности

echo ""
echo "📋 Попытка перезапуска радио:"
execute_telnet_command "atc AT+CFUN=0"  # Отключаем радио
sleep 5
execute_telnet_command "atc AT+CFUN=1"  # Включаем радио

echo ""
echo "4. Проверка других специальных команд"
echo "====================================="

echo "📋 Тестирование unlock:"
execute_telnet_command "unlock --help"

echo ""
echo "📋 Тестирование hspa_locker:"
execute_telnet_command "hspa_locker --help"

echo ""
echo "5. Прямое управление интерфейсом wan0"
echo "====================================="

echo "📋 Текущий статус wan0:"
execute_telnet_command "ifconfig wan0"

echo ""
echo "📋 Попытка перезапуска wan0:"
execute_telnet_command "ifconfig wan0 down"
sleep 5
execute_telnet_command "ifconfig wan0 up"

echo ""
echo "⏳ Ожидание восстановления..."
sleep 15

echo ""
echo "📋 Новый статус wan0:"
execute_telnet_command "ifconfig wan0"

echo ""
echo "6. Проверка изменения внешнего IP"
echo "================================="

echo "📋 Получение внешнего IP через интерфейс:"
INTERFACE="enx0c5b8f279a64"
NEW_IP=$(curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"')
echo "Внешний IP: $NEW_IP"

echo ""
echo "7. Проверка маршрутов"
echo "===================="

echo "📋 Таблица маршрутизации:"
execute_telnet_command "route -n"

echo ""
echo "📋 Резюме тестирования:"
echo "======================"
echo "Проверили специальные команды модема:"
echo "1. atc - для AT команд"
echo "2. unlock - для разблокировки"
echo "3. hspa_locker - для управления технологией"
echo "4. ifconfig - для управления интерфейсами"
echo ""
echo "Наиболее перспективные методы:"
echo "- AT+CGACT для управления PDP контекстом"
echo "- AT+CFUN для управления радио модулем"
echo "- ifconfig wan0 для управления интерфейсом"

