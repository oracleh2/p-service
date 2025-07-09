#!/bin/bash

# Скрипт для поиска правильной команды переключения в Storage Mode
INTERFACE="enx0c5b8f279a64"
DEVICE_ID="12d1:14dc"  # Huawei E3372 HiLink

echo "🔍 Поиск команды для переключения в Storage Mode"
echo "==============================================="

# Получаем информацию о USB устройстве
vendor=$(echo "$DEVICE_ID" | cut -d: -f1)
product=$(echo "$DEVICE_ID" | cut -d: -f2)

echo "📱 Устройство: $vendor:$product"
echo "🔧 Интерфейс: $INTERFACE"
echo ""

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

# Функция проверки интерфейса
check_interface() {
    if ip link show "$INTERFACE" >/dev/null 2>&1; then
        if ip addr show "$INTERFACE" | grep -q "inet "; then
            echo "active"
        else
            echo "inactive"
        fi
    else
        echo "missing"
    fi
}

# Функция тестирования команды
test_command() {
    local command_name="$1"
    local command="$2"

    echo "🧪 Тест $command_name"
    echo "Команда: $command"

    # Проверяем начальное состояние
    local initial_mode=$(check_modem_mode)
    local initial_interface=$(check_interface)

    echo "  📋 Начальное состояние:"
    echo "    Режим: $initial_mode"
    echo "    Интерфейс: $initial_interface"

    # Выполняем команду
    echo "  🔧 Выполнение команды..."
    eval "$command" 2>/dev/null

    # Ждем стабилизации
    echo "  ⏳ Ожидание стабилизации (15 секунд)..."
    sleep 15

    # Проверяем результат
    local result_mode=$(check_modem_mode)
    local result_interface=$(check_interface)

    echo "  📊 Результат:"
    echo "    Режим: $result_mode"
    echo "    Интерфейс: $result_interface"

    # Определяем успешность
    if [ "$initial_mode" = "hilink" ] && [ "$result_mode" = "storage" ]; then
        echo "  ✅ УСПЕШНО: Переключился в Storage Mode!"
        return 0
    elif [ "$initial_interface" = "active" ] && [ "$result_interface" = "missing" ]; then
        echo "  ✅ ЧАСТИЧНО: Интерфейс исчез (возможно, Storage Mode)"
        return 0
    else
        echo "  ❌ НЕ СРАБОТАЛО: Режим не изменился"
        return 1
    fi
}

# Функция восстановления в HiLink режим
restore_hilink() {
    echo "🔄 Восстановление HiLink режима..."

    # Попробуем разные команды восстановления
    sudo usb_modeswitch -v "$vendor" -p "$product" -M '55534243123456780000000000000a11062000000000000100000000000000' 2>/dev/null
    sleep 5

    sudo usb_modeswitch -v "$vendor" -p "$product" -H 2>/dev/null
    sleep 5

    sudo usb_modeswitch -v "$vendor" -p "$product" -J 2>/dev/null
    sleep 5

    # Ждем восстановления
    echo "⏳ Ожидание восстановления (20 секунд)..."
    sleep 20

    # Проверяем восстановление
    local restored_mode=$(check_modem_mode)
    local restored_interface=$(check_interface)

    echo "📊 Состояние после восстановления:"
    echo "  Режим: $restored_mode"
    echo "  Интерфейс: $restored_interface"

    # Если интерфейс не активен, активируем его
    if [ "$restored_interface" != "active" ]; then
        echo "🔧 Активация интерфейса..."
        sudo ip link set "$INTERFACE" up 2>/dev/null
        sleep 2
        sudo ip addr flush dev "$INTERFACE" 2>/dev/null
        sudo pkill -f "dhclient.*$INTERFACE" 2>/dev/null
        timeout 15 sudo dhclient "$INTERFACE" 2>/dev/null

        local final_interface=$(check_interface)
        echo "  Финальный статус интерфейса: $final_interface"
    fi

    echo ""
}

# Проверяем начальное состояние
echo "📊 Начальное состояние системы"
echo "=============================="
initial_mode=$(check_modem_mode)
initial_interface=$(check_interface)

echo "📱 Режим модема: $initial_mode"
echo "🔧 Интерфейс: $initial_interface"

if [ "$initial_mode" != "hilink" ]; then
    echo "❌ Модем не в HiLink режиме. Сначала переключите в HiLink."
    exit 1
fi

if [ "$initial_interface" != "active" ]; then
    echo "❌ Интерфейс не активен. Сначала активируйте модем."
    exit 1
fi

echo ""
echo "🧪 Начинаем тестирование команд переключения в Storage Mode"
echo "=========================================================="

# Тестируем различные команды
SUCCESSFUL_COMMANDS=()

# Команда 1: Стандартный EJECT
echo ""
if test_command "1. Стандартный EJECT" "sudo usb_modeswitch -v $vendor -p $product -K"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -K")
fi
restore_hilink

# Команда 2: Detach only
echo ""
if test_command "2. Detach only" "sudo usb_modeswitch -v $vendor -p $product -d"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -d")
fi
restore_hilink

# Команда 3: Специальная команда массового хранения
echo ""
if test_command "3. Mass Storage message" "sudo usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000611000000000000000000000000000000'"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000611000000000000000000000000000000'")
fi
restore_hilink

# Команда 4: Альтернативная команда массового хранения
echo ""
if test_command "4. Alternative Mass Storage" "sudo usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000600000000000000000000000000000000'"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000600000000000000000000000000000000'")
fi
restore_hilink

# Команда 5: Конфигурация из файла
echo ""
if [ -f "/usr/share/usb_modeswitch/$DEVICE_ID" ]; then
    if test_command "5. Config file" "sudo usb_modeswitch -v $vendor -p $product -c /usr/share/usb_modeswitch/$DEVICE_ID"; then
        SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -c /usr/share/usb_modeswitch/$DEVICE_ID")
    fi
    restore_hilink
fi

# Команда 6: Обратная к HiLink команде
echo ""
if test_command "6. Reverse HiLink command" "sudo usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000a11062000000000000100000000000001'"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000a11062000000000000100000000000001'")
fi
restore_hilink

# Команда 7: Huawei режим X
echo ""
if test_command "7. Huawei alt mode" "sudo usb_modeswitch -v $vendor -p $product -X"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -X")
fi
restore_hilink

# Команда 8: Специальная команда отключения
echo ""
if test_command "8. Disconnect message" "sudo usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000000000000000000000000000000000000'"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000000000000000000000000000000000000'")
fi
restore_hilink

# Команда 9: Попытка через message-content2
echo ""
if test_command "9. Second message content" "sudo usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000a11062000000000000100000000000000' -2 '55534243123456780000000000000000000000000000000000000000000000'"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -M '55534243123456780000000000000a11062000000000000100000000000000' -2 '55534243123456780000000000000000000000000000000000000000000000'")
fi
restore_hilink

# Команда 10: Попытка через USB reset с задержкой
echo ""
if test_command "10. USB reset with delay" "sudo usb_modeswitch -v $vendor -p $product -R -w 2000"; then
    SUCCESSFUL_COMMANDS+=("usb_modeswitch -v $vendor -p $product -R -w 2000")
fi
restore_hilink

echo ""
echo "📊 Результаты тестирования"
echo "========================="

if [ ${#SUCCESSFUL_COMMANDS[@]} -gt 0 ]; then
    echo "✅ Найдены работающие команды:"
    for i in "${!SUCCESSFUL_COMMANDS[@]}"; do
        echo "  $((i+1)). ${SUCCESSFUL_COMMANDS[$i]}"
    done

    echo ""
    echo "🚀 Рекомендуемая команда для использования:"
    echo "   ${SUCCESSFUL_COMMANDS[0]}"

    echo ""
    echo "💾 Сохранить в файл test_results.txt? (y/N)"
    read -r save_results

    if [[ "$save_results" =~ ^[Yy]$ ]]; then
        {
            echo "# Результаты тестирования команд Storage Mode"
            echo "# Дата: $(date)"
            echo "# Устройство: $DEVICE_ID"
            echo ""
            echo "## Успешные команды:"
            for i in "${!SUCCESSFUL_COMMANDS[@]}"; do
                echo "$((i+1)). ${SUCCESSFUL_COMMANDS[$i]}"
            done
            echo ""
            echo "## Рекомендуемая команда:"
            echo "${SUCCESSFUL_COMMANDS[0]}"
        } > test_results.txt

        echo "✅ Результаты сохранены в test_results.txt"
    fi

else
    echo "❌ Ни одна команда не сработала"
    echo ""
    echo "🔧 Возможные причины:"
    echo "  1. Модем не поддерживает переключение в Storage Mode"
    echo "  2. Модем имеет заблокированную прошивку"
    echo "  3. Нужны специальные драйверы или утилиты"
    echo "  4. Модем требует физического отключения"
    echo ""
    echo "💡 Альтернативные методы ротации IP:"
    echo "  - API модема (dialup disconnect/connect)"
    echo "  - Перезагрузка через веб-интерфейс"
    echo "  - AT-команды через serial порт"
    echo "  - Физическое переподключение USB"
fi

echo ""
echo "🏁 Тестирование завершено"

# Финальная проверка состояния
final_mode=$(check_modem_mode)
final_interface=$(check_interface)

echo ""
echo "📊 Финальное состояние:"
echo "  Режим: $final_mode"
echo "  Интерфейс: $final_interface"

if [ "$final_mode" = "hilink" ] && [ "$final_interface" = "active" ]; then
    echo "✅ Система восстановлена в рабочее состояние"
else
    echo "⚠️  Возможно, потребуется ручное восстановление"
    echo "   Попробуйте: ./setup_e3372.sh"
fi

