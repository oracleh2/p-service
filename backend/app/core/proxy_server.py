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
        """Универсальный обработчик для всех запросов"""
        start_time = time.time()
        client_ip = self.get_client_ip(request)

        try:
            # Получение целевого URL
            target_url = self.get_target_url(request)
            if not target_url:
                return web.Response(
                    text="Bad Request: Use as HTTP proxy. Example: curl -x http://192.168.1.50:8080 http://httpbin.org/ip",
                    status=400
                )

            logger.info(f"Request: {request.method} {target_url} from {client_ip}")

            # Выбор устройства
            device = await self.select_device(request)
            if not device:
                logger.warning("No devices available")
                return web.Response(text="No devices available", status=503)

            logger.info(f"Selected device: {device['id']} ({device['type']})")

            # Выполнение запроса через интерфейс устройства
            response = await self.forward_request_via_device_interface(request, target_url, device)

            response_time = int((time.time() - start_time) * 1000)
            logger.info(f"Request completed: {response.status} in {response_time}ms")

            return response

        except Exception as e:
            logger.error(f"Error in universal handler: {e}")
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
            # Получаем интерфейс из устройства (теперь он должен быть реальным)
            interface = device.get('interface')
            adb_id = device.get('adb_id')

            if not interface or interface == "unknown":
                logger.warning(f"No interface found for Android device {adb_id}")
                return None

            # Проверяем, что интерфейс существует и активен
            if interface not in netifaces.interfaces():
                logger.warning(f"Interface {interface} not found in system for device {adb_id}")
                return None

            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addrs:
                logger.warning(f"No IP address on interface {interface} for device {adb_id}")
                return None

            ip = addrs[netifaces.AF_INET][0]['addr']

            # Проверяем, что интерфейс UP
            try:
                result = subprocess.run(['ip', 'link', 'show', interface],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'UP' in result.stdout:
                    logger.info(f"Android interface {interface} is UP for device {adb_id}")
                    return {
                        'interface': interface,
                        'ip': ip,
                        'routing_method': 'curl_interface_binding',
                        'type': 'android_usb_tethering'
                    }
                else:
                    logger.warning(f"Interface {interface} is DOWN for device {adb_id}")
                    return None
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout checking interface {interface} status")
                return None

        except Exception as e:
            logger.error(f"Error getting Android interface info for {device.get('adb_id')}: {e}")
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

    async def forward_request_via_device_interface(
        self,
        request: web.Request,
        target_url: str,
        device: Dict[str, Any]
    ) -> web.Response:
        """Выполнение запроса через интерфейс устройства - УЛУЧШЕННАЯ ВЕРСИЯ"""
        try:
            # Получение информации об интерфейсе устройства
            interface_info = await self.get_device_interface_info(device)

            if not interface_info:
                logger.warning(f"No interface info for device {device['id']}, using default routing")
                return await self.forward_request_default(request, target_url, device)

            interface = interface_info['interface']
            device_type = device.get('type', 'unknown')

            logger.info(f"Routing {request.method} request to {target_url} via {device_type} interface {interface}")

            # Использование curl для привязки к интерфейсу
            response = await self.execute_request_via_curl(request, target_url, interface)

            if response:
                # Добавляем информацию об устройстве в заголовки
                response.headers['X-Proxy-Device-Type'] = device_type
                response.headers['X-Proxy-Device-ID'] = device.get('id', 'unknown')
                if device_type == 'android':
                    response.headers[
                        'X-Proxy-Android-Model'] = f"{device.get('manufacturer', 'Unknown')} {device.get('model', 'Unknown')}"
                return response
            else:
                logger.warning(f"Curl request failed for interface {interface}, fallback to default routing")
                return await self.forward_request_default(request, target_url, device)

        except Exception as e:
            logger.error(f"Error forwarding request via device interface: {e}")
            return await self.forward_request_default(request, target_url, device)

    async def execute_request_via_curl(
        self,
        request: web.Request,
        target_url: str,
        interface: str
    ) -> Optional[web.Response]:
        """Выполнение запроса через curl с привязкой к интерфейсу - УЛУЧШЕННАЯ ВЕРСИЯ"""
        try:
            # Проверяем, что интерфейс доступен
            if interface not in netifaces.interfaces():
                logger.error(f"Interface {interface} not found")
                return None

            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addrs:
                logger.error(f"No IP on interface {interface}")
                return None

            # Подготовка команды curl
            curl_cmd = [
                'curl',
                '--interface', interface,
                '--silent',
                '--show-error',
                '--max-time', '30',
                '--location',  # Следовать редиректам
                '--write-out', 'HTTPSTATUS:%{http_code}',
                '--header', f"User-Agent: {request.headers.get('User-Agent', 'Mobile-Proxy/2.0')}",
            ]

            # Добавление заголовков (исключаем некоторые)
            excluded_headers = ['host', 'content-length', 'connection', 'x-proxy-device-id']
            for header_name, header_value in request.headers.items():
                if header_name.lower() not in excluded_headers:
                    curl_cmd.extend(['--header', f"{header_name}: {header_value}"])

            # Обработка POST/PUT данных
            request_body = None
            if request.method in ['POST', 'PUT', 'PATCH']:
                request_body = await request.read()
                if request_body:
                    curl_cmd.extend(['--data-binary', '@-'])
                curl_cmd.extend(['-X', request.method])

            # Добавление URL
            curl_cmd.append(target_url)

            logger.info(f"Executing curl via {interface}: {request.method} {target_url}")

            # Выполнение curl
            if request_body:
                process = await asyncio.create_subprocess_exec(
                    *curl_cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate(input=request_body)
            else:
                process = await asyncio.create_subprocess_exec(
                    *curl_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # Парсинг ответа curl
                output = stdout.decode('utf-8', errors='ignore')

                # Извлечение HTTP статуса
                if 'HTTPSTATUS:' in output:
                    status_pos = output.rfind('HTTPSTATUS:')
                    try:
                        status_code = int(output[status_pos + 11:].strip())
                        response_body = output[:status_pos].encode('utf-8')
                    except ValueError:
                        status_code = 200
                        response_body = stdout
                else:
                    status_code = 200
                    response_body = stdout

                logger.info(
                    f"Curl request successful via {interface}: status {status_code}, body size {len(response_body)}")

                return web.Response(
                    body=response_body,
                    status=status_code,
                    headers={
                        'X-Proxy-Via': f"interface-{interface}",
                        'X-Proxy-Method': 'curl-interface-binding'
                    }
                )
            else:
                error_msg = stderr.decode('utf-8', errors='ignore')
                logger.error(f"Curl request failed via {interface}: {error_msg}")
                return None

        except Exception as e:
            logger.error(f"Error executing curl request via {interface}: {e}")
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
        """Выбор устройства для проксирования - УЛУЧШЕННАЯ ВЕРСИЯ"""
        try:
            if not self.device_manager:
                logger.warning("Device manager not available")
                return None

            # Проверка заголовка для выбора конкретного устройства
            device_id = request.headers.get('X-Proxy-Device-ID')
            if device_id:
                device = await self.device_manager.get_device_by_id(device_id)
                if device and device.get('status') == 'online':
                    logger.info(f"Using specific device requested: {device_id}")
                    return device
                else:
                    logger.warning(f"Requested device {device_id} not available")

            # Выбор случайного доступного устройства
            device = await self.device_manager.get_random_device()
            if device:
                logger.info(f"Selected random device: {device.get('id')} ({device.get('type')})")
            else:
                logger.warning("No online devices available")

            return device

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
