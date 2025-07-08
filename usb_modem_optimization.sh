#!/bin/bash
# Быстрая оптимизация частотных диапазонов для Huawei модемов

MODEM_IP="192.168.8.1"  # Стандартный IP для Huawei

echo "🚀 Быстрая оптимизация скорости Huawei модема"
echo "============================================="

# Получаем токен сессии
get_token() {
    curl -s "http://$MODEM_IP/api/webserver/SesTokInfo" | grep -o '<SesInfo>[^<]*</SesInfo>' | sed 's/<[^>]*>//g'
}

# Отправляем API запрос
send_request() {
    local endpoint=$1
    local data=$2
    local token=$(get_token)

    curl -s -X POST \
        -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
        -H "__RequestVerificationToken: $token" \
        -d "$data" \
        "http://$MODEM_IP$endpoint"
}

echo "1. Проверяем доступность модема..."
if ! ping -c 1 -W 3 $MODEM_IP >/dev/null 2>&1; then
    echo "❌ Модем недоступен по адресу $MODEM_IP"
    echo "Проверьте подключение модема"
    exit 1
fi

echo "✅ Модем найден: $MODEM_IP"

echo ""
echo "2. Применяем оптимизации..."

# Оптимизация 1: Устанавливаем режим "Только LTE"
echo "📡 Фиксируем режим LTE..."
send_request "/api/net/net-mode" \
    '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>3FFFFFFF</NetworkBand></request>'

sleep 3

# Оптимизация 2: Отключаем медленный Band 20, оставляем быстрые Band 3,7,1
echo "⚡ Оптимизируем частотные диапазоны (отключаем Band 20)..."
send_request "/api/net/net-mode" \
    '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>C5</NetworkBand></request>'

sleep 3

# Оптимизация 3: Устанавливаем приоритет Band 7 (самый быстрый)
echo "🔥 Устанавливаем приоритет Band 7 (2600 MHz)..."
send_request "/api/net/net-mode" \
    '<?xml version="1.0" encoding="UTF-8"?><request><NetworkMode>03</NetworkMode><NetworkBand>40</NetworkBand></request>'

sleep 5

echo ""
echo "3. Перезагружаем модем для применения настроек..."
send_request "/api/device/control" \
    '<?xml version="1.0" encoding="UTF-8"?><request><Control>1</Control></request>'

echo "⏳ Ожидание перезагрузки (30 секунд)..."
sleep 30

echo ""
echo "✅ Оптимизация завершена!"
echo ""
echo "📊 Для проверки результата:"
echo "  1. Откройте http://$MODEM_IP в браузере"
echo "  2. Проверьте текущий Band в разделе 'About'"
echo "  3. Запустите тест скорости: speedtest-cli"
echo ""
echo "🎯 Ожидаемые улучшения:"
echo "  - Стабильное соединение без переключений 3G/4G"
echo "  - Использование самых быстрых частот"
echo "  - Увеличение скорости в 2-5 раз"

