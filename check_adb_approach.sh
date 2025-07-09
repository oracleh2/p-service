#!/bin/bash

# Проверка ADB подхода к модему
MODEM_IP="192.168.108.1"
ADB_PORT="5555"

echo "🔍 Проверка ADB подхода к модему"
echo "================================="

echo ""
echo "1. Проверка доступности ADB портов"
echo "=================================="

# Проверяем стандартные ADB порты
ADB_PORTS=(5555 5037 5038 5039 22 23)

for port in "${ADB_PORTS[@]}"; do
    echo -n "Порт $port: "
    if timeout 3 nc -z "$MODEM_IP" $port 2>/dev/null; then
        echo "✅ ОТКРЫТ"

        # Если порт 5555 открыт, пробуем ADB
        if [ "$port" = "5555" ]; then
            echo "  🔧 Пробуем ADB подключение..."

            # Добавляем устройство в ADB
            adb connect "$MODEM_IP:$port" 2>/dev/null
            sleep 2

            # Проверяем список устройств
            if adb devices | grep -q "$MODEM_IP:$port"; then
                echo "  ✅ ADB подключение успешно!"
                ADB_CONNECTED=true
                ADB_DEVICE="$MODEM_IP:$port"
            else
                echo "  ❌ ADB подключение не удалось"
            fi
        fi
    else
        echo "❌ ЗАКРЫТ"
    fi
done

echo ""
echo "2. Тестирование ADB команд"
echo "=========================="

if [ "$ADB_CONNECTED" = true ]; then
    echo "📱 Тестирование ADB команд на $ADB_DEVICE"

    # Проверка shell доступа
    echo "🔧 Проверка shell доступа:"
    adb -s "$ADB_DEVICE" shell "echo 'ADB shell works'" 2>/dev/null

    # Проверка системных свойств
    echo ""
    echo "🔧 Системные свойства (сеть):"
    adb -s "$ADB_DEVICE" shell "getprop | grep -E '(net|radio|ril|mobile|data)'" 2>/dev/null | head -10

    # Проверка интерфейсов
    echo ""
    echo "🔧 Сетевые интерфейсы:"
    adb -s "$ADB_DEVICE" shell "netcfg" 2>/dev/null || adb -s "$ADB_DEVICE" shell "ifconfig" 2>/dev/null

    # Проверка доступных команд
    echo ""
    echo "🔧 Доступные команды управления данными:"
    adb -s "$ADB_DEVICE" shell "svc --help" 2>/dev/null
    adb -s "$ADB_DEVICE" shell "svc data --help" 2>/dev/null

    echo ""
    echo "3. Тестирование управления мобильными данными"
    echo "============================================"

    # Проверяем статус данных
    echo "📋 Текущий статус данных:"
    adb -s "$ADB_DEVICE" shell "svc data status" 2>/dev/null

    # Пробуем отключить данные
    echo ""
    echo "📋 Отключение мобильных данных..."
    adb -s "$ADB_DEVICE" shell "svc data disable" 2>/dev/null
    sleep 5

    # Проверяем статус
    echo "📋 Статус после отключения:"
    adb -s "$ADB_DEVICE" shell "svc data status" 2>/dev/null

    # Включаем данные
    echo ""
    echo "📋 Включение мобильных данных..."
    adb -s "$ADB_DEVICE" shell "svc data enable" 2>/dev/null
    sleep 10

    # Проверяем статус
    echo "📋 Статус после включения:"
    adb -s "$ADB_DEVICE" shell "svc data status" 2>/dev/null

    echo ""
    echo "4. Проверка результата"
    echo "====================="

    # Проверяем интерфейсы после операции
    echo "📋 Интерфейсы после операции:"
    adb -s "$ADB_DEVICE" shell "ifconfig" 2>/dev/null

    # Отключаемся от ADB
    adb disconnect "$ADB_DEVICE" 2>/dev/null

else
    echo "❌ ADB недоступен, пробуем альтернативные методы"

    echo ""
    echo "3. Альтернативный подход - через Telnet"
    echo "======================================="

    # Проверяем, есть ли adb команда в самом модеме
    echo "🔧 Проверка наличия ADB в модеме через Telnet:"

    {
        sleep 1
        echo "find /system -name adb"
        sleep 3
        echo "which adb"
        sleep 2
        echo "exit"
    } | timeout 15 telnet "$MODEM_IP" 2>/dev/null | grep -v "Trying\|Connected\|Escape\|Connection closed"

fi

echo ""
echo "4. Проверка Android команд через Telnet"
echo "======================================="

# Функция для выполнения команд через telnet
execute_telnet_command() {
    local command="$1"
    echo "▶️ $command"

    {
        sleep 1
        echo "$command"
        sleep 3
        echo "exit"
    } | timeout 15 telnet "$MODEM_IP" 2>/dev/null | grep -v "Trying\|Connected\|Escape\|Connection closed"
}

# Пробуем Android команды напрямую через Telnet
echo "🔧 Проверка Android команд в модеме:"

# Проверяем доступность svc команд
execute_telnet_command "find /system -name svc"

# Проверяем системные свойства
execute_telnet_command "getprop ro.product.model"
execute_telnet_command "getprop ro.build.version.release"

# Проверяем настройки данных
execute_telnet_command "getprop | grep mobile"

echo ""
echo "📋 РЕЗЮМЕ:"
echo "=========="
if [ "$ADB_CONNECTED" = true ]; then
    echo "✅ ADB подключение работает!"
    echo "🔧 Можно использовать ADB команды для управления данными"
    echo "📋 Рекомендуемые команды:"
    echo "   - adb shell svc data disable"
    echo "   - adb shell svc data enable"
else
    echo "❌ ADB недоступен"
    echo "🔧 Нужно использовать альтернативные методы"
    echo "📋 Варианты:"
    echo "   - Telnet с Android командами"
    echo "   - Прямое управление через AT команды"
    echo "   - Веб-интерфейс HiLink API"
fi
