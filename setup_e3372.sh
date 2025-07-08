#!/bin/bash
# Универсальная настройка Huawei модемов в Ubuntu
# Поддерживает множественные модемы E3372, E3372h, E5770s и другие

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

echo "🔧 Универсальная настройка Huawei модемов"
echo "=========================================="

# Список поддерживаемых модемов Huawei (vendor:product)
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

# Ассоциативный массив названий модемов
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
    echo ""
    echo "🔍 Проверьте подключенные USB устройства:"
    lsusb | grep -i huawei || echo "  Нет устройств Huawei"
    echo ""
    echo "💡 Убедитесь, что:"
    echo "  - Модем подключен к USB порту"
    echo "  - USB кабель исправен"
    echo "  - Модем включен"
    exit 1
fi

echo ""
echo "📊 Найдено модемов: ${#FOUND_MODEMS[@]}"

# Определяем режим каждого модема и сохраняем информацию
echo ""
echo "2. Анализ режимов всех найденных модемов..."

declare -A MODEM_INFO
MODEMS_TO_CONFIGURE=()

for modem_id in "${FOUND_MODEMS[@]}"; do
    echo ""
    echo "🔍 Анализируем $modem_id (${MODEM_NAMES[$modem_id]})..."

    # Получаем детальную информацию о модеме
    DEVICE_INFO=$(lsusb -v -d "$modem_id" 2>/dev/null)

    # Определяем режим модема
    if echo "$DEVICE_INFO" | grep -q "bInterfaceClass.*9 Hub"; then
        mode="hub"
        echo "  🔌 Режим: USB Hub (возможно, составное устройство)"
    elif echo "$DEVICE_INFO" | grep -q "bInterfaceClass.*2 Communications"; then
        mode="hilink"
        echo "  📱 Режим: HiLink (модем-роутер)"
    elif echo "$DEVICE_INFO" | grep -q "bInterfaceClass.*8 Mass Storage"; then
        mode="storage"
        echo "  💾 Режим: Накопитель (требует переключения)"
    elif echo "$DEVICE_INFO" | grep -q "bInterfaceClass.*255 Vendor Specific"; then
        mode="modem"
        echo "  📡 Режим: Модем (Stick mode)"
    else
        mode="unknown"
        echo "  ❓ Режим: Неизвестный"
    fi

    # Получаем Bus и Device номера
    bus_device=$(lsusb | grep "$modem_id" | awk '{print $2 ":" $4}' | tr -d ':')
    bus_num=$(echo "$bus_device" | cut -d: -f1)
    dev_num=$(echo "$bus_device" | cut -d: -f2)

    # Ищем связанные сетевые интерфейсы
    network_interface=""
    for interface in $(ip link show | grep -E "enx|usb" | cut -d: -f2 | tr -d ' '); do
        # Проверяем, связан ли интерфейс с этим USB устройством
        if [ -d "/sys/class/net/$interface/device" ]; then
            usb_path=$(readlink "/sys/class/net/$interface/device" 2>/dev/null | grep -o "[0-9]*-[0-9]*" | head -1)
            if [ -n "$usb_path" ]; then
                interface_bus=$(echo "$usb_path" | cut -d- -f1)
                # Простая проверка соответствия
                if [ "$interface_bus" = "$bus_num" ]; then
                    network_interface="$interface"
                    break
                fi
            fi
        fi
    done

    if [ -n "$network_interface" ]; then
        # Проверяем состояние интерфейса
        if ip addr show "$network_interface" | grep -q "inet "; then
            ip_address=$(ip addr show "$network_interface" | grep "inet " | awk '{print $2}' | head -1)
            echo "  🌐 Сетевой интерфейс: $network_interface (IP: $ip_address) ✅"
            interface_status="configured"
        else
            echo "  🌐 Сетевой интерфейс: $network_interface (не настроен) ⚠️"
            interface_status="not_configured"
        fi
    else
        echo "  🌐 Сетевой интерфейс: не найден ❌"
        interface_status="missing"
    fi

    # Сохраняем информацию о модеме
    MODEM_INFO["${modem_id}_mode"]="$mode"
    MODEM_INFO["${modem_id}_bus_device"]="$bus_device"
    MODEM_INFO["${modem_id}_interface"]="$network_interface"
    MODEM_INFO["${modem_id}_interface_status"]="$interface_status"

    # Добавляем в список для настройки, если требуется
    if [ "$mode" = "storage" ] || [ "$interface_status" = "missing" ] || [ "$interface_status" = "not_configured" ]; then
        MODEMS_TO_CONFIGURE+=("$modem_id")
        echo "  📝 Требует настройки: Да"
    else
        echo "  📝 Требует настройки: Нет"
    fi
done

echo ""
echo "3. Установка необходимых пакетов..."

# Проверяем и устанавливаем usb-modeswitch
if ! command -v usb_modeswitch &> /dev/null; then
    echo "📦 Устанавливаем usb-modeswitch..."
    sudo apt update
    sudo apt install -y usb-modeswitch usb-modeswitch-data
else
    echo "✅ usb-modeswitch уже установлен"
fi

# Устанавливаем дополнительные пакеты для работы с модемами
if ! command -v wvdial &> /dev/null; then
    echo "📦 Устанавливаем дополнительные пакеты для модемов..."
    sudo apt install -y ppp wvdial
else
    echo "✅ Пакеты для модемов уже установлены"
fi

# Проверяем NetworkManager
if ! systemctl is-active --quiet NetworkManager; then
    echo "📦 Устанавливаем и запускаем NetworkManager..."
    sudo apt install -y network-manager
    sudo systemctl enable NetworkManager
    sudo systemctl start NetworkManager
else
    echo "✅ NetworkManager работает"
fi

echo ""
echo "4. Настройка модемов..."

if [ ${#MODEMS_TO_CONFIGURE[@]} -eq 0 ]; then
    echo "✅ Все модемы уже настроены!"
else
    echo "🔧 Настраиваем ${#MODEMS_TO_CONFIGURE[@]} модем(ов)..."

    for modem_id in "${MODEMS_TO_CONFIGURE[@]}"; do
        echo ""
        echo "⚙️  Настройка $modem_id (${MODEM_NAMES[$modem_id]})..."

        mode="${MODEM_INFO[${modem_id}_mode]}"

        # Переключаем модем из режима накопителя
        if [ "$mode" = "storage" ]; then
            echo "  🔄 Переключаем из режима накопителя..."
            vendor=$(echo "$modem_id" | cut -d: -f1)
            product=$(echo "$modem_id" | cut -d: -f2)

            # Пытаемся найти конфигурацию для usb_modeswitch
            if [ -f "/usr/share/usb_modeswitch/$modem_id" ]; then
                sudo usb_modeswitch -v "$vendor" -p "$product" -c "/usr/share/usb_modeswitch/$modem_id"
            else
                # Используем общую конфигурацию для Huawei
                sudo usb_modeswitch -v "$vendor" -p "$product" -M '55534243123456780000000000000a11062000000000000100000000000000'
            fi

            echo "  ⏳ Ждем переключения (15 секунд)..."
            sleep 15
        fi

        # Ищем появившиеся сетевые интерфейсы
        echo "  🔍 Поиск сетевых интерфейсов..."
        interface_found=false

        for attempt in {1..20}; do
            # Ищем новые интерфейсы, связанные с USB
            for interface in $(ip link show | grep -E "enx|usb" | cut -d: -f2 | tr -d ' '); do
                if [ -z "${MODEM_INFO[${modem_id}_interface]}" ] || [ "${MODEM_INFO[${modem_id}_interface]}" != "$interface" ]; then
                    # Проверяем, что интерфейс активен
                    if ip link show "$interface" | grep -q "state UP\|state UNKNOWN"; then
                        echo "  ✅ Найден новый интерфейс: $interface"
                        MODEM_INFO["${modem_id}_interface"]="$interface"
                        interface_found=true
                        break
                    fi
                fi
            done

            if [ "$interface_found" = true ]; then
                break
            fi

            echo "  ⏳ Ожидание интерфейса... ($attempt/20)"
            sleep 3
        done

        # Настраиваем найденный интерфейс
        if [ "$interface_found" = true ]; then
            interface="${MODEM_INFO[${modem_id}_interface]}"
            echo "  🔗 Настройка интерфейса $interface..."

            # Поднимаем интерфейс
            sudo ip link set "$interface" up

            # Получаем IP через DHCP
            echo "  🌐 Получение IP адреса..."
            if command -v dhclient &> /dev/null; then
                timeout 15 sudo dhclient "$interface" 2>/dev/null || true
            elif command -v dhcpcd &> /dev/null; then
                timeout 15 sudo dhcpcd "$interface" 2>/dev/null || true
            fi

            sleep 5

            # Проверяем результат
            if ip addr show "$interface" | grep -q "inet "; then
                ip_address=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
                echo "  ✅ IP адрес получен: $ip_address"
                MODEM_INFO["${modem_id}_interface_status"]="configured"

                # Проверяем маршрут
                gateway=$(ip route show dev "$interface" | grep default | awk '{print $3}' | head -1)
                if [ -n "$gateway" ]; then
                    echo "  ✅ Шлюз: $gateway"
                fi
            else
                echo "  ⚠️  IP адрес не получен автоматически"
                MODEM_INFO["${modem_id}_interface_status"]="manual_required"
            fi
        else
            echo "  ❌ Сетевой интерфейс не найден"
            MODEM_INFO["${modem_id}_interface_status"]="missing"
        fi
    done
fi

echo ""
echo "5. Настройка веб-интерфейсов (опционально)..."

if [ "$CONFIGURE_WEB_INTERFACE" = true ]; then
    echo "🌐 Настройка веб-интерфейсов модемов..."

    # Расширенный список возможных IP адресов для веб-интерфейсов
    WEB_IPS=(
        "192.168.8.1"     # Стандартный Huawei
        "192.168.1.1"     # Альтернативный
        "192.168.43.1"    # Точка доступа
        "192.168.0.1"     # Роутер режим
        "192.168.107.1"   # Пользовательский
        "192.168.100.1"   # Пользовательский
        "10.0.0.1"        # Альтернативная сеть
    )

    declare -A WORKING_WEB_INTERFACES

    echo "  🔍 Поиск активных веб-интерфейсов..."

    for ip in "${WEB_IPS[@]}"; do
        echo -n "    Проверяем $ip... "

        # Проверяем доступность веб-интерфейса
        if ping -c 1 -W 2 "$ip" >/dev/null 2>&1; then
            # Проверяем, что это действительно веб-интерфейс Huawei
            if curl -s --connect-timeout 3 "http://$ip" | grep -qi "huawei\|mobile.*wifi\|lte\|4g"; then
                echo "✅ Найден"

                # Пытаемся получить информацию о модеме
                device_info=$(curl -s --connect-timeout 5 "http://$ip/api/device/information" 2>/dev/null)
                if [ -n "$device_info" ]; then
                    model=$(echo "$device_info" | grep -o '<DeviceName>[^<]*</DeviceName>' | sed 's/<[^>]*>//g')
                    imei=$(echo "$device_info" | grep -o '<Imei>[^<]*</Imei>' | sed 's/<[^>]*>//g')

                    if [ -n "$model" ]; then
                        echo "      📱 Модель: $model"
                        WORKING_WEB_INTERFACES["$ip"]="$model"
                    fi
                    if [ -n "$imei" ]; then
                        echo "      🆔 IMEI: $imei"
                    fi

                    # Проверяем статус подключения
                    status_info=$(curl -s --connect-timeout 5 "http://$ip/api/monitoring/status" 2>/dev/null)
                    if [ -n "$status_info" ]; then
                        connection_status=$(echo "$status_info" | grep -o '<ConnectionStatus>[^<]*</ConnectionStatus>' | sed 's/<[^>]*>//g')
                        case "$connection_status" in
                            "901") echo "      📶 Статус: Подключено" ;;
                            "902") echo "      📶 Статус: Отключено" ;;
                            "903") echo "      📶 Статус: Отключение..." ;;
                            "904") echo "      📶 Статус: Подключение..." ;;
                            *) echo "      📶 Статус: $connection_status" ;;
                        esac

                        # Если модем отключен, пытаемся подключить
                        if [ "$connection_status" = "902" ]; then
                            echo "      🔄 Попытка подключения..."
                            token=$(curl -s "http://$ip/api/webserver/SesTokInfo" | grep -o '<SesInfo>[^<]*</SesInfo>' | sed 's/<[^>]*>//g')
                            if [ -n "$token" ]; then
                                curl -s -X POST \
                                    -H "Content-Type: application/x-www-form-urlencoded" \
                                    -H "__RequestVerificationToken: $token" \
                                    -d '<?xml version="1.0" encoding="UTF-8"?><request><Action>1</Action></request>' \
                                    "http://$ip/api/dialup/dial" >/dev/null 2>&1

                                sleep 5

                                # Проверяем результат
                                new_status=$(curl -s "http://$ip/api/monitoring/status" | grep -o '<ConnectionStatus>[^<]*</ConnectionStatus>' | sed 's/<[^>]*>//g')
                                if [ "$new_status" = "901" ] || [ "$new_status" = "904" ]; then
                                    echo "      ✅ Подключение успешно"
                                else
                                    echo "      ⚠️  Подключение не удалось (возможно, нужен PIN код)"
                                fi
                            fi
                        fi
                    fi
                else
                    echo "      ⚠️  API недоступен"
                    WORKING_WEB_INTERFACES["$ip"]="Unknown model"
                fi
            else
                echo "❌ Не Huawei"
            fi
        else
            echo "❌ Недоступен"
        fi
    done

    if [ ${#WORKING_WEB_INTERFACES[@]} -eq 0 ]; then
        echo ""
        echo "  ⚠️  Активные веб-интерфейсы не найдены"
        echo "  💡 Возможные причины:"
        echo "    - Модемы в режиме Stick (не HiLink)"
        echo "    - Требуется ручная настройка IP"
        echo "    - SIM-карты не вставлены"
    else
        echo ""
        echo "  ✅ Найдено активных веб-интерфейсов: ${#WORKING_WEB_INTERFACES[@]}"
        for ip in "${!WORKING_WEB_INTERFACES[@]}"; do
            echo "    🌐 $ip - ${WORKING_WEB_INTERFACES[$ip]}"
        done
    fi
else
    echo "⏭️  Настройка веб-интерфейсов пропущена (используйте --with-web для включения)"
fi

echo ""
echo "6. Финальная проверка и тестирование..."

echo "📊 Итоговое состояние всех модемов:"
echo "===================================="

TOTAL_CONFIGURED=0
TOTAL_WORKING=0

for modem_id in "${FOUND_MODEMS[@]}"; do
    echo ""
    echo "📱 $modem_id (${MODEM_NAMES[$modem_id]}):"

    mode="${MODEM_INFO[${modem_id}_mode]}"
    interface="${MODEM_INFO[${modem_id}_interface]}"
    interface_status="${MODEM_INFO[${modem_id}_interface_status]}"

    echo "  🔧 Режим: $mode"

    if [ -n "$interface" ]; then
        echo "  🌐 Интерфейс: $interface"

        # Проверяем текущее состояние интерфейса
        if ip addr show "$interface" 2>/dev/null | grep -q "inet "; then
            ip_address=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
            echo "  📍 IP: $ip_address"

            # Тестируем соединение
            echo -n "  🌍 Тест интернета: "
            if timeout 10 curl -s --interface "$interface" http://httpbin.org/ip >/dev/null 2>&1; then
                external_ip=$(timeout 10 curl -s --interface "$interface" http://httpbin.org/ip 2>/dev/null | grep -o '"origin": "[^"]*"' | cut -d'"' -f4 2>/dev/null)
                if [ -n "$external_ip" ]; then
                    echo "✅ Работает (внешний IP: $external_ip)"
                    TOTAL_WORKING=$((TOTAL_WORKING + 1))
                else
                    echo "✅ Работает"
                    TOTAL_WORKING=$((TOTAL_WORKING + 1))
                fi
            else
                echo "❌ Не работает"
            fi

            TOTAL_CONFIGURED=$((TOTAL_CONFIGURED + 1))
        else
            echo "  📍 IP: не настроен"
            echo "  🌍 Тест интернета: ❌ Недоступен"
        fi
    else
        echo "  🌐 Интерфейс: не найден"
        echo "  📍 IP: недоступен"
        echo "  🌍 Тест интернета: ❌ Недоступен"
    fi

    # Показываем статус настройки
    case "$interface_status" in
        "configured") echo "  ✅ Статус: Полностью настроен" ;;
        "not_configured") echo "  ⚠️  Статус: Требует настройки IP" ;;
        "missing") echo "  ❌ Статус: Интерфейс не найден" ;;
        "manual_required") echo "  🔧 Статус: Требует ручной настройки" ;;
        *) echo "  ❓ Статус: $interface_status" ;;
    esac
done

echo ""
echo "📈 Общая статистика:"
echo "===================="
echo "📱 Всего модемов найдено: ${#FOUND_MODEMS[@]}"
echo "🔧 Модемов настроено: $TOTAL_CONFIGURED"
echo "🌍 Модемов с интернетом: $TOTAL_WORKING"
echo "📦 Модемов требует настройки: $((${#FOUND_MODEMS[@]} - TOTAL_CONFIGURED))"

if [ "$CONFIGURE_WEB_INTERFACE" = true ]; then
    if [ ${#WORKING_WEB_INTERFACES[@]} -gt 0 ]; then
        echo "🌐 Веб-интерфейсов активно: ${#WORKING_WEB_INTERFACES[@]}"
    fi
fi

echo ""
echo "🛠️  Полезная информация:"
echo "========================="

echo "📋 Все сетевые интерфейсы модемов:"
for modem_id in "${FOUND_MODEMS[@]}"; do
    interface="${MODEM_INFO[${modem_id}_interface]}"
    if [ -n "$interface" ]; then
        if ip addr show "$interface" 2>/dev/null | grep -q "inet "; then
            ip_addr=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | head -1)
            echo "  $interface: $ip_addr (${MODEM_NAMES[$modem_id]})"
        else
            echo "  $interface: не настроен (${MODEM_NAMES[$modem_id]})"
        fi
    fi
done

if [ "$CONFIGURE_WEB_INTERFACE" = true ]; then
    if [ ${#WORKING_WEB_INTERFACES[@]} -gt 0 ]; then
        echo ""
        echo "🌐 Веб-интерфейсы модемов:"
        for ip in "${!WORKING_WEB_INTERFACES[@]}"; do
            echo "  http://$ip (${WORKING_WEB_INTERFACES[$ip]})"
        done
    fi
fi

echo ""
echo "🔧 Команды для диагностики:"
echo "==========================="
echo "# Проверка всех USB модемов:"
echo "lsusb | grep 12d1"
echo ""
echo "# Проверка сетевых интерфейсов:"
echo "ip addr show | grep -E 'enx|usb'"
echo ""
echo "# Перезапуск DHCP для интерфейса:"
echo "sudo dhclient <interface_name>"
echo ""
echo "# Проверка интернета через интерфейс:"
echo "curl --interface <interface_name> http://httpbin.org/ip"

if [ $TOTAL_WORKING -eq ${#FOUND_MODEMS[@]} ] && [ $TOTAL_WORKING -gt 0 ]; then
    echo ""
    echo "🎉 Отлично! Все модемы настроены и работают!"
    echo ""
    echo "🚀 Следующие шаги:"
    echo "=================="
    echo "1. Интегрируйте модемы в Mobile Proxy Service"
    echo "2. Настройте автоматическую ротацию IP"
    echo "3. Добавьте мониторинг состояния модемов"
    echo "4. Настройте балансировку нагрузки между модемами"
elif [ $TOTAL_WORKING -gt 0 ]; then
    echo ""
    echo "✅ Часть модемов настроена успешно!"
    echo ""
    echo "⚠️  Для не работающих модемов:"
    echo "=============================="
    echo "1. Проверьте SIM-карты и PIN коды"
    echo "2. Убедитесь в наличии интернет-трафика"
    echo "3. Попробуйте ручную настройку через веб-интерфейс"
    echo "4. Перезапустите скрипт с --with-web"
else
    echo ""
    echo "⚠️  Ни один модем не работает полностью"
    echo ""
    echo "🔧 Рекомендации по устранению проблем:"
    echo "====================================="
    echo "1. Запустите скрипт с --with-web для настройки веб-интерфейсов"
    echo "2. Вставьте SIM-карты с активным интернет-тарифом"
    echo "3. Проверьте PIN коды SIM-карт"
    echo "4. Убедитесь, что модемы не заблокированы оператором"
    echo "5. Попробуйте переподключить модемы к другим USB портам"
fi

echo ""
echo "🏁 Настройка завершена!"
