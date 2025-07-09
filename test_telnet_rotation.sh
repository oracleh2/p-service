#!/bin/bash

# Тестирование telnet ротации для Huawei модема
MODEM_IP="192.168.108.1"
INTERFACE="enx0c5b8f279a64"

echo "🔍 Тестирование Telnet ротации для модема $MODEM_IP"
echo "================================================="

# Проверяем доступность telnet
echo "1. Проверка доступности Telnet..."
if ! timeout 3 nc -z "$MODEM_IP" 23; then
    echo "❌ Telnet недоступен на порту 23"
    exit 1
fi
echo "✅ Telnet доступен"

# Получаем текущий внешний IP
echo ""
echo "2. Получение текущего внешнего IP..."
CURRENT_IP=$(curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"')
echo "Текущий внешний IP: $CURRENT_IP"

# Функция для telnet команд
execute_telnet_commands() {
    local username="$1"
    local password="$2"
    local commands="$3"

    echo "Попытка подключения с учетными данными: $username:$password"

    {
        sleep 1
        echo "$username"
        sleep 1
        echo "$password"
        sleep 2
        echo "$commands"
        sleep 5
        echo "exit"
    } | timeout 30 telnet "$MODEM_IP" 2>/dev/null
}

# Пробуем разные учетные данные
echo ""
echo "3. Попытка подключения через Telnet..."

CREDENTIALS=(
    "admin:admin"
    "root:admin"
    "root:root"
    "user:user"
    "::"  # пустые
)

for cred in "${CREDENTIALS[@]}"; do
    IFS=':' read -r username password <<< "$cred"

    echo ""
    echo "🔐 Тестирование: $username:$password"

    # Сначала простая проверка подключения
    result=$(execute_telnet_commands "$username" "$password" "whoami; pwd; ls -la")

    if echo "$result" | grep -q "root\|admin\|#"; then
        echo "✅ Успешное подключение!"
        echo "Результат:"
        echo "$result"

        # Если подключение успешно, пробуем команды ротации
        echo ""
        echo "4. Выполнение команд ротации..."

        # Метод 1: dhclient
        echo "Метод 1: dhclient"
        rotation_result=$(execute_telnet_commands "$username" "$password" "dhclient -r; sleep 3; dhclient; sleep 5; ifconfig")
        echo "Результат dhclient:"
        echo "$rotation_result"

        # Метод 2: network restart
        echo ""
        echo "Метод 2: network restart"
        network_result=$(execute_telnet_commands "$username" "$password" "/etc/init.d/network restart; sleep 10; ifconfig")
        echo "Результат network restart:"
        echo "$network_result"

        # Проверяем новый IP
        echo ""
        echo "5. Проверка нового внешнего IP..."
        sleep 15
        NEW_IP=$(curl --interface "$INTERFACE" -s --connect-timeout 10 https://httpbin.org/ip 2>/dev/null | grep -o '"[0-9.]*"' | tr -d '"')
        echo "Новый внешний IP: $NEW_IP"

        if [ "$CURRENT_IP" != "$NEW_IP" ] && [ "$NEW_IP" != "" ]; then
            echo "🎉 УСПЕХ! IP изменен с $CURRENT_IP на $NEW_IP"
        else
            echo "⚠️ IP не изменился или не определен"
        fi

        break
    else
        echo "❌ Подключение не удалось"
    fi
done

echo ""
echo "📋 Резюме:"
echo "- Исходный IP: $CURRENT_IP"
echo "- Новый IP: $NEW_IP"
echo "- Результат: $([ "$CURRENT_IP" != "$NEW_IP" ] && echo "IP изменен" || echo "IP не изменился")"
echo ""
echo "💡 Если telnet не работает, попробуйте:"
echo "1. Проверить SSH: ssh root@$MODEM_IP"
echo "2. Найти другие открытые порты: nmap $MODEM_IP"
echo "3. Использовать веб-интерфейс для включения telnet"

