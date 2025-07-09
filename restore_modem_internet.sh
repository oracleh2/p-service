#!/bin/bash

# ЭКСТРЕННОЕ ВОССТАНОВЛЕНИЕ ИНТЕРНЕТА НА МОДЕМЕ
MODEM_IP="192.168.108.1"
INTERFACE="enx0c5b8f279a64"

echo "🚨 ЭКСТРЕННОЕ ВОССТАНОВЛЕНИЕ ИНТЕРНЕТА НА МОДЕМЕ"
echo "================================================"

# Функция для выполнения команд через telnet
execute_telnet_command() {
    local command="$1"
    local wait_time=${2:-5}

    echo "🔧 Выполняю: $command"
    {
        sleep 1
        echo "$command"
        sleep $wait_time
        echo "exit"
    } | timeout 20 telnet "$MODEM_IP" 2>/dev/null | grep -v "Trying\|Connected\|Escape\|Connection closed"
}

echo ""
echo "1. ВОССТАНОВЛЕНИЕ РАДИО МОДУЛЯ"
echo "=============================="

echo "🔄 Включаем радио модуль..."
execute_telnet_command "atc AT+CFUN=1" 10

echo ""
echo "2. ПРИНУДИТЕЛЬНАЯ РЕГИСТРАЦИЯ В СЕТИ"
echo "===================================="

echo "🔍 Поиск доступных сетей..."
execute_telnet_command "atc AT+COPS=0" 15

echo ""
echo "3. ВОССТАНОВЛЕНИЕ PDP КОНТЕКСТА"
echo "==============================="

echo "🔧 Настройка APN..."
execute_telnet_command "atc AT+CGDCONT=1,\"IP\",\"internet\"" 5

echo "🔄 Активация PDP контекста..."
execute_telnet_command "atc AT+CGACT=1,1" 10

echo ""
echo "4. ПРОВЕРКА СТАТУСА СЕТИ"
echo "======================="

echo "📡 Проверка регистрации в сети..."
execute_telnet_command "atc AT+CREG?" 3

echo "📡 Проверка типа сети..."
execute_telnet_command "atc AT+COPS?" 3

echo "📡 Проверка PDP контекста..."
execute_telnet_command "atc AT+CGACT?" 3

echo ""
echo "5. ВОССТАНОВЛЕНИЕ СЕТЕВЫХ ИНТЕРФЕЙСОВ"
echo "====================================="

echo "🔧 Проверка интерфейса wan0..."
execute_telnet_command "ifconfig wan0" 3

echo "🔧 Перезапуск wan0..."
execute_telnet_command "ifconfig wan0 down" 3
execute_telnet_command "ifconfig wan0 up" 5

echo ""
echo "6. ВОССТАНОВЛЕНИЕ МАРШРУТИЗАЦИИ"
echo "=============================="

echo "🛣️ Добавление маршрутов..."
# Пытаемся восстановить маршрут к шлюзу
execute_telnet_command "route add default gw 10.64.64.1 wan0" 3

echo "📋 Проверка маршрутов..."
execute_telnet_command "route -n" 3

echo ""
echo "7. ДОПОЛНИТЕЛЬНЫЕ ПОПЫТКИ ВОССТАНОВЛЕНИЯ"
echo "========================================"

echo "🔄 Альтернативная активация соединения..."
execute_telnet_command "atc AT+CGACT=0" 5
execute_telnet_command "atc AT+CGACT=1" 10

echo "🔄 Перезапуск DHCP клиента (если есть)..."
execute_telnet_command "killall dhcpc" 3
execute_telnet_command "dhcpc -i wan0" 5

echo ""
echo "8. ФИНАЛЬНАЯ ПРОВЕРКА"
echo "===================="

echo "📋 Финальная проверка интерфейсов..."
execute_telnet_command "ifconfig" 3

echo "📋 Финальная проверка маршрутов..."
execute_telnet_command "route -n" 3

echo "📋 Пинг Google DNS..."
execute_telnet_command "ping -c 3 8.8.8.8" 10

echo ""
echo "9. ПРОВЕРКА ИНТЕРНЕТА НА СИСТЕМЕ"
echo "==============================="

echo "🌐 Проверка интернета через интерфейс..."
sleep 10

# Проверяем интернет через интерфейс
echo "🔍 Тест 1: Пинг через интерфейс..."
if timeout 5 ping -I "$INTERFACE" -c 1 8.8.8.8 >/dev/null 2>&1; then
    echo "✅ Ping работает"
else
    echo "❌ Ping не работает"
fi

echo "🔍 Тест 2: HTTP запрос..."
EXTERNAL_IP=$(timeout 10 curl --interface "$INTERFACE" -s https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"')
if [ -n "$EXTERNAL_IP" ]; then
    echo "✅ HTTP работает. Внешний IP: $EXTERNAL_IP"
else
    echo "❌ HTTP не работает"
fi

echo ""
echo "10. РЕКОМЕНДАЦИИ ПО ВОССТАНОВЛЕНИЮ"
echo "=================================="

if [ -n "$EXTERNAL_IP" ]; then
    echo "🎉 УСПЕХ! Интернет восстановлен!"
    echo "📋 Внешний IP: $EXTERNAL_IP"
    echo "✅ Модем работает нормально"
else
    echo "⚠️ Интернет пока не восстановлен"
    echo ""
    echo "🔧 Попробуйте эти действия:"
    echo "1. Перезагрузите модем:"
    echo "   sudo usb_modeswitch -R -v 12d1 -p 1f01"
    echo ""
    echo "2. Или физически отключите/подключите модем"
    echo ""
    echo "3. Проверьте SIM карту и PIN код"
    echo ""
    echo "4. Запустите HiLink восстановление:"
    echo "   curl -X POST http://192.168.108.1/api/device/control -d '<?xml version=\"1.0\"?><request><Control>1</Control></request>'"
fi

echo ""
echo "11. ЗАЩИТА ОТ ПОВТОРНЫХ ПРОБЛЕМ"
echo "==============================="

echo "⚠️ ВАЖНО: AT+CFUN команды могут сбивать настройки сети"
echo "✅ Используйте более безопасные методы:"
echo "   - HiLink API для ротации IP"
echo "   - ADB команды (если доступны)"
echo "   - Управление через веб-интерфейс"
echo ""
echo "❌ ИЗБЕГАЙТЕ:"
echo "   - AT+CFUN=0/1 (сбрасывает сеть)"
echo "   - AT+CGACT без понимания последствий"
echo "   - Экспериментов с AT командами на продакшене"
