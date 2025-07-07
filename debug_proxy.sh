#!/bin/bash
# debug_proxy.sh - Полная диагностика dedicated proxy сервера

echo "🔍 DEDICATED PROXY DIAGNOSTIC SCRIPT"
echo "===================================="
date
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Функция для цветного вывода
log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_debug() { echo -e "${PURPLE}🐛 $1${NC}"; }
log_test() { echo -e "${CYAN}🧪 $1${NC}"; }

# Настройки
PROXY_HOST="192.168.1.50"
PROXY_PORT="6001"
USERNAME="device_android_"
PASSWORD="9xliPbsP-VtHPkYH45QX0g"
API_HOST="192.168.1.50"
API_PORT="8000"

echo "📋 Configuration:"
echo "   Proxy: $PROXY_HOST:$PROXY_PORT"
echo "   Username: $USERNAME"
echo "   Password: $PASSWORD"
echo "   API: $API_HOST:$API_PORT"
echo ""

# 1. Проверка сетевого подключения
log_info "1. Checking network connectivity..."
ping -c 1 $PROXY_HOST &>/dev/null
if [ $? -eq 0 ]; then
    log_success "Host $PROXY_HOST is reachable"
else
    log_error "Host $PROXY_HOST is NOT reachable"
    exit 1
fi

# 2. Проверка что порт слушается
log_info "2. Checking if proxy port is listening..."
nc -z $PROXY_HOST $PROXY_PORT
if [ $? -eq 0 ]; then
    log_success "Port $PROXY_PORT is listening"
else
    log_error "Port $PROXY_PORT is NOT listening"

    # Проверяем что слушается на этом порту
    log_debug "Checking what's listening on port $PROXY_PORT:"
    ssh $PROXY_HOST "netstat -tuln | grep :$PROXY_PORT" || true
    exit 1
fi

# 3. Проверка статуса dedicated proxy через API
log_info "3. Checking dedicated proxy status via API..."
API_RESPONSE=$(curl -s "http://$API_HOST:$API_PORT/api/v1/dedicated-proxy/list" 2>/dev/null)
if [ $? -eq 0 ]; then
    log_success "API is responding"
    echo "API Response: $API_RESPONSE" | jq . 2>/dev/null || echo "Raw: $API_RESPONSE"
else
    log_error "API is not responding"
fi

# 4. Тестирование простого HTTP подключения к прокси
log_info "4. Testing basic HTTP connection to proxy..."
HTTP_TEST=$(curl -v -m 5 "http://$PROXY_HOST:$PROXY_PORT/" 2>&1)
echo "HTTP Test Response:"
echo "$HTTP_TEST"
echo ""

# 5. Тестирование аутентификации
log_info "5. Testing proxy authentication..."
AUTH_TEST=$(curl -v -m 5 -H "Proxy-Authorization: Basic $(echo -n "$USERNAME:$PASSWORD" | base64)" "http://$PROXY_HOST:$PROXY_PORT/" 2>&1)
echo "Auth Test Response:"
echo "$AUTH_TEST"
echo ""

# 6. Тестирование простого GET запроса через прокси
log_info "6. Testing simple GET request through proxy..."
GET_TEST=$(curl -v -m 10 -x "http://$USERNAME:$PASSWORD@$PROXY_HOST:$PROXY_PORT" "http://httpbin.org/ip" 2>&1)
echo "GET Test Response:"
echo "$GET_TEST"
echo ""

# 7. Подробный тест CONNECT запроса
log_info "7. Testing CONNECT request in detail..."
log_test "Sending CONNECT request to httpbin.org:443..."

# Создаем детальный CONNECT тест
CONNECT_TEST=$(timeout 15 bash -c "
exec 5<>/dev/tcp/$PROXY_HOST/$PROXY_PORT
echo 'CONNECT httpbin.org:443 HTTP/1.1'
echo 'Host: httpbin.org:443'
echo 'Proxy-Authorization: Basic $(echo -n \"$USERNAME:$PASSWORD\" | base64)'
echo 'User-Agent: Debug-Script/1.0'
echo 'Proxy-Connection: Keep-Alive'
echo ''
} >&5

# Читаем ответ
timeout 5 cat <&5
exec 5>&-
" 2>&1)

echo "CONNECT Test Response:"
echo "$CONNECT_TEST"
echo ""

# 8. Проверка логов сервера
log_info "8. Checking recent server logs..."
log_debug "Last 20 lines from backend logs:"
ssh $PROXY_HOST "tail -20 /var/www/p-service/logs/backend-error*.log 2>/dev/null | grep -E '(CONNECT|proxy_handler|dedicated|6001)' | tail -10" ||
ssh $PROXY_HOST "journalctl -u p-service-backend -n 20 | grep -E '(CONNECT|proxy_handler|dedicated|6001)'" ||
log_warning "Could not access server logs"

# 9. Проверка процессов
log_info "9. Checking processes..."
ssh $PROXY_HOST "ps aux | grep -E '(python|proxy|6001)' | grep -v grep" || log_warning "Could not check processes"

# 10. Проверка портов
log_info "10. Checking port details..."
ssh $PROXY_HOST "netstat -tulpn | grep :6001" || log_warning "Could not check port details"

# 11. Тест с telnet для низкоуровневой диагностики
log_info "11. Low-level telnet test..."
TELNET_TEST=$(timeout 10 bash -c "
{
    echo 'CONNECT httpbin.org:443 HTTP/1.1'
    echo 'Host: httpbin.org:443'
    echo 'Proxy-Authorization: Basic $(echo -n \"$USERNAME:$PASSWORD\" | base64)'
    echo ''
    sleep 2
} | telnet $PROXY_HOST $PROXY_PORT 2>&1
")
echo "Telnet test:"
echo "$TELNET_TEST"
echo ""

# 12. Детальный анализ CONNECT запроса через strace (если возможно)
log_info "12. Detailed CONNECT analysis..."
log_test "Sending CONNECT with maximum verbosity..."

# Максимально детальный CONNECT тест
DETAILED_CONNECT=$(curl -vvv --trace-ascii /dev/stderr -m 15 \
    -x "http://$USERNAME:$PASSWORD@$PROXY_HOST:$PROXY_PORT" \
    "https://httpbin.org/ip" 2>&1)

echo "Detailed CONNECT output:"
echo "$DETAILED_CONNECT"
echo ""

# 13. Проверка конфигурации прокси через API
log_info "13. Checking proxy configuration..."
PROXY_CONFIG=$(curl -s "http://$API_HOST:$API_PORT/api/v1/dedicated-proxy/android_AH3SCP4B11207250" 2>/dev/null)
if [ $? -eq 0 ]; then
    log_success "Got proxy configuration"
    echo "$PROXY_CONFIG" | jq . 2>/dev/null || echo "Raw: $PROXY_CONFIG"
else
    log_warning "Could not get proxy configuration"
fi

# 14. Мониторинг в реальном времени (краткий)
log_info "14. Real-time monitoring test..."
log_test "Starting background log monitoring..."

# Запускаем мониторинг логов в фоне
(ssh $PROXY_HOST "tail -f /var/www/p-service/logs/backend-error*.log 2>/dev/null | grep --line-buffered -E '(CONNECT|proxy_handler|dedicated|6001)'" &
 ssh $PROXY_HOST "journalctl -u p-service-backend -f | grep --line-buffered -E '(CONNECT|proxy_handler|dedicated|6001)'" &) &
MONITOR_PID=$!

# Ждем немного чтобы мониторинг запустился
sleep 2

log_test "Sending test CONNECT request while monitoring..."
TEST_RESULT=$(timeout 10 curl -vvv -x "http://$USERNAME:$PASSWORD@$PROXY_HOST:$PROXY_PORT" "https://httpbin.org/ip" 2>&1)

# Ждем еще немного для получения логов
sleep 3

# Останавливаем мониторинг
kill $MONITOR_PID 2>/dev/null

echo "Test result while monitoring:"
echo "$TEST_RESULT"
echo ""

# 15. Проверка aiohttp маршрутов (через отладочный API если есть)
log_info "15. Checking aiohttp routes..."
ROUTES_CHECK=$(curl -s "http://$PROXY_HOST:$PROXY_PORT/" -H "User-Agent: Route-Debug/1.0" 2>&1)
echo "Routes check:"
echo "$ROUTES_CHECK"
echo ""

# 16. Финальный анализ
log_info "16. Final analysis..."
echo "🔍 DIAGNOSTIC SUMMARY:"
echo "====================="

# Проверяем основные индикаторы проблем
if echo "$CONNECT_TEST" | grep -q "404"; then
    log_error "Issue: CONNECT requests return 404 - routing problem"
fi

if echo "$CONNECT_TEST" | grep -q "407"; then
    log_error "Issue: Authentication problem"
fi

if echo "$CONNECT_TEST" | grep -q "Connection refused"; then
    log_error "Issue: Connection refused - service not running"
fi

if echo "$CONNECT_TEST" | grep -q "timeout"; then
    log_error "Issue: Request timeout - service hanging"
fi

# Рекомендации
echo ""
log_info "🎯 RECOMMENDATIONS:"
echo "=================="

echo "1. Check if the proxy_handler method is being called:"
echo "   grep 'proxy_handler' /var/www/p-service/logs/backend-error*.log"
echo ""

echo "2. Check aiohttp route registration:"
echo "   Look for route registration in logs during startup"
echo ""

echo "3. Verify middleware execution:"
echo "   Check if auth_middleware is being called"
echo ""

echo "4. Manual route test:"
echo "   curl -v 'http://$PROXY_HOST:$PROXY_PORT/test' -H 'Proxy-Authorization: Basic $(echo -n \"$USERNAME:$PASSWORD\" | base64)'"
echo ""

echo "5. Check device manager:"
echo "   curl -s 'http://$API_HOST:$API_PORT/api/v1/admin/modems'"
echo ""

log_success "Diagnostic complete! Check the output above for issues."

