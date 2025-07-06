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
