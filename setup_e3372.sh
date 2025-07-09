#!/bin/bash
# Улучшенная универсальная настройка Huawei модемов
# Исправляет проблемы с переключением режимов и активацией интерфейсов

# Флаги командной строки
CONFIGURE_WEB_INTERFACE=false

# Обработка аргументов
while [[ $# -gt 0 ]]; do
    case $1 in
        --with-web)
            CONFIGURE_WEB_INTERFACE=true
            shift
            ;;
        -h|--help)
            echo "Использование: $0 [опции]"
            echo ""
            echo "Опции:"
            echo "  --with-web    Настроить веб-интерфейс модемов"
            echo "  -h, --help    Показать эту справку"
            echo ""
            echo "Примеры:"
            echo "  $0                # Базовая настройка всех модемов"
            echo "  $0 --with-web     # Настройка с веб-интерфейсом"
            exit 0
            ;;
        *)
            echo "❌ Неизвестный аргумент: $1"
            echo "Используйте -h для справки"
            exit 1
            ;;
    esac
done

echo "🔧 Улучшенная настройка Huawei модемов"
echo "======================================="

# Список поддерживаемых модемов Huawei
HUAWEI_MODEMS=(
    "12d1:14dc"  # E3372 HiLink
    "12d1:1f01"  # E3372 Stick
    "12d1:157d"  # E3372h
    "12d1:14db"  # E3372s
    "12d1:1506"  # E5770s
    "12d1:1573"  # E5770
    "12d1:15ca"  # E8372
    "12d1:1442"  # E5573
    "12d1:14fe"  # E5577
)

declare -A MODEM_NAMES=(
    ["12d1:14dc"]="E3372 HiLink"
    ["12d1:1f01"]="E3372 Stick"
    ["12d1:157d"]="E3372h"
    ["12d1:14db"]="E3372s"
    ["12d1:1506"]="E5770s"
    ["12d1:1573"]="E5770"
    ["12d1:15ca"]="E8372"
    ["12d1:1442"]="E5573"
    ["12d1:14fe"]="E5577"
)

# Поиск всех подключенных Huawei модемов
echo "1. Поиск всех подключенных Huawei модемов..."

FOUND_MODEMS=()
for modem_id in "${HUAWEI_MODEMS[@]}"; do
    if lsusb | grep -q "$modem_id"; then
        FOUND_MODEMS+=("$modem_id")
        modem_name="${MODEM_NAMES[$modem_id]}"
        bus_device=$(lsusb | grep "$modem_id" | awk '{print $2 ":" $4}' | tr -d ':')
        echo "✅ Найден: Huawei $modem_name (ID: $modem_id, Bus/Device: $bus_device)"
    fi
done

if [ ${#FOUND_MODEMS[@]} -eq 0 ]; then
    echo "❌ Huawei модемы не найдены"
    exit 1
fi

echo ""
echo "📊 Найдено модемов: ${#FOUND_MODEMS[@]}"

# Проверяем существующие USB сетевые интерфейсы
echo ""
echo "2. Поиск существующих USB сетевых интерфейсов..."

USB_INTERFACES=()
for interface in $(ip link show | grep -E "enx" | cut -d: -f2 | tr -d ' '); do
    USB_INTERFACES+=("$interface")
    state=$(ip link show "$interface" | grep -o "state [A-Z]*" | cut -d' ' -f2)
    echo "🔍 Найден USB интерфейс: $interface (состояние: $state)"
done

if [ ${#USB_INTERFACES[@]} -gt 0 ]; then
    echo ""
    echo "📶 Обнаружены готовые USB интерфейсы! Попробуем их активировать..."

    for interface in "${USB_INTERFACES[@]}"; do
        echo ""
        echo "🔧 Настройка интерфейса $interface..."

        # Проверяем текущее состояние
        if ip addr show "$interface" | grep -q "inet "; then
            ip_addr=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
            echo "  ✅ Уже настроен: $ip_addr"
            continue
        fi

        # Поднимаем интерфейс
        echo "  🔗 Активация интерфейса..."
        sudo ip link set "$interface" up
        sleep 2

        # Пытаемся получить IP через DHCP
        echo "  🌐 Получение IP адреса через DHCP..."

        # Останавливаем существующие процессы dhclient для этого интерфейса
        sudo pkill -f "dhclient.*$interface" 2>/dev/null || true
        sleep 1

        # Запускаем dhclient в фоне с таймаутом
        timeout 20 sudo dhclient -v "$interface" 2>/dev/null &
        DHCP_PID=$!

        # Ждем результата
        for i in {1..20}; do
            if ip addr show "$interface" | grep -q "inet "; then
                ip_address=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
                echo "  ✅ IP адрес получен: $ip_address"

                # Проверяем маршрут
                gateway=$(ip route show dev "$interface" | grep default | awk '{print $3}' | head -1)
                if [ -n "$gateway" ]; then
                    echo "  ✅ Шлюз: $gateway"
                fi

                # Тестируем соединение
                echo "  🌐 Тест интернета..."
                if timeout 10 curl -s --interface "$interface" http://httpbin.org/ip >/dev/null 2>&1; then
                    external_ip=$(timeout 10 curl -s --interface "$interface" http://httpbin.org/ip | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
                    echo "  ✅ Интернет работает! Внешний IP: $external_ip"
                else
                    echo "  ⚠️  Интернет не работает (возможно, нужен PIN или SIM)"
                fi
                break
            fi

            echo "  ⏳ Ожидание IP... ($i/20)"
            sleep 1
        done

        # Завершаем процесс dhclient
        kill $DHCP_PID 2>/dev/null || true

        if ! ip addr show "$interface" | grep -q "inet "; then
            echo "  ❌ IP адрес не получен"
        fi
    done
fi

echo ""
echo "3. Улучшенное переключение режимов модемов..."

declare -A MODEM_INFO
MODEMS_TO_CONFIGURE=()

for modem_id in "${FOUND_MODEMS[@]}"; do
    echo ""
    echo "🔍 Анализ $modem_id (${MODEM_NAMES[$modem_id]})..."

    # Получаем детальную информацию
    vendor=$(echo "$modem_id" | cut -d: -f1)
    product=$(echo "$modem_id" | cut -d: -f2)

    # Проверяем текущий режим через lsusb
    device_info=$(lsusb -v -d "$modem_id" 2>/dev/null)

    # Улучшенное определение режима
    if echo "$device_info" | grep -q "bInterfaceClass.*8 Mass Storage"; then
        mode="storage"
        echo "  💾 Режим: Mass Storage (требует переключения)"
        needs_switching=true
    elif echo "$device_info" | grep -q "bInterfaceClass.*2 Communications"; then
        mode="hilink"
        echo "  📱 Режим: HiLink Communications"
        needs_switching=false
    elif echo "$device_info" | grep -q "bInterfaceClass.*255 Vendor Specific"; then
        mode="vendor_specific"
        echo "  🔧 Режим: Vendor Specific (возможно, уже переключен)"
        needs_switching=false
    else
        mode="unknown"
        echo "  ❓ Режим: Неопределенный"
        needs_switching=true
    fi

    # Если нужно переключение, пытаемся разными способами
    if [ "$needs_switching" = true ]; then
        echo "  🔄 Попытка переключения режима..."

        # Способ 1: Стандартный usb_modeswitch
        echo "    Способ 1: Стандартное переключение..."
        if [ -f "/usr/share/usb_modeswitch/$modem_id" ]; then
            echo "sudo usb_modeswitch -v \"$vendor\" -p \"$product\" -c \"/usr/share/usb_modeswitch/$modem_id\""
            sudo usb_modeswitch -v "$vendor" -p "$product" -c "/usr/share/usb_modeswitch/$modem_id" 2>/dev/null
        else
            echo "sudo usb_modeswitch -v \"$vendor\" -p \"$product\" -M '55534243123456780000000000000a11062000000000000100000000000000'"
            sudo usb_modeswitch -v "$vendor" -p "$product" -M '55534243123456780000000000000a11062000000000000100000000000000' 2>/dev/null
        fi
        sleep 5

        # Проверяем результат
        if lsusb -v -d "$modem_id" 2>/dev/null | grep -q "bInterfaceClass.*2 Communications"; then
            echo "    ✅ Способ 1 успешен"
        else
            # Способ 2: Альтернативные команды для E3372
            echo "    Способ 2: Альтернативное переключение для E3372..."
            if [ "$modem_id" = "12d1:14dc" ]; then
                # Специальные команды для E3372
                sudo usb_modeswitch -v "$vendor" -p "$product" -J 2>/dev/null || true
                sleep 3
                sudo usb_modeswitch -v "$vendor" -p "$product" -H 2>/dev/null || true
                sleep 3
            fi

            # Способ 3: Переподключение USB
            echo "    Способ 3: Программное переподключение..."
            bus_device=$(lsusb | grep "$modem_id" | awk '{print $2 ":" $4}' | tr -d ':')
            bus_num=$(echo "$bus_device" | cut -d: -f1)
            dev_num=$(echo "$bus_device" | cut -d: -f2)

            # Попытка reset через USB
            if [ -f "/sys/bus/usb/devices/$bus_num-1" ]; then
                echo 0 | sudo tee "/sys/bus/usb/devices/$bus_num-1/authorized" >/dev/null 2>&1 || true
                sleep 2
                echo 1 | sudo tee "/sys/bus/usb/devices/$bus_num-1/authorized" >/dev/null 2>&1 || true
                sleep 3
            fi
        fi

        # Финальная проверка
        echo "  ⏳ Ожидание стабилизации (10 секунд)..."
        sleep 10
    fi

    MODEM_INFO["${modem_id}_processed"]="true"
done

echo ""
echo "4. Финальная активация интерфейсов..."

# Повторно ищем все USB интерфейсы после переключения
ALL_USB_INTERFACES=()
for interface in $(ip link show | grep -E "enx" | cut -d: -f2 | tr -d ' '); do
    ALL_USB_INTERFACES+=("$interface")
done

if [ ${#ALL_USB_INTERFACES[@]} -eq 0 ]; then
    echo "❌ USB сетевые интерфейсы не найдены"
    echo ""
    echo "🔧 Возможные решения:"
    echo "1. Переподключите модем к другому USB порту"
    echo "2. Попробуйте другой USB кабель"
    echo "3. Проверьте, что SIM-карта вставлена"
    echo "4. Перезагрузите компьютер"
else
    echo "✅ Найдено USB интерфейсов: ${#ALL_USB_INTERFACES[@]}"

    WORKING_INTERFACES=0

    for interface in "${ALL_USB_INTERFACES[@]}"; do
        echo ""
        echo "🔧 Финальная настройка $interface..."

        # Принудительно поднимаем интерфейс
        sudo ip link set "$interface" up

        # Если уже есть IP, пропускаем
        if ip addr show "$interface" | grep -q "inet "; then
            ip_addr=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
            echo "  ✅ Уже настроен: $ip_addr"
            WORKING_INTERFACES=$((WORKING_INTERFACES + 1))
            continue
        fi

        # Освобождаем интерфейс от старых настроек
        sudo ip addr flush dev "$interface" 2>/dev/null || true
        sudo pkill -f "dhclient.*$interface" 2>/dev/null || true

        # Пытаемся получить IP разными способами
        echo "  🌐 Попытка 1: dhclient..."
        timeout 15 sudo dhclient -v "$interface" 2>/dev/null || true

        if ip addr show "$interface" | grep -q "inet "; then
            ip_address=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
            echo "  ✅ IP получен: $ip_address"
            WORKING_INTERFACES=$((WORKING_INTERFACES + 1))
        else
            echo "  🔄 Попытка 2: NetworkManager..."
            # Пытаемся через NetworkManager
            if command -v nmcli &> /dev/null; then
                nmcli device connect "$interface" 2>/dev/null || true
                sleep 5

                if ip addr show "$interface" | grep -q "inet "; then
                    ip_address=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
                    echo "  ✅ IP получен через NM: $ip_address"
                    WORKING_INTERFACES=$((WORKING_INTERFACES + 1))
                else
                    echo "  ❌ IP не получен"
                fi
            else
                echo "  ❌ NetworkManager недоступен"
            fi
        fi
    done

    echo ""
    echo "📊 Результат настройки:"
    echo "======================="
    echo "🔧 Всего USB интерфейсов: ${#ALL_USB_INTERFACES[@]}"
    echo "✅ Рабочих интерфейсов: $WORKING_INTERFACES"
fi

# Проверка веб-интерфейсов
if [ "$CONFIGURE_WEB_INTERFACE" = true ]; then
    echo ""
    echo "5. Поиск веб-интерфейсов модемов..."

    WEB_IPS=("192.168.8.1" "192.168.1.1" "192.168.43.1" "192.168.0.1" "192.168.107.1")
    FOUND_WEB=0

    for ip in "${WEB_IPS[@]}"; do
        echo -n "  Проверяем $ip... "
        if ping -c 1 -W 2 "$ip" >/dev/null 2>&1; then
            if curl -s --connect-timeout 3 "http://$ip" | grep -qi "huawei\|mobile.*wifi\|lte"; then
                echo "✅ Найден"
                FOUND_WEB=$((FOUND_WEB + 1))

                # Получаем информацию о модеме
                device_info=$(curl -s "http://$ip/api/device/information" 2>/dev/null)
                if [ -n "$device_info" ]; then
                    model=$(echo "$device_info" | grep -o '<DeviceName>[^<]*</DeviceName>' | sed 's/<[^>]*>//g')
                    echo "    📱 Модель: ${model:-"Unknown"}"
                fi
            else
                echo "❌"
            fi
        else
            echo "❌"
        fi
    done

    echo ""
    echo "✅ Найдено веб-интерфейсов: $FOUND_WEB"
fi

echo ""
echo "🏁 Настройка завершена!"
echo "======================="

# Финальная статистика
echo ""
echo "📋 Итоговая информация:"
for interface in "${ALL_USB_INTERFACES[@]}"; do
    if ip addr show "$interface" | grep -q "inet "; then
        ip_addr=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
        echo "  🌐 $interface: $ip_addr"

        # Тест интернета
        if timeout 5 curl -s --interface "$interface" http://httpbin.org/ip >/dev/null 2>&1; then
            echo "    ✅ Интернет работает"
        else
            echo "    ⚠️  Интернет не работает"
        fi
    else
        echo "  ❌ $interface: не настроен"
    fi
done

if [ $WORKING_INTERFACES -gt 0 ]; then
    echo ""
    echo "🎉 Успех! Настроено интерфейсов: $WORKING_INTERFACES"
    echo ""
    echo "🚀 Следующие шаги:"
    echo "1. Интегрируйте модемы в Mobile Proxy Service"
    echo "2. Настройте автоматическую ротацию IP"
    echo "3. Добавьте мониторинг состояния"
else
    echo ""
    echo "⚠️  Требуется ручная настройка"
    echo ""
    echo "🔧 Попробуйте:"
    echo "1. Запустить скрипт с --with-web"
    echo "2. Проверить SIM-карту и PIN код"
    echo "3. Переподключить модем к другому порту"
    echo "4. Перезагрузить компьютер"
fi
