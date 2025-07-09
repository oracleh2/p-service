#!/bin/bash

# Улучшенный скрипт ротации IP через переключение в Storage Mode
# Поддерживает настройку таймаутов и лучше восстанавливает интерфейс

INTERFACE="enx0c5b8f279a64"
MODEM_IP="192.168.108.1"
DEVICE_ID="12d1:14dc"  # Huawei E3372 HiLink

# Таймауты по умолчанию (в секундах)
DEFAULT_STORAGE_TIMEOUT=15
DEFAULT_RESTORE_TIMEOUT=20
DEFAULT_INTERFACE_TIMEOUT=60
DEFAULT_DHCP_TIMEOUT=20

# Переменные для таймаутов
STORAGE_TIMEOUT=$DEFAULT_STORAGE_TIMEOUT
RESTORE_TIMEOUT=$DEFAULT_RESTORE_TIMEOUT
INTERFACE_TIMEOUT=$DEFAULT_INTERFACE_TIMEOUT
DHCP_TIMEOUT=$DEFAULT_DHCP_TIMEOUT

# Функция помощи
show_help() {
    echo "Использование: $0 [опции]"
    echo ""
    echo "Опции:"
    echo "  -s, --storage-timeout SEC     Таймаут ожидания в Storage Mode (по умолчанию: $DEFAULT_STORAGE_TIMEOUT)"
    echo "  -r, --restore-timeout SEC     Таймаут восстановления HiLink (по умолчанию: $DEFAULT_RESTORE_TIMEOUT)"
    echo "  -i, --interface-timeout SEC   Таймаут ожидания интерфейса (по умолчанию: $DEFAULT_INTERFACE_TIMEOUT)"
    echo "  -d, --dhcp-timeout SEC        Таймаут DHCP (по умолчанию: $DEFAULT_DHCP_TIMEOUT)"
    echo "  -h, --help                    Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0                            # Стандартные таймауты"
    echo "  $0 -s 10 -r 15               # Быстрая ротация"
    echo "  $0 -s 30 -r 45 -i 90         # Медленная но стабильная ротация"
    echo "  $0 --storage-timeout 5        # Только быстрое переключение в storage"
    echo ""
    echo "Рекомендуемые диапазоны:"
    echo "  Storage timeout:   5-30 секунд"
    echo "  Restore timeout:   10-60 секунд"
    echo "  Interface timeout: 30-120 секунд"
    echo "  DHCP timeout:      10-30 секунд"
}

# Обработка аргументов
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--storage-timeout)
            STORAGE_TIMEOUT="$2"
            shift 2
            ;;
        -r|--restore-timeout)
            RESTORE_TIMEOUT="$2"
            shift 2
            ;;
        -i|--interface-timeout)
            INTERFACE_TIMEOUT="$2"
            shift 2
            ;;
        -d|--dhcp-timeout)
            DHCP_TIMEOUT="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "❌ Неизвестный аргумент: $1"
            echo "Используйте -h для справки"
            exit 1
            ;;
    esac
done

# Проверка валидности таймаутов
validate_timeout() {
    local timeout="$1"
    local name="$2"

    if ! [[ "$timeout" =~ ^[0-9]+$ ]] || [ "$timeout" -lt 1 ] || [ "$timeout" -gt 300 ]; then
        echo "❌ Неверный таймаут для $name: $timeout (должен быть 1-300 секунд)"
        exit 1
    fi
}

validate_timeout "$STORAGE_TIMEOUT" "storage"
validate_timeout "$RESTORE_TIMEOUT" "restore"
validate_timeout "$INTERFACE_TIMEOUT" "interface"
validate_timeout "$DHCP_TIMEOUT" "dhcp"

echo "🔄 Улучшенная ротация IP через Storage Mode"
echo "==========================================="
echo "⏱️  Таймауты: Storage=${STORAGE_TIMEOUT}s, Restore=${RESTORE_TIMEOUT}s, Interface=${INTERFACE_TIMEOUT}s, DHCP=${DHCP_TIMEOUT}s"
echo ""

# Функция получения внешнего IP
get_external_ip() {
    local timeout="${1:-10}"
    local ip=$(timeout "$timeout" curl --interface "$INTERFACE" -s https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"' || echo "unknown")
    echo "$ip"
}

# Функция проверки доступности интерфейса
check_interface() {
    if ip link show "$INTERFACE" >/dev/null 2>&1; then
        if ip addr show "$INTERFACE" | grep -q "inet "; then
            return 0
        fi
    fi
    return 1
}

# Функция ожидания появления интерфейса
wait_for_interface() {
    local timeout="$1"
    local counter=0

    echo "⏳ Ожидание интерфейса $INTERFACE (таймаут: ${timeout}s)..."

    while [ $counter -lt $timeout ]; do
        if ip link show "$INTERFACE" >/dev/null 2>&1; then
            echo "✅ Интерфейс $INTERFACE появился через ${counter}s"
            return 0
        fi

        if [ $((counter % 10)) -eq 0 ] && [ $counter -gt 0 ]; then
            echo "  ⏳ Ожидание... (${counter}/${timeout}s)"
        fi

        sleep 1
        counter=$((counter + 1))
    done

    echo "❌ Интерфейс не появился в течение ${timeout}s"
    return 1
}

# Функция активации интерфейса через DHCP
activate_interface() {
    local timeout="$1"

    echo "🔧 Активация интерфейса $INTERFACE..."

    # Поднимаем интерфейс
    sudo ip link set "$INTERFACE" up 2>/dev/null || true
    sleep 2

    # Очищаем старые настройки
    sudo ip addr flush dev "$INTERFACE" 2>/dev/null || true
    sudo pkill -f "dhclient.*$INTERFACE" 2>/dev/null || true
    sleep 1

    # Получаем IP через DHCP
    echo "📡 Получение IP через DHCP (таймаут: ${timeout}s)..."
    timeout "$timeout" sudo dhclient "$INTERFACE" 2>/dev/null || true

    # Проверяем результат
    if check_interface; then
        local ip=$(ip addr show "$INTERFACE" | grep "inet " | awk '{print $2}' | head -1)
        echo "✅ IP получен: $ip"
        return 0
    else
        echo "❌ Не удалось получить IP"
        return 1
    fi
}

# Функция проверки режима модема
check_modem_mode() {
    local mode_info=$(lsusb -v -d "$DEVICE_ID" 2>/dev/null | grep -E "bInterfaceClass.*[0-9]" | head -1)

    if echo "$mode_info" | grep -q "8 Mass Storage"; then
        echo "storage"
    elif echo "$mode_info" | grep -q "2 Communications"; then
        echo "hilink"
    else
        echo "unknown"
    fi
}

# Получаем начальное состояние
echo "📊 Проверка начального состояния"
echo "================================"

if check_interface; then
    INITIAL_IP=$(get_external_ip 10)
    echo "✅ Интерфейс активен"
    echo "🌐 Начальный внешний IP: $INITIAL_IP"
else
    echo "❌ Интерфейс не активен"
    echo "🔧 Попытка активации..."
    if activate_interface "$DHCP_TIMEOUT"; then
        INITIAL_IP=$(get_external_ip 10)
        echo "🌐 Начальный внешний IP: $INITIAL_IP"
    else
        echo "❌ Не удалось активировать интерфейс"
        exit 1
    fi
fi

# Проверяем начальный режим
INITIAL_MODE=$(check_modem_mode)
echo "📱 Начальный режим модема: $INITIAL_MODE"

# Получаем информацию о USB устройстве
vendor=$(echo "$DEVICE_ID" | cut -d: -f1)
product=$(echo "$DEVICE_ID" | cut -d: -f2)

echo ""
echo "🔄 Начало ротации через Storage Mode"
echo "===================================="
echo "⏱️  Этап 1: Переключение в Storage Mode (${STORAGE_TIMEOUT}s)"

# Шаг 1: Переключение в Storage Mode
echo "🔧 Переключение в Storage Mode..."

# Используем рабочий метод из логов
sudo usb_modeswitch -v "$vendor" -p "$product" -M '55534243123456780000000000000a11062000000000000100000000000000' 2>/dev/null

echo "⏳ Ожидание переключения в Storage Mode (${STORAGE_TIMEOUT}s)..."
sleep "$STORAGE_TIMEOUT"

# Проверяем переключение
STORAGE_MODE=$(check_modem_mode)
echo "📋 Режим после переключения: $STORAGE_MODE"

if [ "$STORAGE_MODE" = "storage" ]; then
    echo "✅ Успешно переключен в Storage Mode"
elif [ "$STORAGE_MODE" = "hilink" ]; then
    echo "⚠️  Остался в HiLink Mode (возможно, быстрое переключение)"
else
    echo "❓ Неопределенный режим: $STORAGE_MODE"
fi

# Проверяем исчезновение интерфейса
if check_interface; then
    echo "⚠️  Интерфейс всё ещё доступен"
else
    echo "✅ Интерфейс исчез (модем в Storage Mode)"
fi

echo ""
echo "⏱️  Этап 2: Переключение обратно в HiLink Mode (${RESTORE_TIMEOUT}s)"

# Шаг 2: Переключение обратно в HiLink Mode
echo "🔧 Переключение обратно в HiLink Mode..."

# Используем команду -H для Huawei (из логов это сработало)
sudo usb_modeswitch -v "$vendor" -p "$product" -H 2>/dev/null || true
sleep 3

# Дополнительная команда -J для надежности
sudo usb_modeswitch -v "$vendor" -p "$product" -J 2>/dev/null || true
sleep 3

# Стандартное переключение без параметров
sudo usb_modeswitch -v "$vendor" -p "$product" 2>/dev/null || true

echo "⏳ Ожидание переключения обратно в HiLink Mode (${RESTORE_TIMEOUT}s)..."
sleep "$RESTORE_TIMEOUT"

# Проверяем переключение
HILINK_MODE=$(check_modem_mode)
echo "📋 Режим после восстановления: $HILINK_MODE"

if [ "$HILINK_MODE" = "hilink" ]; then
    echo "✅ Успешно переключен обратно в HiLink Mode"
elif [ "$HILINK_MODE" = "storage" ]; then
    echo "❌ Остался в Storage Mode"
else
    echo "❓ Неопределенный режим: $HILINK_MODE"
fi

echo ""
echo "⏱️  Этап 3: Восстановление интерфейса (${INTERFACE_TIMEOUT}s)"

# Шаг 3: Ожидание появления интерфейса
if wait_for_interface "$INTERFACE_TIMEOUT"; then
    echo "✅ Интерфейс появился"

    # Активируем интерфейс
    if activate_interface "$DHCP_TIMEOUT"; then
        echo "✅ Интерфейс успешно активирован"
    else
        echo "❌ Не удалось активировать интерфейс"
    fi
else
    echo "❌ Интерфейс не появился"

    # Дополнительная попытка принудительной активации
    echo "🔧 Попытка принудительной активации..."

    # Проверяем системные логи
    echo "📋 Последние системные события:"
    sudo dmesg | tail -5 | grep -i "usb\|cdc\|rndis\|hilink" || echo "  Нет релевантных событий"

    # Попытка переподключения USB
    echo "🔌 Попытка программного переподключения USB..."
    USB_DEVICE_PATH=$(find /sys/bus/usb/devices -name "*$vendor*" -type d | head -1)

    if [ -n "$USB_DEVICE_PATH" ] && [ -f "$USB_DEVICE_PATH/authorized" ] && [ -w "$USB_DEVICE_PATH/authorized" ]; then
        echo "  🔧 Отключение..."
        echo 0 | sudo tee "$USB_DEVICE_PATH/authorized" >/dev/null
        sleep 3
        echo "  🔧 Включение..."
        echo 1 | sudo tee "$USB_DEVICE_PATH/authorized" >/dev/null
        sleep 5

        # Повторная попытка ожидания интерфейса
        if wait_for_interface 30; then
            activate_interface "$DHCP_TIMEOUT"
        fi
    fi
fi

echo ""
echo "📊 Проверка результатов ротации"
echo "==============================="

# Финальная проверка
if check_interface; then
    echo "✅ Интерфейс $INTERFACE активен"

    # Получаем новый IP
    echo "🌐 Получение нового внешнего IP..."
    NEW_IP=$(get_external_ip 15)

    echo ""
    echo "📋 Результат ротации:"
    echo "  Начальный IP: $INITIAL_IP"
    echo "  Новый IP:     $NEW_IP"
    echo "  Начальный режим: $INITIAL_MODE"
    echo "  Финальный режим: $(check_modem_mode)"

    if [ "$INITIAL_IP" != "$NEW_IP" ] && [ "$NEW_IP" != "unknown" ] && [ -n "$NEW_IP" ]; then
        echo "  ✅ IP успешно изменился!"
        echo ""
        echo "🎉 Ротация через Storage Mode УСПЕШНА!"
        echo ""
        echo "📊 Статистика таймаутов:"
        echo "  Storage timeout: ${STORAGE_TIMEOUT}s ✅"
        echo "  Restore timeout: ${RESTORE_TIMEOUT}s ✅"
        echo "  Interface timeout: ${INTERFACE_TIMEOUT}s ✅"
        echo "  DHCP timeout: ${DHCP_TIMEOUT}s ✅"

        # Рекомендации по оптимизации
        echo ""
        echo "💡 Рекомендации по оптимизации:"
        if [ "$STORAGE_TIMEOUT" -gt 20 ]; then
            echo "  • Можно уменьшить storage timeout до 10-15s"
        fi
        if [ "$RESTORE_TIMEOUT" -gt 30 ]; then
            echo "  • Можно уменьшить restore timeout до 20-25s"
        fi
        if [ "$INTERFACE_TIMEOUT" -gt 40 ]; then
            echo "  • Можно уменьшить interface timeout до 30-40s"
        fi
        echo "  • Для быстрой ротации попробуйте: $0 -s 10 -r 15 -i 30"

        exit 0
    else
        echo "  ⚠️ IP не изменился или не удалось получить новый IP"
        echo ""
        echo "❌ Ротация через Storage Mode НЕ СРАБОТАЛА"

        # Диагностика
        echo ""
        echo "🔍 Диагностика:"
        echo "  • Интерфейс работает, но IP не изменился"
        echo "  • Возможно, оператор не выдал новый IP"
        echo "  • Попробуйте увеличить таймауты"
        echo "  • Или повторите ротацию через некоторое время"

        exit 1
    fi

else
    echo "❌ Интерфейс $INTERFACE не активен"
    echo "❌ Ротация не удалась - интерфейс недоступен"

    # Расширенная диагностика
    echo ""
    echo "🔍 Расширенная диагностика:"
    echo "================================"

    echo "📱 USB устройство:"
    lsusb | grep "$DEVICE_ID" || echo "  Устройство не найдено"

    echo ""
    echo "🔧 Режим устройства:"
    echo "  $(check_modem_mode)"

    echo ""
    echo "🌐 Сетевые интерфейсы:"
    ip link show | grep -E "enx" || echo "  USB интерфейсы не найдены"

    echo ""
    echo "📊 Системные логи (последние 5 строк):"
    sudo dmesg | tail -5 | grep -i "usb\|cdc\|rndis\|hilink" || echo "  Нет релевантных логов"

    echo ""
    echo "🔧 Рекомендации:"
    echo "  1. Увеличьте таймауты: $0 -s 30 -r 60 -i 120"
    echo "  2. Попробуйте физически переподключить модем"
    echo "  3. Перезагрузите систему"
    echo "  4. Проверьте ./setup_e3372.sh для восстановления"

    exit 1
fi
