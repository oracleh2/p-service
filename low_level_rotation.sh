#!/bin/bash

# Низкоуровневые подходы к ротации IP
INTERFACE="enx0c5b8f279a64"
MODEM_IP="192.168.108.1"

echo "⚙️ Низкоуровневые подходы к ротации IP"
echo "====================================="

# Метод 1: Прямая работа с TTY устройствами
echo ""
echo "1. Прямая работа с TTY устройствами"
echo "=================================="

echo "🔍 Поиск TTY устройств модема..."
for tty_device in /dev/ttyUSB* /dev/ttyACM*; do
    if [ -c "$tty_device" ]; then
        echo "  📱 Найден: $tty_device"

        # Проверка доступности
        if [ -r "$tty_device" ] && [ -w "$tty_device" ]; then
            echo "    ✅ Доступен для чтения/записи"

            # Попытка отправки AT команды безопасно
            echo "    🔧 Тест связи..."
            timeout 3 bash -c "echo 'AT' > '$tty_device' && sleep 1 && cat '$tty_device'" 2>/dev/null
        else
            echo "    ❌ Недоступен для чтения/записи"
        fi
    fi
done

# Метод 2: Управление через sysfs
echo ""
echo "2. Управление через sysfs"
echo "======================="

echo "🔍 Поиск sysfs записей для модема..."
SYSFS_PATHS=(
    "/sys/class/net/$INTERFACE"
    "/sys/class/tty/ttyUSB*"
    "/sys/class/usb_device/*"
)

for path_pattern in "${SYSFS_PATHS[@]}"; do
    for path in $path_pattern; do
        if [ -d "$path" ]; then
            echo "  📂 Найден: $path"

            # Ищем интересные файлы
            for file in "$path"/*; do
                if [ -f "$file" ] && [ -r "$file" ]; then
                    filename=$(basename "$file")
                    case "$filename" in
                        "power"|"reset"|"remove"|"authorized"|"bConfigurationValue")
                            echo "    🔧 Управляющий файл: $filename"
                            if [ -w "$file" ]; then
                                echo "      ✅ Доступен для записи"
                            else
                                echo "      ❌ Только для чтения"
                            fi
                            ;;
                    esac
                fi
            done
        fi
    done
done

# Метод 3: Управление питанием USB
echo ""
echo "3. Управление питанием USB"
echo "========================"

echo "🔍 Поиск USB устройств модема..."
for usb_device in /sys/bus/usb/devices/*; do
    if [ -d "$usb_device" ]; then
        # Проверяем vendor:product
        if [ -f "$usb_device/idVendor" ] && [ -f "$usb_device/idProduct" ]; then
            vendor=$(cat "$usb_device/idVendor" 2>/dev/null)
            product=$(cat "$usb_device/idProduct" 2>/dev/null)

            if [ "$vendor" = "12d1" ]; then  # Huawei
                echo "  📱 Huawei устройство: $usb_device ($vendor:$product)"

                # Проверяем доступные управляющие файлы
                for control_file in "power/control" "power/autosuspend" "authorized" "remove"; do
                    if [ -f "$usb_device/$control_file" ]; then
                        echo "    🔧 Управляющий файл: $control_file"
                        if [ -w "$usb_device/$control_file" ]; then
                            current_value=$(cat "$usb_device/$control_file" 2>/dev/null)
                            echo "      Текущее значение: $current_value"
                            echo "      ✅ Доступен для записи"
                        fi
                    fi
                done
            fi
        fi
    fi
done

# Метод 4: Kernel modules управление
echo ""
echo "4. Kernel modules управление"
echo "=========================="

echo "🔍 Проверка загруженных модулей..."
MODULES=("cdc_ether" "usbnet" "option" "usb_wwan" "qmi_wwan" "cdc_mbim")

for module in "${MODULES[@]}"; do
    if lsmod | grep -q "^$module"; then
        echo "  ✅ Модуль $module загружен"

        # Информация о модуле
        modinfo "$module" 2>/dev/null | grep -E "^(description|author|version)" | head -3

        # Параметры модуля
        if [ -d "/sys/module/$module/parameters" ]; then
            echo "    🔧 Параметры:"
            for param in "/sys/module/$module/parameters"/*; do
                if [ -f "$param" ]; then
                    param_name=$(basename "$param")
                    param_value=$(cat "$param" 2>/dev/null)
                    echo "      $param_name = $param_value"
                fi
            done
        fi
    else
        echo "  ❌ Модуль $module не загружен"
    fi
done

# Метод 5: Прямая работа с сетевыми пакетами
echo ""
echo "5. Прямая работа с сетевыми пакетами"
echo "=================================="

if command -v tcpdump >/dev/null 2>&1; then
    echo "🔍 Анализ трафика на интерфейсе $INTERFACE (5 секунд)..."
    timeout 5 tcpdump -i "$INTERFACE" -c 10 2>/dev/null | head -5
else
    echo "❌ tcpdump не установлен"
fi

# Проверка ARP таблицы
echo ""
echo "🔍 ARP таблица для модема:"
arp -n | grep "$MODEM_IP" || echo "  Записей не найдено"

# Метод 6: Эмуляция физического отключения через GPIO (если доступно)
echo ""
echo "6. Эмуляция физического отключения"
echo "================================="

echo "🔍 Проверка GPIO интерфейсов..."
if [ -d "/sys/class/gpio" ]; then
    echo "  ✅ GPIO интерфейс доступен"

    # Список доступных GPIO
    if [ -f "/sys/class/gpio/gpiochip0/ngpio" ]; then
        ngpio=$(cat /sys/class/gpio/gpiochip0/ngpio 2>/dev/null)
        echo "  📊 Доступно GPIO пинов: $ngpio"
    fi

    # Проверка экспортированных GPIO
    if [ -d "/sys/class/gpio" ]; then
        exported_gpios=$(ls /sys/class/gpio/ | grep "^gpio[0-9]" | wc -l)
        echo "  📊 Экспортированных GPIO: $exported_gpios"
    fi
else
    echo "  ❌ GPIO интерфейс недоступен"
fi

# Метод 7: Программная эмуляция USB disconnect
echo ""
echo "7. Программная эмуляция USB disconnect"
echo "====================================="

echo "🔧 Тестирование USB disconnect эмуляции..."

# Поиск USB устройства
USB_DEVICE_PATH=$(find /sys/bus/usb/devices -name "*12d1*" -type d | head -1)
if [ -n "$USB_DEVICE_PATH" ]; then
    echo "  📱 USB устройство найдено: $USB_DEVICE_PATH"

    # Проверяем authorized файл
    if [ -f "$USB_DEVICE_PATH/authorized" ]; then
        echo "  🔧 Попытка программного отключения..."
        current_auth=$(cat "$USB_DEVICE_PATH/authorized")
        echo "    Текущий статус authorized: $current_auth"

        if [ -w "$USB_DEVICE_PATH/authorized" ]; then
            echo "    ✅ Можно управлять авторизацией"
        else
            echo "    ❌ Нет прав на управление авторизацией"
        fi
    fi

    # Проверяем remove файл
    if [ -f "$USB_DEVICE_PATH/remove" ]; then
        echo "  🔧 Remove файл доступен"
        if [ -w "$USB_DEVICE_PATH/remove" ]; then
            echo "    ✅ Можно программно удалить устройство"
        else
            echo "    ❌ Нет прав на удаление устройства"
        fi
    fi
fi

echo ""
echo "📊 Резюме низкоуровневых методов:"
echo "================================="
echo "1. TTY устройства - прямая отправка AT команд"
echo "2. sysfs управление - низкоуровневый доступ к устройству"
echo "3. USB питание - управление питанием через sysfs"
echo "4. Kernel modules - перезагрузка драйверов"
echo "5. Сетевые пакеты - анализ и вмешательство в трафик"
echo "6. GPIO эмуляция - физическое управление (если доступно)"
echo "7. USB disconnect - программная эмуляция отключения"

