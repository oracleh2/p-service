#!/bin/bash
# Скрипт для проверки и запуска прокси-сервера

echo "🔍 Checking proxy server status..."

# 1. Проверяем статус прокси-сервера
echo "1. Checking proxy server status:"
curl -s http://192.168.1.50:8000/admin/proxy-server/status | jq .

echo ""
echo "2. Checking if port 8080 is open:"
netstat -tuln | grep :8080

echo ""
echo "3. Testing direct connection to proxy port:"
timeout 3 curl -v http://192.168.1.50:8080/ 2>&1 || echo "Connection failed"

echo ""
echo "4. Trying to start proxy server:"
curl -X POST http://192.168.1.50:8000/admin/proxy-server/start | jq .

echo ""
echo "5. Waiting 3 seconds and checking status again:"
sleep 3
curl -s http://192.168.1.50:8000/admin/proxy-server/status | jq .

echo ""
echo "6. Testing proxy after start:"
timeout 5 curl -v http://192.168.1.50:8080/ 2>&1 || echo "Still not working"

echo ""
echo "7. Checking backend logs for proxy errors:"
echo "Recent proxy-related logs:"
tail -n 20 /var/www/p-service/logs/backend-error-0.log | grep -i proxy

echo ""
echo "8. Testing proxy with device ID:"
curl -X POST "http://192.168.1.50:8000/admin/modems/android_AH3SCP4B11207250/test" | jq .

echo "🔍 Checking proxy server error details..."

echo "1. Full error from logs:"
echo "Last 30 lines containing proxy errors:"
grep -A 10 -B 5 "proxy_server.py.*line 171" /var/www/p-service/logs/backend-error*.log | tail -30

echo ""
echo "2. Testing proxy with a proper HTTP request:"
echo "Testing with httpbin.org through proxy:"
curl -v -x http://192.168.1.50:8080 https://httpbin.org/ip 2>&1

echo ""
echo "3. Testing proxy root endpoint:"
echo "GET request to proxy root:"
curl -v http://192.168.1.50:8080/ 2>&1

echo ""
echo "4. Check if the issue is in get_target_url function:"
echo "Let's see recent error logs:"
tail -50 /var/www/p-service/logs/backend-error*.log | grep -A 5 -B 5 "proxy_handler\|get_target_url\|select_device"


echo "🧪 Testing current proxy functionality..."

echo ""
echo "1. Test HTTP (not HTTPS) through proxy:"
curl -x http://192.168.1.50:8080 http://httpbin.org/ip

echo ""
echo "2. Test direct API call:"
curl -X POST "http://192.168.1.50:8000/proxy/test?modem_id=android_AH3SCP4B11207250"

echo ""
echo "3. Test proxy status endpoint:"
curl http://192.168.1.50:8080/status

echo ""
echo "4. Check if proxy routes are set correctly:"
echo "Testing with various paths:"
curl -s http://192.168.1.50:8080/test123 | head -100
