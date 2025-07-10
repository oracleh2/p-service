#!/bin/bash
# setup_usb_rotation.sh - Настройка системы для USB ротации модемов E3372h

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}🔧 Настройка системы для USB ротации модемов E3372h${NC}"
echo "================================================================"

# Проверка прав пользователя
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  Скрипт запущен от root. Рекомендуется запуск от обычного пользователя.${NC}"
fi

# Функция для проверки команды
check_command() {
    if command -v "$1" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ $1 найден${NC}"
        return 0
    else
        echo -e "${RED}❌ $1 не найден${NC}"
        return 1
    fi
}

# Функция для установки пакетов
install_packages() {
    echo -e "${BLUE}📦 Установка необходимых пакетов...${NC}"

    if [ -f /etc/debian_version ]; then
        # Debian/Ubuntu
        echo "Обнаружена система Debian/Ubuntu"
        sudo apt-get update
        sudo apt-get install -y curl lsusb usbutils findutils sudo
    elif [ -f /etc/redhat-release ]; then
        # Red Hat/CentOS/Fedora
        echo "Обнаружена система Red Hat/CentOS/Fedora"
        sudo yum install -y curl usbutils findutils sudo
    elif [ -f /etc/arch-release ]; then
        # Arch Linux
        echo "Обнаружена система Arch Linux"
        sudo pacman -S --noconfirm curl usbutils findutils sudo
    else
        echo -e "${YELLOW}⚠️  Неизвестная система. Убедитесь, что установлены: curl, lsusb, usbutils, findutils${NC}"
    fi
}

# Функция для настройки sudo
setup_sudo() {
    echo -e "${BLUE}🔐 Настройка sudo для USB ротации...${NC}"

    local username=$(whoami)
    local sudoers_file="/etc/sudoers.d/usb-rotation"

    echo "Создание правил sudo для пользователя: $username"

    # Создаем файл с правилами sudo
    sudo tee "$sudoers_file" > /dev/null << EOF
# Правила sudo для USB ротации модемов E3372h
# Пользователь: $username
# Создано: $(date)

# Разрешаем запись в файлы authorized для USB устройств
$username ALL=(root) NOPASSWD: /usr/bin/tee /sys/bus/usb/devices/*/authorized

# Разрешаем выполнение echo для USB устройств
$username ALL=(root) NOPASSWD: /bin/echo

# Разрешаем выполнение команд для тестирования
$username ALL=(root) NOPASSWD: /usr/bin/find /sys/bus/usb/devices/ -name idVendor -exec /bin/grep -l 12d1 {} \;
$username ALL=(root) NOPASSWD: /usr/bin/test -f /sys/bus/usb/devices/*/authorized
EOF

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Файл sudo создан: $sudoers_file${NC}"

        # Проверяем синтаксис
        sudo visudo -c -f "$sudoers_file"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ Синтаксис sudo файла корректен${NC}"
        else
            echo -e "${RED}❌ Ошибка в синтаксисе sudo файла${NC}"
            sudo rm -f "$sudoers_file"
            return 1
        fi
    else
        echo -e "${RED}❌ Не удалось создать файл sudo${NC}"
        return 1
    fi
}

# Функция для настройки udev правил
setup_udev() {
    echo -e "${BLUE}🔧 Настройка udev правил для модемов Huawei...${NC}"

    local udev_file="/etc/udev/rules.d/99-huawei-modems.rules"

    # Создаем udev правила
    sudo tee "$udev_file" > /dev/null << 'EOF'
# Udev правила для модемов Huawei E3372h
# Позволяют пользователям управлять USB устройствами Huawei

# Huawei модемы (VID: 12d1)
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", MODE="0664", GROUP="dialout"

# Разрешения на sysfs для authorized файлов
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", RUN+="/bin/chmod 664 /sys%p/authorized"

# Дополнительные разрешения для конкретных моделей
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", ATTRS{idProduct}=="14dc", MODE="0664", GROUP="dialout"
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", ATTRS{idProduct}=="1f01", MODE="0664", GROUP="dialout"
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", ATTRS{idProduct}=="157d", MODE="0664", GROUP="dialout"
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", ATTRS{idProduct}=="14db", MODE="0664", GROUP="dialout"
EOF

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Udev правила созданы: $udev_file${NC}"

        # Перезагружаем udev правила
        sudo udevadm control --reload-rules
        sudo udevadm trigger

        echo -e "${GREEN}✅ Udev правила перезагружены${NC}"
    else
        echo -e "${RED}❌ Не удалось создать udev правила${NC}"
        return 1
    fi
}

# Функция для добавления пользователя в группы
setup_groups() {
    echo -e "${BLUE}👥 Настройка групп пользователей...${NC}"

    local username=$(whoami)

    # Добавляем пользователя в группы dialout и plugdev
    sudo usermod -a -G dialout "$username"
    sudo usermod -a -G plugdev "$username"

    echo -e "${GREEN}✅ Пользователь $username добавлен в группы: dialout, plugdev${NC}"
    echo -e "${YELLOW}⚠️  Может потребоваться перелогин для применения изменений групп${NC}"
}

# Функция для создания вспомогательных скриптов
create_helper_scripts() {
    echo -e "${BLUE}📝 Создание вспомогательных скриптов...${NC}"

    local scripts_dir="$HOME/.local/bin"
    mkdir -p "$scripts_dir"

    # Скрипт для проверки USB устройств
    cat > "$scripts_dir/check-usb-modems.sh" << 'EOF'
#!/bin/bash
# Проверка USB модемов Huawei

echo "🔍 Поиск USB модемов Huawei..."
echo "=============================="

# Поиск через lsusb
echo "1. Поиск через lsusb:"
lsusb | grep -i huawei | while read line; do
    echo "   📱 $line"
done

echo ""

# Поиск через sysfs
echo "2. Поиск через sysfs:"
find /sys/bus/usb/devices/ -name idVendor -exec grep -l 12d1 {} \; 2>/dev/null | while read vendor_file; do
    device_path=$(dirname "$vendor_file")
    device_name=$(basename "$device_path")

    if [ -f "$device_path/idProduct" ]; then
        product_id=$(cat "$device_path/idProduct")
        echo "   🔧 Устройство: $device_name (12d1:$product_id)"

        if [ -f "$device_path/authorized" ]; then
            auth_status=$(cat "$device_path/authorized")
            echo "      Авторизация: $auth_status"
            echo "      Файл: $device_path/authorized"
        fi
    fi
done

echo ""

# Поиск сетевых интерфейсов
echo "3. USB сетевые интерфейсы:"
ip link show | grep -E "enx[a-f0-9]{12}" | while read line; do
    interface=$(echo "$line" | cut -d: -f2 | tr -d ' ')
    state=$(echo "$line" | grep -o "state [A-Z]*" | cut -d' ' -f2)
    echo "   🔗 $interface ($state)"

    # Получаем IP если есть
    ip_addr=$(ip addr show "$interface" 2>/dev/null | grep "inet " | awk '{print $2}' | head -1)
    if [ -n "$ip_addr" ]; then
        echo "      IP: $ip_addr"
    fi
done
EOF

    chmod +x "$scripts_dir/check-usb-modems.sh"

    # Скрипт для быстрого тестирования
    cat > "$scripts_dir/test-usb-rotation.sh" << 'EOF'
#!/bin/bash
# Быстрое тестирование USB ротации

echo "🧪 Быстрое тестирование USB ротации"
echo "===================================="

# Проверка sudo
echo "1. Проверка sudo..."
if sudo -n echo "test" >/dev/null 2>&1; then
    echo "   ✅ Sudo работает"
else
    echo "   ❌ Sudo не настроен"
    exit 1
fi

# Проверка USB устройств
echo "2. Проверка USB устройств..."
usb_count=$(lsusb | grep -c "12d1.*Huawei")
if [ "$usb_count" -gt 0 ]; then
    echo "   ✅ Найдено USB устройств Huawei: $usb_count"
else
    echo "   ❌ USB устройства Huawei не найдены"
    exit 1
fi

# Проверка sysfs
echo "3. Проверка sysfs..."
sysfs_count=$(find /sys/bus/usb/devices/ -name idVendor -exec grep -l 12d1 {} \; 2>/dev/null | wc -l)
if [ "$sysfs_count" -gt 0 ]; then
    echo "   ✅ Найдено устройств в sysfs: $sysfs_count"
else
    echo "   ❌ Устройства в sysfs не найдены"
    exit 1
fi

# Проверка authorized файлов
echo "4. Проверка authorized файлов..."
auth_files=$(find /sys/bus/usb/devices/ -name idVendor -exec grep -l 12d1 {} \; 2>/dev/null | while read vendor_file; do
    device_path=$(dirname "$vendor_file")
    auth_file="$device_path/authorized"
    if [ -f "$auth_file" ]; then
        echo "$auth_file"
    fi
done)

auth_count=$(echo "$auth_files" | wc -l)
if [ "$auth_count" -gt 0 ]; then
    echo "   ✅ Найдено authorized файлов: $auth_count"
else
    echo "   ❌ Authorized файлы не найдены"
    exit 1
fi

echo ""
echo "🎉 Все проверки пройдены успешно!"
echo "💡 Система готова к USB ротации"
EOF

    chmod +x "$scripts_dir/test-usb-rotation.sh"

    echo -e "${GREEN}✅ Вспомогательные скрипты созданы в: $scripts_dir${NC}"
    echo -e "${CYAN}   📝 check-usb-modems.sh - проверка USB устройств${NC}"
    echo -e "${CYAN}   🧪 test-usb-rotation.sh - быстрое тестирование${NC}"

    # Добавляем в PATH если нужно
    if [[ ":$PATH:" != *":$scripts_dir:"* ]]; then
        echo -e "${YELLOW}💡 Добавьте $scripts_dir в PATH для удобства использования${NC}"
        echo -e "${YELLOW}   Добавьте в ~/.bashrc: export PATH=\"\$PATH:$scripts_dir\"${NC}"
    fi
}

# Функция для финальной проверки
final_check() {
    echo -e "${BLUE}🔍 Финальная проверка настроек...${NC}"

    local errors=0

    # Проверка команд
    echo "1. Проверка необходимых команд:"
    for cmd in curl lsusb find sudo; do
        if check_command "$cmd"; then
            true
        else
            ((errors++))
        fi
    done

    # Проверка sudo
    echo "2. Проверка sudo:"
    if sudo -n echo "test" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Sudo работает без пароля${NC}"
    else
        echo -e "${RED}❌ Sudo не настроен${NC}"
        ((errors++))
    fi

    # Проверка USB устройств
    echo "3. Проверка USB устройств:"
    usb_count=$(lsusb | grep -c "12d1.*Huawei" || echo "0")
    if [ "$usb_count" -gt 0 ]; then
        echo -e "${GREEN}✅ Найдено USB устройств Huawei: $usb_count${NC}"
    else
        echo -e "${YELLOW}⚠️  USB устройства Huawei не найдены (возможно не подключены)${NC}"
    fi

    # Проверка групп
    echo "4. Проверка групп пользователя:"
    if groups | grep -q dialout; then
        echo -e "${GREEN}✅ Пользователь в группе dialout${NC}"
    else
        echo -e "${YELLOW}⚠️  Пользователь не в группе dialout${NC}"
    fi

    # Проверка файлов
    echo "5. Проверка созданных файлов:"
    if [ -f "/etc/sudoers.d/usb-rotation" ]; then
        echo -e "${GREEN}✅ Файл sudo создан${NC}"
    else
        echo -e "${RED}❌ Файл sudo не создан${NC}"
        ((errors++))
    fi

    if [ -f "/etc/udev/rules.d/99-huawei-modems.rules" ]; then
        echo -e "${GREEN}✅ Udev правила созданы${NC}"
    else
        echo -e "${RED}❌ Udev правила не созданы${NC}"
        ((errors++))
    fi

    echo ""
    if [ $errors -eq 0 ]; then
        echo -e "${GREEN}🎉 Все проверки пройдены успешно!${NC}"
        echo -e "${GREEN}✅ Система готова к использованию USB ротации${NC}"
        return 0
    else
        echo -e "${RED}❌ Обнаружено ошибок: $errors${NC}"
        echo -e "${RED}🔧 Исправьте ошибки и повторите настройку${NC}"
        return 1
    fi
}

# Основная функция
main() {
    echo -e "${CYAN}Начинаем настройку системы...${NC}"
    echo ""

    # Проверка и установка пакетов
    echo -e "${BLUE}Этап 1: Проверка и установка пакетов${NC}"
    install_packages
    echo ""

    # Настройка sudo
    echo -e "${BLUE}Этап 2: Настройка sudo${NC}"
    setup_sudo
    echo ""

    # Настройка udev
    echo -e "${BLUE}Этап 3: Настройка udev${NC}"
    setup_udev
    echo ""

    # Настройка групп
    echo -e "${BLUE}Этап 4: Настройка групп${NC}"
    setup_groups
    echo ""

    # Создание вспомогательных скриптов
    echo -e "${BLUE}Этап 5: Создание вспомогательных скриптов${NC}"
    create_helper_scripts
    echo ""

    # Финальная проверка
    echo -e "${BLUE}Этап 6: Финальная проверка${NC}"
    if final_check; then
        echo ""
        echo -e "${GREEN}🎉 НАСТРОЙКА УСПЕШНО ЗАВЕРШЕНА!${NC}"
        echo ""
        echo -e "${CYAN}📋 Следующие шаги:${NC}"
        echo -e "${CYAN}1. Перелогиньтесь для применения изменений групп${NC}"
        echo -e "${CYAN}2. Подключите модем Huawei E3372h${NC}"
        echo -e "${CYAN}3. Запустите тестирование: python3 test_usb_rotation.py${NC}"
        echo -e "${CYAN}4. Или используйте быстрый тест: ~/.local/bin/test-usb-rotation.sh${NC}"
        echo ""
        echo -e "${GREEN}✅ Система готова к использованию USB ротации!${NC}"
        return 0
    else
        echo ""
        echo -e "${RED}❌ НАСТРОЙКА НЕ ЗАВЕРШЕНА${NC}"
        echo -e "${RED}🔧 Исправьте обнаруженные проблемы и повторите${NC}"
        return 1
    fi
}

# Обработка аргументов
case "${1:-}" in
    --help|-h)
        echo "Использование: $0 [опции]"
        echo ""
        echo "Опции:"
        echo "  --help, -h     Показать эту справку"
        echo "  --check        Только проверить текущие настройки"
        echo "  --uninstall    Удалить созданные файлы"
        echo ""
        echo "Этот скрипт настраивает систему для USB ротации модемов Huawei E3372h."
        echo "Он создает необходимые sudo правила, udev правила и вспомогательные скрипты."
        exit 0
        ;;
    --check)
        echo -e "${CYAN}🔍 Проверка текущих настроек...${NC}"
        final_check
        exit $?
        ;;
    --uninstall)
        echo -e "${YELLOW}🗑️  Удаление настроек USB ротации...${NC}"

        # Удаляем созданные файлы
        sudo rm -f /etc/sudoers.d/usb-rotation
        sudo rm -f /etc/udev/rules.d/99-huawei-modems.rules
        rm -f ~/.local/bin/check-usb-modems.sh
        rm -f ~/.local/bin/test-usb-rotation.sh

        # Перезагружаем udev
        sudo udevadm control --reload-rules
        sudo udevadm trigger

        echo -e "${GREEN}✅ Настройки удалены${NC}"
        exit 0
        ;;
    "")
        # Запуск основной функции
        main
        exit $?
        ;;
    *)
        echo -e "${RED}❌ Неизвестная опция: $1${NC}"
        echo "Используйте --help для справки"
        exit 1
        ;;
esac
