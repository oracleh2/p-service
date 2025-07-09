#!/bin/bash

# Тестирование прямых команд через ADB
MODEM_IP="192.168.108.1"
INTERFACE="enx0c5b8f279a64"

echo "🔍 Тестирование прямых команд через ADB"
echo "======================================="

# Подключаемся к модему
echo "📱 Подключение к модему..."
adb connect "$MODEM_IP:5555" >/dev/null 2>&1

# Проверяем подключение
if ! adb devices | grep -q "$MODEM_IP:5555"; then
    echo "❌ ADB подключение не удалось"
    exit 1
fi

echo "✅ ADB подключение установлено"

# Получаем текущий внешний IP
get_external_ip() {
    curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"'
}

echo ""
echo "1. Получение исходного IP"
echo "========================"
ORIGINAL_IP=$(get_external_ip)
echo "📋 Исходный внешний IP: $ORIGINAL_IP"

echo ""
echo "2. Тестирование AT команд через ADB"
echo "==================================="

# Функция для выполнения AT команд через ADB
adb_at_command() {
    local at_cmd="$1"
    echo "🔧 Выполнение: $at_cmd"
    adb shell "echo '$at_cmd' | atc" 2>/dev/null
}

echo "📋 Проверка радио модуля:"
adb_at_command "AT+CFUN?"

echo "📋 Проверка сети:"
adb_at_command "AT+COPS?"

echo "📋 Проверка PDP контекста:"
adb_at_command "AT+CGACT?"

echo ""
echo "3. Тестирование управления интерфейсами через ADB"
echo "================================================"

echo "📋 Текущий статус WAN интерфейса:"
adb shell "ifconfig wan0"

echo ""
echo "🔄 Попытка 1: Перезапуск WAN интерфейса через ADB"
echo "=================================================="

echo "🔧 Отключение wan0..."
adb shell "ifconfig wan0 down"
sleep 3

echo "🔧 Включение wan0..."
adb shell "ifconfig wan0 up"
sleep 10

echo "📋 Статус после перезапуска:"
adb shell "ifconfig wan0"

# Проверяем изменение IP
echo ""
echo "📋 Проверка IP после перезапуска wan0:"
NEW_IP_1=$(get_external_ip)
echo "IP после перезапуска wan0: $NEW_IP_1"

echo ""
echo "🔄 Попытка 2: AT команды через ADB"
echo "=================================="

echo "🔧 Мягкая перезагрузка радио..."
adb_at_command "AT+CFUN=0"
sleep 8
adb_at_command "AT+CFUN=1"
sleep 20

echo "📋 Проверка IP после AT команд:"
NEW_IP_2=$(get_external_ip)
echo "IP после AT команд: $NEW_IP_2"

echo ""
echo "🔄 Попытка 3: Управление PDP через ADB"
echo "======================================"

echo "🔧 Деактивация PDP..."
adb_at_command "AT+CGACT=0,1"
sleep 5

echo "🔧 Активация PDP..."
adb_at_command "AT+CGACT=1,1"
sleep 15

echo "📋 Проверка IP после PDP операций:"
NEW_IP_3=$(get_external_ip)
echo "IP после PDP операций: $NEW_IP_3"

echo ""
echo "🔄 Попытка 4: Комбинированный подход"
echo "===================================="

echo "🔧 Комбинированная ротация:"
echo "  1. Отключение wan0"
adb shell "ifconfig wan0 down"
sleep 3

echo "  2. Мягкая перезагрузка радио"
adb_at_command "AT+CFUN=0"
sleep 5
adb_at_command "AT+CFUN=1"
sleep 8

echo "  3. Включение wan0"
adb shell "ifconfig wan0 up"
sleep 15

echo "📋 Проверка IP после комбинированной ротации:"
NEW_IP_4=$(get_external_ip)
echo "IP после комбинированной ротации: $NEW_IP_4"

echo ""
echo "4. Финальная проверка состояния"
echo "==============================="

echo "📋 Финальное состояние сети:"
adb_at_command "AT+CREG?"
adb_at_command "AT+COPS?"
adb shell "ifconfig wan0"

# Отключаемся от ADB
adb disconnect "$MODEM_IP:5555" >/dev/null 2>&1

echo ""
echo "📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:"
echo "=========================="
echo "Исходный IP:                    $ORIGINAL_IP"
echo "После перезапуска wan0:         $NEW_IP_1"
echo "После AT команд:                $NEW_IP_2"
echo "После PDP операций:             $NEW_IP_3"
echo "После комбинированной ротации:  $NEW_IP_4"

echo ""
echo "🎯 АНАЛИЗ ЭФФЕКТИВНОСТИ:"
echo "======================="

# Подсчитываем успешные изменения IP
success_count=0
methods=("wan0_restart" "at_commands" "pdp_operations" "combined")
ips=("$NEW_IP_1" "$NEW_IP_2" "$NEW_IP_3" "$NEW_IP_4")

for i in {0..3}; do
    if [ "${ips[$i]}" != "$ORIGINAL_IP" ] && [ -n "${ips[$i]}" ]; then
        echo "✅ ${methods[$i]}: IP изменился ($ORIGINAL_IP → ${ips[$i]})"
        ((success_count++))
    else
        echo "❌ ${methods[$i]}: IP не изменился"
    fi
done

echo ""
echo "📋 РЕКОМЕНДАЦИИ:"
echo "==============="

if [ $success_count -gt 0 ]; then
    echo "🎉 Найдено $success_count рабочих методов ротации IP через ADB!"
    echo ""
    echo "🔧 Рекомендуемая последовательность для Python кода:"

    # Определяем лучший метод
    if [ "$NEW_IP_4" != "$ORIGINAL_IP" ] && [ -n "$NEW_IP_4" ]; then
        echo "1. Комбинированный подход (наиболее эффективен)"
        echo "   - ifconfig wan0 down"
        echo "   - AT+CFUN=0 → AT+CFUN=1"
        echo "   - ifconfig wan0 up"
    elif [ "$NEW_IP_2" != "$ORIGINAL_IP" ] && [ -n "$NEW_IP_2" ]; then
        echo "1. AT команды (эффективно)"
        echo "   - AT+CFUN=0 → AT+CFUN=1"
    elif [ "$NEW_IP_1" != "$ORIGINAL_IP" ] && [ -n "$NEW_IP_1" ]; then
        echo "1. Перезапуск wan0 (простой метод)"
        echo "   - ifconfig wan0 down → ifconfig wan0 up"
    fi

    echo ""
    echo "💻 Готовый код для интеграции:"
    echo "adb connect 192.168.108.1:5555"
    echo "adb shell 'ifconfig wan0 down'"
    echo "adb shell 'echo AT+CFUN=0 | atc'"
    echo "sleep 8"
    echo "adb shell 'echo AT+CFUN=1 | atc'"
    echo "sleep 8"
    echo "adb shell 'ifconfig wan0 up'"
    echo "sleep 15"
    echo "adb disconnect 192.168.108.1:5555"

else
    echo "⚠️ Ни один метод не показал стабильного изменения IP"
    echo "🔧 Возможные причины:"
    echo "   - Оператор не меняет IP при переподключении"
    echo "   - Нужно больше времени между операциями"
    echo "   - Требуется другой подход"
fi
