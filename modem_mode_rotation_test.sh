#!/bin/bash

# Тест переключения режимов модема для ротации IP
INTERFACE="enx0c5b8f279a64"
MODEM_IP="192.168.108.1"
DEVICE_ID="12d1:14dc"  # Huawei E3372 HiLink

echo "🔄 Тест переключения режимов модема для ротации IP"
echo "=================================================="

# Функция получения внешнего IP
get_external_ip() {
    local ip=$(timeout 10 curl --interface "$INTERFACE" -s https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"' || echo "unknown")
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
    local timeout=60
    local counter=0

    echo "⏳ Ожидание появления интерфейса $INTERFACE..."

    while [ $counter -lt $timeout ]; do
        if check_interface; then
            echo "✅ Интерфейс $INTERFACE доступен"
            return 0
        fi

        echo "  Проверка ($((counter+1))/$timeout)..."
        sleep 1
        counter=$((counter + 1))
    done

    echo "❌ Интерфейс не появился в течение $timeout секунд"
    return 1
}

# Функция активации интерфейса
activate_interface() {
    echo "🔧 Активация интерфейса $INTERFACE..."

    # Поднимаем интерфейс
    sudo ip link set "$INTERFACE" up 2>/dev/null || true
    sleep 2

    # Очищаем старые настройки
    sudo ip addr flush dev "$INTERFACE" 2>/dev/null || true
    sudo pkill -f "dhclient.*$INTERFACE" 2>/dev/null || true

    # Получаем IP через DHCP
    echo "  📡 Получение IP через DHCP..."
    timeout 20 sudo dhclient "$INTERFACE" 2>/dev/null || true

    # Проверяем результат
    if check_interface; then
        local ip=$(ip addr show "$INTERFACE" | grep "inet " | awk '{print $2}' | head -1)
        echo "  ✅ IP получен: $ip"
        return 0
    else
        echo "  ❌ Не удалось получить IP"
        return 1
    fi
}

# Получаем начальный IP
echo ""
echo "📊 Проверка начального состояния"
echo "================================"

if check_interface; then
    INITIAL_IP=$(get_external_ip)
    echo "✅ Интерфейс активен"
    echo "🌐 Начальный внешний IP: $INITIAL_IP"
else
    echo "❌ Интерфейс не активен"
    echo "🔧 Попытка активации..."
    if activate_interface; then
        INITIAL_IP=$(get_external_ip)
        echo "🌐 Начальный внешний IP: $INITIAL_IP"
    else
        echo "❌ Не удалось активировать интерфейс"
        exit 1
    fi
fi

echo ""
echo "🔄 Метод 1: Переключение в Storage Mode и обратно"
echo "================================================"

# Получаем информацию о USB устройстве
vendor=$(echo "$DEVICE_ID" | cut -d: -f1)
product=$(echo "$DEVICE_ID" | cut -d: -f2)

echo "📱 Устройство: $vendor:$product"

# Проверяем текущий режим
echo "🔍 Проверка текущего режима..."
current_mode=$(lsusb -v -d "$DEVICE_ID" 2>/dev/null | grep -E "bInterfaceClass.*[0-9]" | head -1)
echo "  Текущий режим: $current_mode"

# Шаг 1: Переключение в Storage Mode
echo ""
echo "🔄 Шаг 1: Переключение в Storage Mode"
echo "===================================="

echo "🔧 Попытка переключения в Storage Mode..."

# Метод 1: Стандартный способ переключения в storage
if [ -f "/usr/share/usb_modeswitch/$DEVICE_ID" ]; then
    echo "  Используем конфигурацию из /usr/share/usb_modeswitch/$DEVICE_ID"
    sudo usb_modeswitch -v "$vendor" -p "$product" -c "/usr/share/usb_modeswitch/$DEVICE_ID" -R 2>/dev/null
else
    echo "  Используем стандартную команду для переключения в storage"
    # Команда для переключения в storage mode
    sudo usb_modeswitch -v "$vendor" -p "$product" -M '55534243123456780000000000000a11062000000000000100000000000000' -R 2>/dev/null
fi

echo "⏳ Ожидание переключения в storage mode (15 секунд)..."
sleep 15

# Проверяем, что устройство в storage mode
storage_check=$(lsusb -v -d "$DEVICE_ID" 2>/dev/null | grep "bInterfaceClass.*8 Mass Storage" || echo "")
if [ -n "$storage_check" ]; then
    echo "✅ Устройство переключилось в Storage Mode"
else
    echo "⚠️ Устройство может не быть в Storage Mode (или уже переключается)"
fi

# Проверяем, что интерфейс исчез
if ! check_interface; then
    echo "✅ Сетевой интерфейс исчез (модем в Storage Mode)"
else
    echo "⚠️ Сетевой интерфейс всё ещё доступен"
fi

echo ""
echo "🔄 Шаг 2: Переключение обратно в HiLink Mode"
echo "=========================================="

echo "🔧 Попытка переключения обратно в HiLink Mode..."

# Различные способы переключения обратно в HiLink
echo "  Способ 1: Стандартное переключение"
sudo usb_modeswitch -v "$vendor" -p "$product" -J 2>/dev/null || true
sleep 5

echo "  Способ 2: Альтернативная команда"
sudo usb_modeswitch -v "$vendor" -p "$product" -H 2>/dev/null || true
sleep 5

echo "  Способ 3: Переключение без -R флага"
sudo usb_modeswitch -v "$vendor" -p "$product" 2>/dev/null || true
sleep 5

echo "⏳ Ожидание переключения обратно в HiLink mode (20 секунд)..."
sleep 20

# Проверяем, что устройство переключилось обратно
hilink_check=$(lsusb -v -d "$DEVICE_ID" 2>/dev/null | grep "bInterfaceClass.*2 Communications" || echo "")
if [ -n "$hilink_check" ]; then
    echo "✅ Устройство переключилось обратно в HiLink Mode"
else
    echo "⚠️ Устройство может не быть в HiLink Mode"
fi

# Ожидаем появления интерфейса
if wait_for_interface; then
    if activate_interface; then
        echo "✅ Интерфейс успешно активирован после переключения"
    else
        echo "❌ Не удалось активировать интерфейс после переключения"
    fi
else
    echo "❌ Интерфейс не появился после переключения"
fi

echo ""
echo "🔄 Метод 2: Программное переподключение USB"
echo "========================================="

echo "🔧 Поиск USB устройства в системе..."
USB_DEVICE_PATH=$(find /sys/bus/usb/devices -name "*$vendor*" -type d | head -1)

if [ -n "$USB_DEVICE_PATH" ]; then
    echo "📱 USB устройство найдено: $USB_DEVICE_PATH"

    # Проверяем authorized файл
    if [ -f "$USB_DEVICE_PATH/authorized" ] && [ -w "$USB_DEVICE_PATH/authorized" ]; then
        echo "🔧 Программное отключение USB..."
        echo 0 | sudo tee "$USB_DEVICE_PATH/authorized" >/dev/null
        sleep 5

        echo "🔧 Программное включение USB..."
        echo 1 | sudo tee "$USB_DEVICE_PATH/authorized" >/dev/null
        sleep 10

        echo "✅ USB переподключение выполнено"
    else
        echo "❌ Не удалось управлять USB authorized"
    fi
else
    echo "❌ USB устройство не найдено в sysfs"
fi

echo ""
echo "🔄 Метод 3: Сброс через reset endpoint"
echo "===================================="

echo "🔧 Попытка сброса через usb_modeswitch reset..."
sudo usb_modeswitch -v "$vendor" -p "$product" -R 2>/dev/null || true
sleep 15

if wait_for_interface; then
    if activate_interface; then
        echo "✅ Интерфейс восстановлен после reset"
    fi
fi

echo ""
echo "📊 Проверка результатов ротации"
echo "==============================="

if check_interface; then
    echo "✅ Интерфейс $INTERFACE активен"

    # Получаем новый IP
    echo "🌐 Получение нового внешнего IP..."
    NEW_IP=$(get_external_ip)

    echo ""
    echo "📋 Результат ротации:"
    echo "  Начальный IP: $INITIAL_IP"
    echo "  Новый IP:     $NEW_IP"

    if [ "$INITIAL_IP" != "$NEW_IP" ] && [ "$NEW_IP" != "unknown" ] && [ -n "$NEW_IP" ]; then
        echo "  ✅ IP успешно изменился!"
        echo ""
        echo "🎉 Переключение режимов модема РАБОТАЕТ для ротации IP!"
    else
        echo "  ⚠️ IP не изменился или не удалось получить новый IP"
        echo ""
        echo "❌ Переключение режимов модема НЕ РАБОТАЕТ для ротации IP"
    fi

    # Дополнительная информация
    echo ""
    echo "📊 Дополнительная информация:"
    local_ip=$(ip addr show "$INTERFACE" | grep "inet " | awk '{print $2}' | head -1)
    gateway=$(ip route show dev "$INTERFACE" | grep default | awk '{print $3}' | head -1)
    echo "  Локальный IP: $local_ip"
    echo "  Шлюз:        $gateway"

    # Проверка доступности веб-интерфейса модема
    if ping -c 1 -W 2 "$MODEM_IP" >/dev/null 2>&1; then
        echo "  Веб-интерфейс: $MODEM_IP доступен"
    else
        echo "  Веб-интерфейс: $MODEM_IP недоступен"
    fi

else
    echo "❌ Интерфейс $INTERFACE не активен"
    echo "❌ Тест не удался - интерфейс недоступен"
fi

echo ""
echo "🔍 Финальная диагностика"
echo "======================="

echo "📱 Информация об USB устройстве:"
lsusb | grep "$DEVICE_ID" || echo "  Устройство не найдено"

echo ""
echo "🔧 Режим устройства:"
device_mode=$(lsusb -v -d "$DEVICE_ID" 2>/dev/null | grep -E "bInterfaceClass.*[0-9]" | head -1)
echo "  $device_mode"

echo ""
echo "🌐 Сетевые интерфейсы:"
ip link show | grep -E "enx" || echo "  USB интерфейсы не найдены"

echo ""
echo "📊 Системные логи (последние 10 строк):"
sudo dmesg | tail -10 | grep -i "usb\|cdc\|rndis\|hilink" || echo "  Нет релевантных логов"

echo ""
echo "🏁 Тест завершён"
echo "==============="

if [ "$INITIAL_IP" != "$NEW_IP" ] && [ "$NEW_IP" != "unknown" ] && [ -n "$NEW_IP" ]; then
    echo "✅ Переключение режимов модема ЭФФЕКТИВНО для ротации IP!"
    echo ""
    echo "🚀 Рекомендации для интеграции:"
    echo "1. Реализовать метод 'mode_switch' в RotationManager"
    echo "2. Добавить задержки для стабилизации (15-20 секунд)"
    echo "3. Обеспечить переактивацию интерфейса после переключения"
    echo "4. Добавить мониторинг появления интерфейса"
    echo "5. Реализовать retry логику при неудачном переключении"
else
    echo "❌ Переключение режимов модема НЕ ЭФФЕКТИВНО для ротации IP"
    echo ""
    echo "🔧 Альтернативные решения:"
    echo "1. Исследовать API модема для переподключения"
    echo "2. Попробовать физическое переподключение USB"
    echo "3. Использовать AT-команды для сброса соединения"
    echo "4. Рассмотреть другие методы ротации IP"
fi
