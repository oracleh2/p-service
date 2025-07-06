# backend/app/core/proxy_server.py - ENHANCED VERSION WITH DEVICE INTERFACE ROUTING

import asyncio
import aiohttp
from aiohttp import web, ClientSession, ClientTimeout, TCPConnector
import time
import socket
import netifaces
from typing import Optional, Dict, Any, List
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import structlog
import subprocess
import re
import json
from datetime import datetime, timezone
import psutil
import random


from ..config import settings

logger = structlog.get_logger()


class ProxyServer:
    """HTTP прокси-сервер с маршрутизацией через интерфейсы мобильных устройств"""

    def __init__(self, device_manager, stats_collector):
        self.device_manager = device_manager
        self.stats_collector = stats_collector
        self.app = None
        self.runner = None
        self.site = None
        self.session: Optional[ClientSession] = None
        self.running = False

    async def start(self):
        """Запуск прокси-сервера"""
        try:
            logger.info(f"Starting enhanced proxy server on {settings.proxy_host}:{settings.proxy_port}")

            # Создание веб-приложения
            self.app = web.Application()
            self.setup_routes()

            # Запуск сервера
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(
                self.runner,
                settings.proxy_host,
                settings.proxy_port
            )

            await self.site.start()
            self.running = True

            logger.info(f"✅ Proxy server started on {settings.proxy_host}:{settings.proxy_port}")

        except Exception as e:
            logger.error(f"❌ Failed to start proxy server: {e}")
            self.running = False
            raise

    async def stop(self):
        """Остановка прокси-сервера"""
        self.running = False

        if self.site:
            await self.site.stop()

        if self.runner:
            await self.runner.cleanup()

        if self.session:
            await self.session.close()

        logger.info("Proxy server stopped")

    def setup_routes(self):
        """Настройка маршрутов"""
        # Корневой обработчик для информации
        self.app.router.add_get('/', self.root_handler)

        # Статус прокси
        self.app.router.add_get('/status', self.status_handler)

        # Универсальный обработчик для всех прокси-запросов
        self.app.router.add_route('*', '/{path:.*}', self.universal_handler)

    async def root_handler(self, request):
        """Обработчик корневого пути"""
        try:
            device_count = 0
            if self.device_manager:
                devices = await self.device_manager.get_all_devices()
                device_count = len(devices)

            return web.json_response({
                "service": "Mobile Proxy Server with Interface Routing",
                "status": "running",
                "version": "2.0.0",
                "available_devices": device_count,
                "features": ["Interface Routing", "IP Rotation", "Device Management"],
                "message": "Enhanced proxy server with device interface routing",
                "examples": {
                    "http": "curl -x http://192.168.1.50:8080 http://httpbin.org/ip",
                    "https": "curl -x http://192.168.1.50:8080 https://httpbin.org/ip",
                    "specific_device": "curl -H 'X-Proxy-Device-ID: android_AH3SCP4B11207250' -x http://192.168.1.50:8080 http://httpbin.org/ip"
                }
            })
        except Exception as e:
            logger.error(f"Error in root handler: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def status_handler(self, request):
        """Обработчик статуса прокси"""
        try:
            device_count = 0
            online_devices = 0
            device_interfaces = []

            if self.device_manager:
                devices = await self.device_manager.get_all_devices()
                device_count = len(devices)
                online_devices = len([d for d in devices.values() if d.get('status') == 'online'])

                # Информация об интерфейсах устройств
                for device_id, device in devices.items():
                    if device.get('status') == 'online':
                        interface_info = await self.get_device_interface_info(device)
                        if interface_info:
                            device_interfaces.append({
                                "device_id": device_id,
                                "device_type": device.get('type'),
                                "interface": interface_info.get('interface'),
                                "ip": interface_info.get('ip'),
                                "routing_method": interface_info.get('routing_method')
                            })

            return web.json_response({
                "proxy_status": "running",
                "total_devices": device_count,
                "online_devices": online_devices,
                "device_interfaces": device_interfaces,
                "proxy_host": settings.proxy_host,
                "proxy_port": settings.proxy_port,
                "supports": ["HTTP", "HTTPS", "Interface Routing"]
            })
        except Exception as e:
            logger.error(f"Error in status handler: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def universal_handler(self, request: web.Request) -> web.Response:
        """ИСПРАВЛЕННЫЙ универсальный обработчик"""
        start_time = time.time()
        client_ip = self.get_client_ip(request)

        try:
            target_url = self.get_target_url(request)
            if not target_url:
                return web.Response(
                    text="Bad Request: Use as HTTP proxy. Example: curl -x http://192.168.1.50:8080 http://httpbin.org/ip",
                    status=400
                )

            logger.info(f"📡 PROXY REQUEST: {request.method} {target_url} from {client_ip}")

            device = await self.debug_device_selection(request)
            if not device:
                logger.error("❌ NO DEVICES AVAILABLE")
                return web.Response(text="No devices available", status=503)

            device_id = device.get('id', 'unknown')
            device_type = device.get('type', 'unknown')
            interface = device.get('interface', 'unknown')

            logger.info(f"✅ SELECTED DEVICE: {device_id}")
            logger.info(f"   Type: {device_type}")
            logger.info(f"   Interface: {interface}")

            # Проверяем что это Android устройство с правильным интерфейсом
            if device_type == 'android' and interface == 'enx566cf3eaaf4b':
                logger.info(f"🚀 USING ANDROID INTERFACE: {interface}")

                # Тестируем подключение (опционально)
                connectivity_ok = await self.test_interface_connectivity(interface)
                if connectivity_ok:
                    logger.info(f"✅ Interface {interface} connectivity test passed")
                else:
                    logger.warning(f"⚠️ Interface {interface} connectivity test failed, but trying anyway")

                # Используем исправленный curl
                response = await self.force_curl_via_interface(request, target_url, interface)

                if response:
                    response_time = int((time.time() - start_time) * 1000)
                    logger.info(f"🎉 SUCCESS via {interface}: {response.status} in {response_time}ms")

                    # Добавляем отладочные заголовки
                    response.headers['X-Debug-Device-ID'] = device_id
                    response.headers['X-Debug-Success'] = 'true'
                    response.headers['X-Response-Time-Ms'] = str(response_time)

                    return response
                else:
                    logger.error(f"❌ IMPROVED CURL STILL FAILED via {interface}")
            else:
                logger.warning(f"⚠️ WRONG DEVICE TYPE OR INTERFACE: type={device_type}, interface={interface}")

            # Fallback
            logger.info("🔄 USING FALLBACK (this will use server's main interface)")
            response = await self.forward_request_default(request, target_url, device)

            response_time = int((time.time() - start_time) * 1000)
            logger.info(f"✅ Fallback completed: {response.status} in {response_time}ms")

            response.headers['X-Debug-Via-Fallback'] = 'true'
            return response

        except Exception as e:
            logger.error(f"❌ ERROR in universal_handler: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return web.Response(text=f"Internal Server Error: {str(e)}", status=500)

    async def get_device_interface_info(self, device: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Получение информации об интерфейсе устройства"""
        try:
            device_type = device.get('type')
            device_id = device.get('id')

            if device_type == 'android':
                return await self.get_android_interface_info(device)
            elif device_type == 'usb_modem':
                return await self.get_usb_modem_interface_info(device)
            elif device_type == 'raspberry_pi':
                return await self.get_raspberry_interface_info(device)

        except Exception as e:
            logger.error(f"Error getting interface info for device {device_id}: {e}")

        return None

    async def get_android_interface_info(self, device: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Получение информации об интерфейсе Android устройства - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            logger.info(f"🔍 Getting interface info for Android device: {device}")

            # Получаем интерфейс из устройства
            interface = device.get('interface')
            adb_id = device.get('adb_id', device.get('id', 'unknown'))

            logger.info(f"Device interface from data: {interface}")
            logger.info(f"Device ADB ID: {adb_id}")

            # ПРИНУДИТЕЛЬНО УСТАНАВЛИВАЕМ ПРАВИЛЬНЫЙ ИНТЕРФЕЙС
            if not interface or interface == "unknown" or interface == adb_id:
                logger.warning(f"Interface not set correctly, forcing to enx566cf3eaaf4b")
                interface = "enx566cf3eaaf4b"

            logger.info(f"Using interface: {interface}")

            # Проверяем, что интерфейс существует и активен
            if interface not in netifaces.interfaces():
                logger.error(f"Interface {interface} not found in system")
                return None

            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addrs:
                logger.error(f"No IP address on interface {interface}")
                return None

            ip = addrs[netifaces.AF_INET][0]['addr']
            logger.info(f"Interface {interface} has IP: {ip}")

            # Проверяем, что интерфейс UP
            try:
                result = subprocess.run(['ip', 'link', 'show', interface],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'UP' in result.stdout:
                    logger.info(f"✅ Android interface {interface} is UP")
                    return {
                        'interface': interface,
                        'ip': ip,
                        'routing_method': 'curl_interface_binding',
                        'type': 'android_usb_tethering'
                    }
                else:
                    logger.warning(f"Interface {interface} is DOWN, trying to bring UP")
                    # Попытка поднять интерфейс
                    subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'up'], timeout=5)
                    return {
                        'interface': interface,
                        'ip': ip,
                        'routing_method': 'curl_interface_binding',
                        'type': 'android_usb_tethering'
                    }
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout checking interface {interface} status")
                return {
                    'interface': interface,
                    'ip': ip,
                    'routing_method': 'curl_interface_binding',
                    'type': 'android_usb_tethering'
                }

        except Exception as e:
            logger.error(f"Error getting Android interface info: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def get_usb_modem_interface_info(self, device: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Получение информации об интерфейсе USB модема"""
        try:
            # Поиск PPP интерфейса
            interfaces = netifaces.interfaces()
            for interface in interfaces:
                if interface.startswith('ppp') or interface.startswith('wwan'):
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        return {
                            'interface': interface,
                            'ip': addrs[netifaces.AF_INET][0]['addr'],
                            'routing_method': 'curl_interface_binding',
                            'type': 'usb_modem'
                        }

        except Exception as e:
            logger.error(f"Error getting USB modem interface info: {e}")

        return None

    async def get_raspberry_interface_info(self, device: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Получение информации об интерфейсе Raspberry Pi"""
        try:
            interface = device.get('interface', '')
            if interface and interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    return {
                        'interface': interface,
                        'ip': addrs[netifaces.AF_INET][0]['addr'],
                        'routing_method': 'curl_interface_binding',
                        'type': 'raspberry_pi'
                    }

        except Exception as e:
            logger.error(f"Error getting Raspberry Pi interface info: {e}")

        return None

    async def forward_request_via_device_interface(self, request, target_url, device):
        """ИСПРАВЛЕННОЕ выполнение запроса через интерфейс устройства"""
        try:
            logger.info(f"🔄 Processing request via device: {device.get('id')}")

            # ПРИНУДИТЕЛЬНАЯ УСТАНОВКА ИНТЕРФЕЙСА ДЛЯ ANDROID
            if device.get('type') == 'android':
                interface = 'enx566cf3eaaf4b'  # Принудительно используем правильный интерфейс
                logger.info(f"🚀 FORCING Android interface: {interface}")

                # Прямой curl запрос
                curl_cmd = ['curl', '--interface', interface, '--silent', '--max-time', '30', target_url]

                process = await asyncio.create_subprocess_exec(
                    *curl_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    logger.info(f"✅ SUCCESS via {interface}")
                    return web.Response(
                        body=stdout,
                        status=200,
                        headers={'X-Proxy-Via': f'android-{interface}', 'Content-Type': 'application/json'}
                    )

            logger.warning(f"Falling back to default routing")
            return await self.forward_request_default(request, target_url, device)

        except Exception as e:
            logger.error(f"Error: {e}")
            return await self.forward_request_default(request, target_url, device)

    async def execute_request_via_curl(
        self,
        request: web.Request,
        target_url: str,
        interface: str
    ) -> Optional[web.Response]:
        """ПРИНУДИТЕЛЬНОЕ выполнение запроса через curl с интерфейсом"""
        try:
            logger.info(f"🚀 FORCING request via interface: {interface}")
            logger.info(f"Target URL: {target_url}")

            # Проверяем интерфейс
            if interface not in netifaces.interfaces():
                logger.error(f"❌ Interface {interface} not found")
                return None

            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addrs:
                logger.error(f"❌ No IP on interface {interface}")
                return None

            interface_ip = addrs[netifaces.AF_INET][0]['addr']
            logger.info(f"✅ Interface {interface} IP: {interface_ip}")

            # Простая команда curl
            curl_cmd = [
                'curl',
                '--interface', interface,
                '--silent',
                '--max-time', '30',
                '--location',
                '--write-out', 'HTTPSTATUS:%{http_code}',
                '--header', f"User-Agent: Mobile-Proxy-Force/1.0",
                target_url
            ]

            logger.info(f"🔧 Executing: {' '.join(curl_cmd)}")

            process = await asyncio.create_subprocess_exec(
                *curl_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            logger.info(f"Curl exit code: {process.returncode}")

            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='ignore')
                logger.info(f"Curl output length: {len(output)}")

                # Парсинг статуса
                status_code = 200
                response_body = output

                if 'HTTPSTATUS:' in output:
                    try:
                        status_pos = output.rfind('HTTPSTATUS:')
                        status_code = int(output[status_pos + 11:].strip())
                        response_body = output[:status_pos]
                        logger.info(f"✅ Parsed status: {status_code}")
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse status: {e}")

                logger.info(f"🎉 SUCCESS! Request via {interface} completed with status {status_code}")

                return web.Response(
                    body=response_body.encode('utf-8'),
                    status=status_code,
                    headers={
                        'X-Forced-Via-Interface': interface,
                        'X-Interface-IP': interface_ip,
                        'X-Forced-Success': 'true',
                        'Content-Type': 'application/json'
                    }
                )
            else:
                error_msg = stderr.decode('utf-8', errors='ignore')
                logger.error(f"❌ Curl failed: {error_msg}")
                return None

        except Exception as e:
            logger.error(f"❌ Exception in force curl: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def forward_request_default(
        self,
        request: web.Request,
        target_url: str,
        device: Dict[str, Any]
    ) -> web.Response:
        """Fallback: выполнение запроса через обычный HTTP клиент"""
        try:
            # Создание временной сессии для этого запроса
            async with ClientSession(
                timeout=ClientTimeout(total=30),
                connector=TCPConnector(limit=10)
            ) as session:

                # Подготовка заголовков
                headers = dict(request.headers)
                headers.pop('Host', None)
                headers.pop('X-Proxy-Device-ID', None)

                # Получение тела запроса
                body = None
                if request.method in ['POST', 'PUT', 'PATCH']:
                    body = await request.read()

                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=body,
                    allow_redirects=False,
                    ssl=False
                ) as response:
                    response_body = await response.read()
                    response_headers = dict(response.headers)
                    response_headers.pop('Transfer-Encoding', None)
                    response_headers['X-Proxy-Via'] = 'default-routing'

                    return web.Response(
                        body=response_body,
                        status=response.status,
                        headers=response_headers
                    )

        except Exception as e:
            logger.error(f"Error in default request forwarding: {e}")
            return web.Response(text=f"Bad Gateway: {str(e)}", status=502)

    def get_client_ip(self, request: web.Request) -> str:
        """Получение IP адреса клиента"""
        try:
            forwarded_for = request.headers.get('X-Forwarded-For')
            if forwarded_for:
                return forwarded_for.split(',')[0].strip()

            real_ip = request.headers.get('X-Real-IP')
            if real_ip:
                return real_ip

            transport = request.transport
            if transport:
                peername = transport.get_extra_info('peername')
                if peername:
                    return peername[0]

            return 'unknown'
        except Exception:
            return 'unknown'

    def get_target_url(self, request: web.Request) -> Optional[str]:
        """Получение целевого URL из запроса"""
        try:
            # Для прямых HTTP запросов через прокси
            if request.path_qs.startswith('http://') or request.path_qs.startswith('https://'):
                return request.path_qs

            # Для запросов с Host заголовком
            host = request.headers.get('Host')
            if host:
                # Исключаем запросы к самому прокси-серверу
                proxy_hosts = [
                    '192.168.1.50:8080',
                    '127.0.0.1:8080',
                    'localhost:8080',
                    f'{settings.proxy_host}:{settings.proxy_port}'
                ]

                if host not in proxy_hosts:
                    scheme = 'https' if request.secure else 'http'
                    return f"{scheme}://{host}{request.path_qs}"

            return None

        except Exception as e:
            logger.error(f"Error getting target URL: {e}")
            return None

    async def make_request_via_interface(self, session: aiohttp.ClientSession,
                                         method: str, url: str, interface: str,
                                         headers: dict = None, data: bytes = None) -> aiohttp.ClientResponse:
        """Выполнение HTTP запроса через конкретный сетевой интерфейс"""

        try:
            # Получаем IP адрес интерфейса
            import netifaces

            if interface not in netifaces.interfaces():
                raise Exception(f"Interface {interface} not found")

            addresses = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addresses:
                raise Exception(f"No IPv4 address on interface {interface}")

            local_ip = addresses[netifaces.AF_INET][0]['addr']

            # Создаем connector с привязкой к локальному IP
            connector = aiohttp.TCPConnector(
                local_addr=(local_ip, 0),  # Привязываемся к IP интерфейса
                limit=100,
                limit_per_host=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )

            # Создаем новую сессию с этим connector
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as bound_session:

                logger.debug(f"Making request via interface {interface} (IP: {local_ip})")

                async with bound_session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=data,
                    allow_redirects=True
                ) as response:
                    return response

        except Exception as e:
            logger.error(f"Error making request via interface {interface}: {e}")
            raise

    async def select_device(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """Выбор устройства для проксирования - ПРИНУДИТЕЛЬНАЯ ВЕРСИЯ"""
        try:
            logger.info("🔍 Selecting device for proxy request...")

            if not self.device_manager:
                logger.error("Device manager not available")
                return None

            # Проверка заголовка для выбора конкретного устройства
            device_id = request.headers.get('X-Proxy-Device-ID')
            logger.info(f"Requested device ID: {device_id}")

            if device_id:
                device = await self.device_manager.get_device_by_id(device_id)
                if device:
                    logger.info(f"✅ Found requested device: {device}")
                    # ПРИНУДИТЕЛЬНО УСТАНАВЛИВАЕМ ПРАВИЛЬНЫЙ ИНТЕРФЕЙС
                    if device.get('type') == 'android' and device.get('adb_id') == 'AH3SCP4B11207250':
                        device['interface'] = 'enx566cf3eaaf4b'
                        device['status'] = 'online'
                        logger.info(f"🔧 Forced interface to enx566cf3eaaf4b for Android device")
                    return device
                else:
                    logger.warning(f"Requested device {device_id} not found")

            # Выбор случайного доступного устройства
            device = await self.device_manager.get_random_device()
            if device:
                logger.info(f"✅ Selected random device: {device}")
                # ПРИНУДИТЕЛЬНО УСТАНАВЛИВАЕМ ПРАВИЛЬНЫЙ ИНТЕРФЕЙС
                if device.get('type') == 'android' and device.get('adb_id') == 'AH3SCP4B11207250':
                    device['interface'] = 'enx566cf3eaaf4b'
                    device['status'] = 'online'
                    logger.info(f"🔧 Forced interface to enx566cf3eaaf4b for Android device")
                return device
            else:
                logger.warning("No online devices available")

                # ПРИНУДИТЕЛЬНО СОЗДАЕМ Android УСТРОЙСТВО
                logger.info("🚨 Creating emergency Android device...")
                emergency_device = {
                    'id': 'android_AH3SCP4B11207250',
                    'type': 'android',
                    'interface': 'enx566cf3eaaf4b',
                    'adb_id': 'AH3SCP4B11207250',
                    'status': 'online',
                    'device_info': 'Emergency Android Device'
                }
                logger.info(f"✅ Emergency device created: {emergency_device}")
                return emergency_device

        except Exception as e:
            logger.error(f"Error selecting device: {e}")
            return None

    def is_running(self) -> bool:
        """Проверка состояния сервера"""
        return self.running

    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики прокси-сервера"""
        try:
            if self.device_manager:
                device_summary = await self.device_manager.get_summary()
            else:
                device_summary = {"total_devices": 0, "online_devices": 0}

            return {
                "devices": device_summary,
                "server_info": {
                    "running": self.running,
                    "host": settings.proxy_host,
                    "port": settings.proxy_port,
                    "routing_method": "device_interface_binding",
                    "supports_interface_routing": True
                }
            }

        except Exception as e:
            logger.error(f"Error getting proxy stats: {e}")
            return {"error": str(e)}

    async def handle_request(self, request: web.Request) -> web.Response:
        """Обработка HTTP запроса - ОБНОВЛЕННАЯ ВЕРСИЯ"""

        try:
            # Выбираем устройство для запроса
            selected_modem = await self.select_modem()
            if not selected_modem:
                return web.Response(text="No modems available", status=503)

            modem_id = selected_modem['id']

            # Получаем маршрут для устройства
            route = await self.get_route_for_modem(modem_id)
            if not route:
                logger.warning(f"No route available for modem {modem_id}")
                return web.Response(text="No route available", status=503)

            # Подготавливаем URL и заголовки
            target_url = str(request.url).replace(str(request.url.with_path('/').with_query('')), '')
            if not target_url.startswith('http'):
                target_url = f"http://{target_url}"

            # Копируем заголовки, исключая hop-by-hop заголовки
            headers = {}
            for name, value in request.headers.items():
                if name.lower() not in ['connection', 'upgrade', 'proxy-authenticate', 'proxy-authorization', 'te',
                                        'trailers', 'transfer-encoding']:
                    headers[name] = value

            # Читаем тело запроса
            body = await request.read()

            start_time = time.time()

            try:
                # Выполняем запрос в зависимости от типа маршрута
                async with aiohttp.ClientSession() as session:

                    if route.get('method') == 'interface_binding':
                        # Запрос через конкретный интерфейс
                        interface = route.get('interface')
                        logger.debug(f"Making request via interface {interface}")

                        response = await self.make_request_via_interface(
                            session, request.method, target_url, interface, headers, body
                        )
                    else:
                        # Обычный запрос
                        async with session.request(
                            method=request.method,
                            url=target_url,
                            headers=headers,
                            data=body
                        ) as response:
                            pass

                    # Читаем ответ
                    response_body = await response.read()
                    response_headers = {}

                    for name, value in response.headers.items():
                        if name.lower() not in ['connection', 'transfer-encoding']:
                            response_headers[name] = value

                    # Логируем статистику
                    elapsed = time.time() - start_time
                    logger.info(
                        f"Request completed via {modem_id}",
                        method=request.method,
                        url=target_url,
                        status=response.status,
                        elapsed=f"{elapsed:.2f}s",
                        interface=route.get('interface', 'unknown')
                    )

                    return web.Response(
                        body=response_body,
                        status=response.status,
                        headers=response_headers
                    )

            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Request failed via {modem_id}",
                    method=request.method,
                    url=target_url,
                    error=str(e),
                    elapsed=f"{elapsed:.2f}s"
                )
                return web.Response(text=f"Request failed: {str(e)}", status=502)

        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return web.Response(text="Internal server error", status=500)

    async def test_interface_routing(self, interface: str) -> bool:
        """Тестирование маршрутизации через интерфейс"""
        try:
            logger.info(f"🧪 Testing interface routing for {interface}")

            if interface not in netifaces.interfaces():
                logger.error(f"Interface {interface} not found")
                return False

            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addrs:
                logger.error(f"No IP on interface {interface}")
                return False

            interface_ip = addrs[netifaces.AF_INET][0]['addr']
            logger.info(f"Interface {interface} has IP: {interface_ip}")

            # Тестовый запрос
            process = await asyncio.create_subprocess_exec(
                'curl', '--interface', interface, '-s', '--connect-timeout', '5',
                'http://httpbin.org/ip',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                try:
                    import json
                    response = json.loads(stdout.decode())
                    external_ip = response.get('origin', '')
                    logger.info(f"✅ Test successful: interface {interface} -> external IP {external_ip}")
                    return True
                except json.JSONDecodeError:
                    logger.error("Failed to parse test response")
                    return False
            else:
                error_msg = stderr.decode()
                logger.error(f"❌ Test failed for interface {interface}: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"❌ Error testing interface {interface}: {e}")
            return False

    async def debug_device_selection(self, request: web.Request):
        """Отладочная функция для проверки выбора устройства"""
        try:
            if not self.device_manager:
                logger.error("Device manager not available")
                return None

            all_devices = await self.device_manager.get_all_devices()
            logger.info(f"Total devices available: {len(all_devices)}")

            for device_id, device in all_devices.items():
                logger.info(
                    f"Device: {device_id}, type: {device.get('type')}, "
                    f"interface: {device.get('interface')}, status: {device.get('status')}"
                )

            # Проверка заголовка для выбора конкретного устройства
            device_id = request.headers.get('X-Proxy-Device-ID')
            if device_id:
                logger.info(f"Requested specific device: {device_id}")
                device = await self.device_manager.get_device_by_id(device_id)
                if device:
                    logger.info(f"Found requested device: {device}")
                    return device
                else:
                    logger.warning(f"Requested device {device_id} not found")

            # Выбор первого доступного устройства
            online_devices = [d for d in all_devices.values() if d.get('status') == 'online']
            logger.info(f"Online devices: {len(online_devices)}")

            if online_devices:
                selected = online_devices[0]
                logger.info(f"Selected first online device: {selected}")
                return selected
            else:
                logger.warning("No online devices found")
                return None

        except Exception as e:
            logger.error(f"Error in debug_device_selection: {e}")
            return None

    async def force_curl_via_interface(self, request: web.Request, target_url: str, interface: str) -> Optional[
        web.Response]:
        """ИСПРАВЛЕННОЕ принудительное выполнение запроса через curl с интерфейсом"""
        try:
            logger.info(f"🔧 FORCING CURL via interface: {interface}")
            logger.info(f"Target URL: {target_url}")

            # Проверяем интерфейс
            if interface not in netifaces.interfaces():
                logger.error(f"❌ Interface {interface} not found")
                return None

            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addrs:
                logger.error(f"❌ No IP on interface {interface}")
                return None

            interface_ip = addrs[netifaces.AF_INET][0]['addr']
            logger.info(f"✅ Interface {interface} IP: {interface_ip}")

            # ИСПРАВЛЕННАЯ команда curl с правильными параметрами
            curl_cmd = [
                'curl',
                '--interface', interface,
                '--silent',
                '--show-error',  # Показывать ошибки
                '--fail-with-body',  # Возвращать тело даже при ошибке
                '--max-time', '30',
                '--connect-timeout', '10',
                '--location',  # Следовать редиректам
                '--compressed',  # Поддержка сжатия
                '--header', 'Accept: application/json, text/plain, */*',
                '--header', 'User-Agent: Mobile-Proxy-Interface/1.0',
                '--write-out', '\\nHTTPSTATUS:%{http_code}\\nTIME:%{time_total}\\n',
                target_url
            ]

            logger.info(f"🔧 Executing curl with improved parameters:")
            logger.info(f"   Command: {' '.join(curl_cmd[:8])}...")

            # Выполнение с улучшенной обработкой ошибок
            process = await asyncio.create_subprocess_exec(
                *curl_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=35  # Чуть больше чем max-time curl
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ Curl timeout after 35 seconds")
                process.kill()
                return None

            logger.info(f"📊 Curl exit code: {process.returncode}")

            if stderr:
                stderr_text = stderr.decode('utf-8', errors='ignore')
                logger.info(f"📝 Curl stderr: {stderr_text}")

            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='ignore')
                logger.info(f"📦 Curl output length: {len(output)} bytes")

                # Улучшенный парсинг ответа
                status_code = 200
                response_body = output
                time_total = "0"

                # Извлекаем метаданные из write-out
                lines = output.split('\n')
                body_lines = []

                for line in lines:
                    if line.startswith('HTTPSTATUS:'):
                        try:
                            status_code = int(line.split(':')[1].strip())
                            logger.info(f"✅ Parsed HTTP status: {status_code}")
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Failed to parse status: {e}")
                    elif line.startswith('TIME:'):
                        try:
                            time_total = line.split(':')[1].strip()
                            logger.info(f"⏱️ Request time: {time_total}s")
                        except (ValueError, IndexError):
                            pass
                    elif line.strip():  # Непустые строки идут в тело ответа
                        body_lines.append(line)

                # Собираем тело ответа
                if body_lines:
                    response_body = '\n'.join(body_lines)
                else:
                    response_body = output.split('HTTPSTATUS:')[0] if 'HTTPSTATUS:' in output else output

                logger.info(f"🎉 SUCCESS! Interface {interface} -> Status {status_code}, Body: {response_body[:100]}...")

                return web.Response(
                    body=response_body.encode('utf-8'),
                    status=status_code,
                    headers={
                        'X-Proxy-Via': f'interface-{interface}',
                        'X-Interface-IP': interface_ip,
                        'X-Request-Time': time_total,
                        'X-Method': 'curl-interface-binding',
                        'Content-Type': 'application/json' if response_body.strip().startswith('{') else 'text/plain'
                    }
                )
            else:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else 'Unknown error'
                logger.error(f"❌ Curl failed with code {process.returncode}: {error_msg}")

                # Попытка диагностики проблемы
                if 'Network is unreachable' in error_msg:
                    logger.error("🚨 Network unreachable - check interface routing")
                elif 'Could not resolve host' in error_msg:
                    logger.error("🚨 DNS resolution failed - check interface DNS")
                elif 'Connection timed out' in error_msg:
                    logger.error("🚨 Connection timeout - check interface connectivity")

                return None

        except Exception as e:
            logger.error(f"❌ Exception in force_curl_via_interface: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def test_interface_connectivity(self, interface: str) -> bool:
        """Тестирование подключения через интерфейс"""
        try:
            logger.info(f"🧪 Testing connectivity for interface: {interface}")

            # Простой ping через интерфейс
            ping_cmd = ['ping', '-I', interface, '-c', '1', '-W', '5', '8.8.8.8']

            process = await asyncio.create_subprocess_exec(
                *ping_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"✅ Ping test successful for {interface}")
                return True
            else:
                logger.warning(f"❌ Ping test failed for {interface}: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error testing interface {interface}: {e}")
            return False
