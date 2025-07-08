#!/bin/bash
# Универсальный скрипт настройки устройств для Mobile Proxy Service
# Автоматически обнаруживает и настраивает Android устройства, USB модемы и другие устройства

set -e

# Конфигурация
PROXY_PORT="${PROXY_PORT:-8080}"
CONFIG_DIR="/var/lib/mobile-proxy"
LOG_FILE="/var/log/mobile-proxy-setup.log"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции логирования
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $1${NC}" | tee -a "$LOG_FILE"
}

# Функция проверки зависимостей
check_dependencies() {
    log "Проверка зависимостей..."

    local missing_deps=()

    # Проверяем наличие необходимых команд
    command -v ip >/dev/null 2>&1 || missing_deps+=("iproute2")
    command -v iptables >/dev/null 2>&1 || missing_deps+=("iptables")
    command -v dhclient >/dev/null 2>&1 || missing_deps+=("isc-dhcp-client")
    command -v lsusb >/dev/null 2>&1 || missing_deps+=("usbutils")

    # ADB нужен только если есть Android устройства
    if lsusb | grep -qi "android\|samsung\|huawei\|xiaomi\|honor\|oneplus"; then
        command -v adb >/dev/null 2>&1 || missing_deps+=("android-tools-adb")
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        warn "Отсутствуют зависимости: ${missing_deps[*]}"
        info "Установка зависимостей..."
        sudo apt update
        sudo apt install -y "${missing_deps[@]}"
    fi

    log "✅ Все зависимости установлены"
}

# Функция создания директорий
setup_directories() {
    log "Создание директорий конфигурации..."

    sudo mkdir -p "$CONFIG_DIR"
    sudo mkdir -p "$(dirname "$LOG_FILE")"
    sudo touch "$LOG_FILE"
    sudo chmod 666 "$LOG_FILE"

    log "✅ Директории созданы"
}

# Функция обнаружения Android устройств
discover_android_devices() {
    log "Обнаружение Android устройств..."

    local android_devices=()

    # Проверяем ADB
    if ! command -v adb >/dev/null 2>&1; then
        warn "ADB не установлен, пропускаем Android устройства"
        return 0
    fi

    # Получаем список устройств
    local adb_output
    adb_output=$(adb devices 2>/dev/null | grep -E "device$" | awk '{print $1}' || true)

    if [ -z "$adb_output" ]; then
        info "Android устройства не найдены через ADB"
        return 0
    fi

    while IFS= read -r device_id; do
        if [ -n "$device_id" ]; then
            info "Найдено Android устройство: $device_id"

            # Получаем информацию об устройстве
            local model manufacturer
            model=$(adb -s "$device_id" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || echo "Unknown")
            manufacturer=$(adb -s "$device_id" shell getprop ro.product.manufacturer 2>/dev/null | tr -d '\r' || echo "Unknown")

            android_devices+=("$device_id:$manufacturer:$model")

            info "  Модель: $manufacturer $model"
        fi
    done <<< "$adb_output"

    if [ ${#android_devices[@]} -gt 0 ]; then
        log "✅ Найдено Android устройств: ${#android_devices[@]}"
        printf '%s\n' "${android_devices[@]}" > "$CONFIG_DIR/android_devices.list"
    fi
}

# Функция обнаружения USB модемов
discover_usb_modems() {
    log "Обнаружение USB модемов..."

    local usb_modems=()

    # Ищем известных производителей модемов
    local modem_vendors=("12d1" "19d2" "1e0e" "2c7c" "05c6")

    for vendor in "${modem_vendors[@]}"; do
        local devices
        devices=$(lsusb | grep "$vendor" || true)

        if [ -n "$devices" ]; then
            while IFS= read -r line; do
                local bus_device vendor_product description
                bus_device=$(echo "$line" | awk '{print $2":"$4}' | tr -d ':')
                vendor_product=$(echo "$line" | awk '{print $6}')
                description=$(echo "$line" | cut -d' ' -f7-)

                usb_modems+=("$bus_device:$vendor_product:$description")
                info "Найден USB модем: $description ($vendor_product)"
            done <<< "$devices"
        fi
    done

    # Поиск serial портов
    for port in /dev/ttyUSB* /dev/ttyACM*; do
        if [ -e "$port" ]; then
            info "Найден serial порт: $port"
            usb_modems+=("$port:serial:USB Serial Port")
        fi
    done

    if [ ${#usb_modems[@]} -gt 0 ]; then
        log "✅ Найдено USB модемов/портов: ${#usb_modems[@]}"
        printf '%s\n' "${usb_modems[@]}" > "$CONFIG_DIR/usb_modems.list"
    fi
}

# Функция настройки Android устройства
setup_android_device() {
    local device_id="$1"
    local manufacturer="$2"
    local model="$3"

    log "Настройка Android устройства: $device_id ($manufacturer $model)"

    # Проверяем подключение
    if ! adb devices | grep -q "$device_id.*device"; then
        error "Устройство $device_id недоступно"
        return 1
    fi

    # Включаем USB tethering
    info "Включение USB tethering..."
    adb -s "$device_id" shell svc usb setFunctions rndis 2>/dev/null || true

    # Ждем появления интерфейса
    local interface=""
    local attempts=0
    while [ $attempts -lt 30 ]; do
        interface=$(ip link show | grep -E "enx[a-f0-9]{12}" | head -1 | cut -d: -f2 | tr -d ' ' || true)

        if [ -n "$interface" ]; then
            break
        fi

        sleep 2
        ((attempts++))
    done

    if [ -z "$interface" ]; then
        warn "USB интерфейс не появился для $device_id"
        return 1
    fi

    info "Найден USB интерфейс: $interface"

    # Настраиваем интерфейс
    setup_usb_interface "$interface" "$device_id"

    # Создаем конфигурацию для устройства
    create_device_config "$device_id" "android" "$interface" "$manufacturer $model"

    # Создаем скрипты ротации
    create_rotation_scripts "$device_id" "android" "$interface"

    log "✅ Android устройство $device_id настроено"
}

# Функция настройки USB интерфейса
setup_usb_interface() {
    local interface="$1"
    local device_id="$2"

    info "Настройка USB интерфейса $interface..."

    # Поднимаем интерфейс
    sudo ip link set "$interface" up
    sleep 2

    # Получаем IP через DHCP
    info "Получение IP адреса через DHCP..."
    sudo dhclient "$interface" 2>/dev/null || {
        warn "DHCP не сработал, пробуем статическую конфигурацию..."
        sudo ip addr add 192.168.42.100/24 dev "$interface" 2>/dev/null || true
    }

    sleep 3

    # Проверяем IP
    local ip_addr
    ip_addr=$(ip addr show "$interface" | grep "inet " | awk '{print $2}' | cut -d/ -f1 || true)

    if [ -n "$ip_addr" ]; then
        info "IP адрес интерфейса $interface: $ip_addr"

        # Тестируем интернет
        if curl --interface "$interface" -s --connect-timeout 10 https://httpbin.org/ip | grep -q origin; then
            log "✅ Интернет через $interface работает"
            return 0
        else
            warn "Нет интернета через $interface"
        fi
    else
        warn "Не удалось получить IP для $interface"
    fi

    return 1
}

# Функция создания конфигурации устройства
create_device_config() {
    local device_id="$1"
    local device_type="$2"
    local interface="$3"
    local description="$4"

    local config_file="$CONFIG_DIR/device_${device_id}.conf"

    cat > "$config_file" << EOF
# Конфигурация устройства $device_id
DEVICE_ID="$device_id"
DEVICE_TYPE="$device_type"
INTERFACE="$interface"
DESCRIPTION="$description"
PROXY_PORT="$PROXY_PORT"
ROTATION_INTERVAL="600"
CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Маршрутизация
ROUTING_TABLE="device_${device_id//-/_}_table"
ROUTING_TABLE_ID="$((200 + RANDOM % 50))"

# IP адрес интерфейса
IP_ADDRESS="$(ip addr show "$interface" 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1 || echo "unknown")"

# Gateway
GATEWAY="$(ip route show dev "$interface" 2>/dev/null | grep default | awk '{print $3}' || echo "unknown")"
EOF

    info "Создана конфигурация: $config_file"
}

# Функция создания скриптов ротации
create_rotation_scripts() {
    local device_id="$1"
    local device_type="$2"
    local interface="$3"

    local script_dir="$CONFIG_DIR/scripts"
    sudo mkdir -p "$script_dir"

    # Скрипт ротации IP
    local rotation_script="$script_dir/rotate_${device_id}.sh"

    cat > "$rotation_script" << EOF
#!/bin/bash
# Скрипт ротации IP для устройства $device_id

set -e

DEVICE_ID="$device_id"
DEVICE_TYPE="$device_type"
INTERFACE="$interface"

# Загружаем конфигурацию
source "$CONFIG_DIR/device_${device_id}.conf"

log_rotation() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] \$1" >> "/var/log/rotation_${device_id}.log"
}

rotate_ip() {
    log_rotation "Начало ротации IP для \$DEVICE_ID"

    # Получаем текущий IP
    CURRENT_IP=\$(curl --interface "\$INTERFACE" -s --connect-timeout 5 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"' || echo "unknown")
    log_rotation "Текущий IP: \$CURRENT_IP"

    case "\$DEVICE_TYPE" in
        "android")
            # Ротация для Android
            adb -s "\$DEVICE_ID" shell svc data disable
            sleep 8
            adb -s "\$DEVICE_ID" shell svc data enable
            sleep 20
            ;;
        "usb_modem")
            # Ротация для USB модема через AT команды
            echo "AT+CFUN=0" > "\$INTERFACE"
            sleep 5
            echo "AT+CFUN=1" > "\$INTERFACE"
            sleep 15
            ;;
        *)
            log_rotation "Неизвестный тип устройства: \$DEVICE_TYPE"
            exit 1
            ;;
    esac

    # Проверяем новый IP
    sleep 10
    NEW_IP=\$(curl --interface "\$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"' || echo "unknown")
    log_rotation "Новый IP: \$NEW_IP"

    if [ "\$CURRENT_IP" != "\$NEW_IP" ] && [ "\$NEW_IP" != "unknown" ]; then
        log_rotation "✅ IP успешно изменен с \$CURRENT_IP на \$NEW_IP"
        exit 0
    else
        log_rotation "⚠️ IP может не измениться"
        exit 1
    fi
}

# Запуск ротации
rotate_ip
EOF

    chmod +x "$rotation_script"
    info "Создан скрипт ротации: $rotation_script"

    # Скрипт перезапуска устройства
    local restart_script="$script_dir/restart_${device_id}.sh"

    cat > "$restart_script" << EOF
#!/bin/bash
# Скрипт перезапуска устройства $device_id

set -e

# Загружаем конфигурацию
source "$CONFIG_DIR/device_${device_id}.conf"

echo "Перезапуск устройства \$DEVICE_ID..."

# Отключаем интерфейс
sudo ip link set "\$INTERFACE" down

case "\$DEVICE_TYPE" in
    "android")
        # Перезапуск USB tethering
        adb -s "\$DEVICE_ID" shell svc usb setFunctions none
        sleep 5
        adb -s "\$DEVICE_ID" shell svc usb setFunctions rndis
        sleep 10
        ;;
    "usb_modem")
        # Перезапуск модема
        echo "AT+CFUN=0" > "\$INTERFACE"
        sleep 5
        echo "AT+CFUN=1" > "\$INTERFACE"
        sleep 10
        ;;
esac

# Поднимаем интерфейс
sudo ip link set "\$INTERFACE" up
sleep 3

# Обновляем IP
sudo dhclient "\$INTERFACE" 2>/dev/null || true

echo "✅ Устройство \$DEVICE_ID перезапущено"
EOF

    chmod +x "$restart_script"
    info "Создан скрипт перезапуска: $restart_script"
}

# Функция настройки маршрутизации
setup_routing() {
    log "Настройка маршрутизации для всех устройств..."

    # Включаем IP forwarding
    sudo sysctl -w net.ipv4.ip_forward=1
    echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf >/dev/null

    # Настраиваем каждое устройство
    for config_file in "$CONFIG_DIR"/device_*.conf; do
        if [ -f "$config_file" ]; then
            source "$config_file"

            if [ -n "$INTERFACE" ] && [ -n "$IP_ADDRESS" ] && [ "$IP_ADDRESS" != "unknown" ]; then
                setup_device_routing "$DEVICE_ID" "$INTERFACE" "$IP_ADDRESS" "$GATEWAY" "$ROUTING_TABLE" "$ROUTING_TABLE_ID"
            fi
        fi
    done

    log "✅ Маршрутизация настроена"
}

# Функция настройки маршрутизации для устройства
setup_device_routing() {
    local device_id="$1"
    local interface="$2"
    local ip_address="$3"
    local gateway="$4"
    local routing_table="$5"
    local routing_table_id="$6"

    info "Настройка маршрутизации для $device_id ($interface)"

    # Добавляем таблицу маршрутизации
    if ! grep -q "$routing_table" /etc/iproute2/rt_tables 2>/dev/null; then
        echo "$routing_table_id $routing_table" | sudo tee -a /etc/iproute2/rt_tables
    fi

    # Очищаем старые маршруты
    sudo ip route flush table "$routing_table" 2>/dev/null || true
    sudo ip rule del from "$ip_address" table "$routing_table" 2>/dev/null || true

    # Добавляем маршруты
    if [ -n "$gateway" ] && [ "$gateway" != "unknown" ]; then
        sudo ip route add default via "$gateway" dev "$interface" table "$routing_table"
    fi
    sudo ip route add "$ip_address/24" dev "$interface" scope link table "$routing_table"

    # Добавляем правила
    sudo ip rule add from "$ip_address" table "$routing_table"

    # Настраиваем NAT
    sudo iptables -t nat -A POSTROUTING -o "$interface" -j MASQUERADE 2>/dev/null || true

    info "✅ Маршрутизация для $device_id настроена"
}

# Функция создания сводки
create_summary() {
    log "Создание сводки настроенных устройств..."

    local summary_file="$CONFIG_DIR/devices_summary.txt"

    cat > "$summary_file" << EOF
# Сводка настроенных устройств
# Создано: $(date)

EOF

    local device_count=0
    for config_file in "$CONFIG_DIR"/device_*.conf; do
        if [ -f "$config_file" ]; then
            source "$config_file"
            ((device_count++))

            cat >> "$summary_file" << EOF
Устройство #$device_count:
  ID: $DEVICE_ID
  Тип: $DEVICE_TYPE
  Интерфейс: $INTERFACE
  IP: $IP_ADDRESS
  Описание: $DESCRIPTION
  Скрипт ротации: $CONFIG_DIR/scripts/rotate_${DEVICE_ID}.sh
  Скрипт перезапуска: $CONFIG_DIR/scripts/restart_${DEVICE_ID}.sh

EOF
        fi
    done

    echo "Всего настроено устройств: $device_count" >> "$summary_file"

    log "✅ Сводка создана: $summary_file"
    cat "$summary_file"
}

# Основная функция
main() {
    log "🚀 Запуск универсального скрипта настройки устройств"

    # Проверки
    if [ "$EUID" -eq 0 ]; then
        error "Не запускайте скрипт от root! Используйте sudo только когда нужно."
        exit 1
    fi

    # Этапы настройки
    check_dependencies
    setup_directories
    discover_android_devices
    discover_usb_modems

    # Настройка найденных устройств
    if [ -f "$CONFIG_DIR/android_devices.list" ]; then
        while IFS=':' read -r device_id manufacturer model; do
            setup_android_device "$device_id" "$manufacturer" "$model"
        done < "$CONFIG_DIR/android_devices.list"
    fi

    # Настройка маршрутизации
    setup_routing

    # Создание сводки
    create_summary

    log "🎉 Настройка завершена! Все устройства готовы к работе."
    log "📁 Конфигурация сохранена в: $CONFIG_DIR"
    log "📜 Логи доступны в: $LOG_FILE"
}

# Запуск скрипта
main "$@"
