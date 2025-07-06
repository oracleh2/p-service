# backend/app/core/proxy_server.py - ENHANCED VERSION WITH DEVICE INTERFACE ROUTING

import asyncio
import aiohttp
from aiohttp import web, ClientSession, ClientTimeout, TCPConnector
import time
import socket
import netifaces
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
import structlog
import subprocess

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
        """Получение информации об интерфейсе Android устройства"""
        try:
            # Поиск USB tethering интерфейса
            android_interfaces = ['enx566cf3eaaf4b', 'usb0', 'rndis0', 'enp0s20u1']

            for interface in android_interfaces:
                if interface in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        ip = addrs[netifaces.AF_INET][0]['addr']

                        # Проверяем, что интерфейс UP
                        result = subprocess.run(['ip', 'link', 'show', interface],
                                                capture_output=True, text=True)
                        if result.returncode == 0 and 'UP' in result.stdout:
                            return {
                                'interface': interface,
                                'ip': ip,
                                'routing_method': 'curl_interface_binding',
                                'type': 'android_usb_tethering'
                            }

        except Exception as e:
            logger.error(f"Error getting Android interface info: {e}")

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
        """Выполнение запроса через интерфейс устройства"""
        try:
            # Получение информации об интерфейсе устройства
            interface_info = await self.get_device_interface_info(device)

            if not interface_info:
                logger.warning(f"No interface info for device {device['id']}, using default routing")
                return await self.forward_request_default(request, target_url, device)

            interface = interface_info['interface']
            logger.info(f"Routing request via interface {interface} for device {device['id']}")

            # Использование curl для привязки к интерфейсу
            response = await self.execute_request_via_curl(request, target_url, interface)

            if response:
                return response
            else:
                logger.warning(f"Curl request failed, fallback to default routing")
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
        """Выполнение запроса через curl с привязкой к интерфейсу"""
        try:
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

            # Добавление заголовков
            for header_name, header_value in request.headers.items():
                if header_name.lower() not in ['host', 'content-length', 'connection']:
                    curl_cmd.extend(['--header', f"{header_name}: {header_value}"])

            # Обработка POST/PUT данных
            if request.method in ['POST', 'PUT', 'PATCH']:
                body = await request.read()
                if body:
                    curl_cmd.extend(['--data-binary', '@-'])
                curl_cmd.extend(['-X', request.method])

            # Добавление URL
            curl_cmd.append(target_url)

            logger.info(f"Executing curl via {interface}: {' '.join(curl_cmd[:8])}...")

            # Выполнение curl
            if request.method in ['POST', 'PUT', 'PATCH']:
                body = await request.read()
                process = await asyncio.create_subprocess_exec(
                    *curl_cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate(input=body)
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
                    status_code = int(output[status_pos + 11:].strip())
                    response_body = output[:status_pos].encode('utf-8')
                else:
                    status_code = 200
                    response_body = stdout

                logger.info(f"Curl request successful via {interface}: status {status_code}")

                return web.Response(
                    body=response_body,
                    status=status_code,
                    headers={'X-Proxy-Via': f"interface-{interface}"}
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

    async def select_device(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """Выбор устройства для проксирования"""
        try:
            if not self.device_manager:
                return None

            # Проверка заголовка для выбора конкретного устройства
            device_id = request.headers.get('X-Proxy-Device-ID')
            if device_id:
                device = await self.device_manager.get_device_by_id(device_id)
                if device and device.get('status') == 'online':
                    return device

            # Выбор случайного доступного устройства
            return await self.device_manager.get_random_device()

        except Exception as e:
            logger.error(f"Error selecting device: {e}")
            return None

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
