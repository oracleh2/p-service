# backend/app/core/dedicated_proxy_manager.py

import asyncio
import base64
import aiohttp
from aiohttp import web, BasicAuth
from typing import Dict, Any, Optional, List, Set
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import socket
import uuid
import base64

from ..models.database import AsyncSessionLocal
from ..models.base import ProxyDevice
from ..utils.security import get_password_hash, verify_password

logger = structlog.get_logger()


class DedicatedProxyServer:
    """Индивидуальный прокси-сервер для конкретного устройства"""

    def __init__(self, device_id: str, port: int, username: str, password: str, device_manager):
        self.device_id = device_id
        self.port = port
        self.username = username
        self.password = password
        self.device_manager = device_manager
        self.app = None
        self.runner = None
        self.site = None
        self._running = False

    async def start(self):
        """Запуск индивидуального прокси-сервера"""
        if self._running:
            logger.info(f"Dedicated proxy server for {self.device_id} already running on port {self.port}")
            return

        try:
            logger.info(f"🚀 Starting dedicated proxy server for device {self.device_id} on port {self.port}")

            # Проверяем доступность порта
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('0.0.0.0', self.port))
                    logger.info(f"✅ Port {self.port} is available")
                except OSError as e:
                    logger.error(f"❌ Port {self.port} is not available: {e}")
                    raise

            # Создание веб-приложения
            self.app = web.Application()

            # ОТЛАДОЧНЫЙ MIDDLEWARE для логирования всех запросов
            @web.middleware
            async def debug_middleware(request, handler):
                logger.info(f"🔥 RAW REQUEST DEBUG:")
                logger.info(f"   Method: {request.method}")
                logger.info(f"   Path: '{request.path}'")
                logger.info(f"   Path_qs: '{request.path_qs}'")
                logger.info(f"   URL: {request.url}")
                logger.info(f"   Query string: '{request.query_string}'")
                logger.info(f"   Headers: {dict(request.headers)}")

                # Попробуем получить raw данные
                try:
                    if hasattr(request, 'transport') and request.transport:
                        transport = request.transport
                        logger.info(f"   Transport: {type(transport)}")
                        if hasattr(transport, 'get_extra_info'):
                            socket_info = transport.get_extra_info('socket')
                            logger.info(f"   Socket: {socket_info}")
                except Exception as e:
                    logger.info(f"   Transport info error: {e}")

                # Вызываем следующий middleware/handler
                response = await handler(request)

                logger.info(f"   Response status: {response.status}")
                return response

            # Добавляем отладочный middleware первым
            self.app.middlewares.append(debug_middleware)

            # AUTH MIDDLEWARE
            # @web.middleware
            # async def debug_middleware(request, handler):
            #     logger.info(f"🔥 RAW REQUEST DEBUG:")
            #     logger.info(f"   Method: {request.method}")
            #     logger.info(f"   Path: '{request.path}'")
            #     logger.info(f"   Path_qs: '{request.path_qs}'")
            #     logger.info(f"   URL: {request.url}")
            #     logger.info(f"   Query string: '{request.query_string}'")
            #     logger.info(f"   Headers: {dict(request.headers)}")
            #
            #     # Попробуем получить raw данные
            #     try:
            #         if hasattr(request, 'transport') and request.transport:
            #             transport = request.transport
            #             logger.info(f"   Transport: {type(transport)}")
            #             if hasattr(transport, 'get_extra_info'):
            #                 socket_info = transport.get_extra_info('socket')
            #                 logger.info(f"   Socket: {socket_info}")
            #     except Exception as e:
            #         logger.info(f"   Transport info error: {e}")
            #
            #     # Вызываем следующий middleware/handler
            #     response = await handler(request)
            #
            #     logger.info(f"   Response status: {response.status}")
            #     return response
            # async def auth_middleware(request, handler):
            #     # Проверяем аутентификацию
            #     auth_header = request.headers.get('Proxy-Authorization')
            #     if not auth_header:
            #         logger.info("❌ No Proxy-Authorization header")
            #         return web.Response(
            #             status=407,
            #             headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
            #             text="Proxy Authentication Required"
            #         )
            #
            #     try:
            #         # Парсинг Basic Auth
            #         if not auth_header.startswith('Basic '):
            #             raise ValueError("Invalid auth method")
            #
            #         encoded_credentials = auth_header[6:]
            #         decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
            #         username, password = decoded_credentials.split(':', 1)
            #
            #         # Проверка учетных данных
            #         if username != self.username or password != self.password:
            #             logger.info(f"❌ Invalid credentials: {username}")
            #             return web.Response(
            #                 status=407,
            #                 headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
            #                 text="Invalid credentials"
            #             )
            #
            #         logger.info(f"✅ Authentication successful for: {username}")
            #
            #     except Exception as e:
            #         logger.info(f"❌ Authentication error: {e}")
            #         return web.Response(
            #             status=407,
            #             headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
            #             text="Authentication error"
            #         )
            #
            #     # Передаем управление дальше
            #     return await handler(request)
            #
            # self.app.middlewares.append(debug_middleware)
            #
            # self.app.middlewares.append(auth_middleware)

            @web.middleware
            async def auth_and_connect_middleware(request, handler):
                # Проверяем аутентификацию
                auth_header = request.headers.get('Proxy-Authorization')
                if not auth_header:
                    logger.info("❌ No Proxy-Authorization header")
                    return web.Response(
                        status=407,
                        headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
                        text="Proxy Authentication Required"
                    )

                try:
                    # Парсинг Basic Auth
                    if not auth_header.startswith('Basic '):
                        raise ValueError("Invalid auth method")

                    encoded_credentials = auth_header[6:]
                    decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
                    username, password = decoded_credentials.split(':', 1)

                    # Проверка учетных данных
                    if username != self.username or password != self.password:
                        logger.info(f"❌ Invalid credentials: {username}")
                        return web.Response(
                            status=407,
                            headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
                            text="Invalid credentials"
                        )

                    logger.info(f"✅ Authentication successful for: {username}")

                except Exception as e:
                    logger.info(f"❌ Authentication error: {e}")
                    return web.Response(
                        status=407,
                        headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
                        text="Authentication error"
                    )

                # 🔥 ГЛАВНОЕ ИСПРАВЛЕНИЕ: Перехватываем CONNECT на уровне middleware
                if request.method == 'CONNECT':
                    logger.info(f"🔗 CONNECT intercepted in middleware - bypassing router!")

                    # Вызываем proxy_handler напрямую, минуя роутер
                    return await self.proxy_handler(request)

                # Для остальных запросов передаем в роутер
                return await handler(request)

            self.app.middlewares.append(auth_and_connect_middleware)

            # МАКСИМАЛЬНО ПРОСТЫЕ РОУТЫ
            # Один универсальный обработчик
            async def universal_handler(request):
                logger.info(f"🎯 UNIVERSAL HANDLER: {request.method} '{request.path_qs}'")
                return await self.proxy_handler(request)

            for method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']:
                self.app.router.add_route(method, '/{path:.*}', universal_handler)
                self.app.router.add_route(method, '/', universal_handler)


            # self.app.router.add_route('*', '/{path:.*}', universal_handler)

            logger.info(f"📋 Registered universal route for {self.device_id}")

            # Запуск сервера
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
            await self.site.start()

            self._running = True

            # Проверяем запуск
            await asyncio.sleep(0.1)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                result = s.connect_ex(('127.0.0.1', self.port))
                if result == 0:
                    logger.info(f"✅ Dedicated proxy server started and listening on port {self.port}")
                else:
                    logger.error(f"❌ Dedicated proxy server started but not listening on port {self.port}")

            logger.info(
                "Dedicated proxy server started successfully",
                device_id=self.device_id,
                port=self.port,
                username=self.username
            )

        except Exception as e:
            logger.error(
                "Failed to start dedicated proxy server",
                device_id=self.device_id,
                port=self.port,
                error=str(e)
            )
            self._running = False
            raise

    async def proxy_handler(self, request):
        """Отладочная версия обработчика"""
        try:
            logger.info(f"🎯 PROXY HANDLER START")
            logger.info(f"   Method: {request.method}")
            logger.info(f"   Path: '{request.path}'")
            logger.info(f"   Path_qs: '{request.path_qs}'")
            logger.info(f"   URL: {request.url}")
            logger.info(f"   Headers: {dict(request.headers)}")

            # Получение информации об устройстве
            device = await self.device_manager.get_device_by_id(self.device_id)
            if not device or device.get('status') != 'online':
                logger.error(f"Device {self.device_id} not available or offline")
                return web.Response(
                    status=503,
                    text="Device not available"
                )

            # Специальная обработка CONNECT
            if request.method == 'CONNECT':
                logger.info(f"🔗 CONNECT request detected!")

                # Попытка получить target из разных мест
                target_candidates = [
                    request.headers.get('Host'),
                    request.path_qs.strip('/') if request.path_qs != '/' else None,
                    request.path.strip('/') if request.path != '/' else None,
                    str(request.url.host) + ':' + str(request.url.port) if request.url.host else None
                ]

                target = None
                for candidate in target_candidates:
                    if candidate and candidate.strip():
                        target = candidate.strip()
                        logger.info(f"🎯 Found target candidate: '{target}'")
                        break

                if not target:
                    logger.error(f"❌ No target found for CONNECT request")
                    logger.error(f"   Tried candidates: {target_candidates}")
                    return web.Response(
                        status=400,
                        text="Bad Request: No target for CONNECT"
                    )

                logger.info(f"🔗 CONNECT target: '{target}'")

                # Простой ответ для CONNECT
                return web.Response(
                    status=200,
                    text="Connection established",
                    headers={'Connection': 'close'}
                )

            # HTTP запросы
            logger.info(f"🌐 HTTP request processing...")
            return web.Response(
                status=200,
                text=f"HTTP {request.method} request handled",
                headers={'Content-Type': 'text/plain'}
            )

        except Exception as e:
            logger.error(f"Error in proxy handler: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return web.Response(
                status=500,
                text="Internal proxy error"
            )

    async def universal_handler(self, request):
        logger.info(f"🎯 UNIVERSAL HANDLER: {request.method} '{request.path_qs}'")
        return await self.proxy_handler(request)

    async def stop(self):
        """Остановка индивидуального прокси-сервера"""
        if not self._running:
            return

        try:
            if self.site:
                await self.site.stop()
                self.site = None

            if self.runner:
                await self.runner.cleanup()
                self.runner = None

            self.app = None
            self._running = False

            logger.info(
                "Dedicated proxy server stopped",
                device_id=self.device_id,
                port=self.port
            )

        except Exception as e:
            logger.error(
                "Error stopping dedicated proxy server",
                device_id=self.device_id,
                port=self.port,
                error=str(e)
            )

    @web.middleware
    async def auth_middleware(self, request, handler):
        """Этот метод больше не используется - аутентификация перенесена в start()"""
        return await handler(request)

    async def handle_http(self, request, device):
        """Обработка HTTP запросов"""
        # Получение целевого URL из пути запроса
        target_url = str(request.url)

        # Подготовка заголовков
        headers = dict(request.headers)
        headers.pop('Proxy-Authorization', None)
        headers.pop('Host', None)

        # Выполнение запроса через устройство
        try:
            # Здесь должна быть логика прокси через конкретное устройство
            # Пока используем простую реализацию через aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=await request.read() if request.content_length else None
                ) as response:
                    # Подготовка ответа
                    body = await response.read()

                    return web.Response(
                        status=response.status,
                        headers=dict(response.headers),
                        body=body
                    )

        except Exception as e:
            logger.error(
                "Error proxying HTTP request",
                device_id=self.device_id,
                target_url=target_url,
                error=str(e)
            )
            return web.Response(
                status=502,
                text="Bad Gateway"
            )

    async def handle_connect_backup(self, request, device):
        """Обработка CONNECT запросов (HTTPS туннелирование)"""
        # Упрощенная реализация CONNECT
        return web.Response(
            status=200,
            text="Connection established"
        )

    async def handle_connect(self, request, device):
        """ПОЛНАЯ реализация CONNECT запросов (HTTPS туннелирование)"""
        try:
            # Парсим хост и порт из запроса
            host_port = request.path_qs  # например "httpbin.org:443"
            if ':' in host_port:
                host, port = host_port.rsplit(':', 1)
                port = int(port)
            else:
                host = host_port
                port = 443

            logger.info(f"🔗 CONNECT tunnel: {host}:{port} via device {self.device_id}")

            # Получаем интерфейс устройства для туннелирования
            interface = device.get('interface') or device.get('usb_interface')

            if interface and interface != 'unknown':
                logger.info(f"🔧 Creating tunnel via interface: {interface}")
                return await self.create_interface_tunnel(request, host, port, interface)
            else:
                logger.info("🔧 Creating standard tunnel (no specific interface)")
                return await self.create_standard_tunnel(request, host, port)

        except Exception as e:
            logger.error(f"❌ CONNECT error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return web.Response(
                status=502,
                text="Bad Gateway"
            )

    async def create_interface_tunnel(self, request, host: str, port: int, interface: str):
        """Создание туннеля через конкретный интерфейс"""
        try:
            # Создаем сокет с привязкой к интерфейсу
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Привязываем к интерфейсу (только на Linux)
            try:
                target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
                logger.info(f"✅ Socket bound to interface: {interface}")
            except OSError as e:
                logger.warning(f"⚠️  Failed to bind to interface {interface}: {e}, using standard connection")
                # Продолжаем без привязки к интерфейсу

            # Делаем сокет неблокирующим
            target_sock.setblocking(False)

            # Подключаемся к целевому серверу
            try:
                await asyncio.get_event_loop().sock_connect(target_sock, (host, port))
                logger.info(f"✅ Connected to {host}:{port} via interface {interface}")
            except OSError as e:
                target_sock.close()
                logger.error(f"❌ Failed to connect to {host}:{port}: {e}")
                return web.Response(status=502, text="Connection failed")

            # Получаем транспорт клиента
            client_transport = request.transport
            if not client_transport:
                target_sock.close()
                return web.Response(status=502, text="No client transport")

            # Отправляем клиенту подтверждение установки туннеля
            success_response = b"HTTP/1.1 200 Connection established\r\n\r\n"
            client_transport.write(success_response)
            await asyncio.sleep(0.1)  # Даем время на отправку

            logger.info(f"🚀 Starting bidirectional tunnel for {host}:{port}")

            # Запускаем bidirectional туннель
            await self.run_tunnel(client_transport, target_sock, host, port)

            return web.Response(status=200, text="")

        except Exception as e:
            logger.error(f"❌ Interface tunnel error: {e}")
            if 'target_sock' in locals():
                target_sock.close()
            return web.Response(status=502, text="Tunnel creation failed")

    async def create_standard_tunnel(self, request, host: str, port: int):
        """Создание стандартного туннеля"""
        try:
            # Создаем соединение с целевым сервером
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.setblocking(False)

            try:
                await asyncio.get_event_loop().sock_connect(target_sock, (host, port))
                logger.info(f"✅ Connected to {host}:{port} (standard)")
            except OSError as e:
                target_sock.close()
                logger.error(f"❌ Failed to connect to {host}:{port}: {e}")
                return web.Response(status=502, text="Connection failed")

            # Получаем транспорт клиента
            client_transport = request.transport
            if not client_transport:
                target_sock.close()
                return web.Response(status=502, text="No client transport")

            # Отправляем подтверждение
            success_response = b"HTTP/1.1 200 Connection established\r\n\r\n"
            client_transport.write(success_response)
            await asyncio.sleep(0.1)

            logger.info(f"🚀 Starting standard tunnel for {host}:{port}")

            # Запускаем туннель
            await self.run_tunnel(client_transport, target_sock, host, port)

            return web.Response(status=200, text="")

        except Exception as e:
            logger.error(f"❌ Standard tunnel error: {e}")
            if 'target_sock' in locals():
                target_sock.close()
            return web.Response(status=502, text="Connection failed")

    async def run_tunnel(self, client_transport, target_sock, host: str, port: int):
        """Запуск bidirectional туннеля между клиентом и сервером"""
        try:
            # Получаем сокет клиента
            client_sock = client_transport.get_extra_info('socket')
            if not client_sock:
                raise Exception("No client socket available")

            logger.info(f"🔄 Running tunnel: client <-> {host}:{port}")

            # Создаем задачи для перенаправления данных в обе стороны
            client_to_server_task = asyncio.create_task(
                self.forward_data(client_sock, target_sock, f"client -> {host}:{port}")
            )
            server_to_client_task = asyncio.create_task(
                self.forward_data(target_sock, client_sock, f"{host}:{port} -> client")
            )

            # Ждем завершения любой из задач (что означает закрытие соединения)
            try:
                done, pending = await asyncio.wait(
                    [client_to_server_task, server_to_client_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=300  # 5 минут таймаут
                )

                logger.info(f"🔚 Tunnel ended for {host}:{port}")

            except asyncio.TimeoutError:
                logger.info(f"⏰ Tunnel timeout for {host}:{port}")
            finally:
                # Отменяем оставшиеся задачи
                client_to_server_task.cancel()
                server_to_client_task.cancel()

                # Закрываем соединения
                try:
                    target_sock.close()
                except:
                    pass

                try:
                    client_transport.close()
                except:
                    pass

        except Exception as e:
            logger.error(f"❌ Tunnel run error: {e}")
            try:
                target_sock.close()
            except:
                pass

    async def forward_data(self, from_sock, to_sock, direction: str):
        """Перенаправление данных между сокетами"""
        try:
            total_bytes = 0
            while True:
                # Читаем данные из исходного сокета
                try:
                    data = await asyncio.get_event_loop().sock_recv(from_sock, 8192)
                    if not data:
                        logger.debug(f"📤 {direction}: connection closed (no data)")
                        break

                    # Отправляем данные в целевой сокет
                    await asyncio.get_event_loop().sock_sendall(to_sock, data)
                    total_bytes += len(data)

                    if total_bytes % 10240 == 0:  # Логируем каждые 10KB
                        logger.debug(f"📊 {direction}: {total_bytes} bytes transferred")

                except ConnectionResetError:
                    logger.debug(f"📤 {direction}: connection reset")
                    break
                except OSError as e:
                    if e.errno in (9, 104):  # Bad file descriptor or Connection reset
                        logger.debug(f"📤 {direction}: connection error {e}")
                        break
                    raise

            logger.debug(f"✅ {direction}: finished, total {total_bytes} bytes")

        except asyncio.CancelledError:
            logger.debug(f"🚫 {direction}: cancelled")
        except Exception as e:
            logger.debug(f"❌ {direction}: error {e}")
        finally:
            # Попытка закрыть сокеты при завершении
            try:
                from_sock.close()
            except:
                pass
            try:
                to_sock.close()
            except:
                pass

    def is_running(self):
        """Проверка статуса работы сервера"""
        return self._running

    async def handle_connect_direct(self, request, device, target: str):
        """Прямая обработка CONNECT запросов с указанным target"""
        try:
            # Парсим хост и порт из target
            if ':' in target:
                host, port = target.rsplit(':', 1)
                port = int(port)
            else:
                host = target
                port = 443

            logger.info(f"🔗 CONNECT tunnel: {host}:{port} via device {self.device_id}")

            # Получаем интерфейс устройства для туннелирования
            interface = device.get('interface') or device.get('usb_interface')

            if interface and interface != 'unknown':
                logger.info(f"🔧 Creating tunnel via interface: {interface}")
                return await self.create_interface_tunnel_direct(request, host, port, interface)
            else:
                logger.info("🔧 Creating standard tunnel (no specific interface)")
                return await self.create_standard_tunnel_direct(request, host, port)

        except Exception as e:
            logger.error(f"❌ CONNECT direct error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return web.Response(
                status=502,
                text="Bad Gateway"
            )

    async def create_interface_tunnel_direct(self, request, host: str, port: int, interface: str):
        """Создание туннеля через конкретный интерфейс (прямая версия)"""
        try:
            # Создаем сокет с привязкой к интерфейсу
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Привязываем к интерфейсу (только на Linux)
            try:
                target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
                logger.info(f"✅ Socket bound to interface: {interface}")
            except OSError as e:
                logger.warning(f"⚠️  Failed to bind to interface {interface}: {e}, using standard connection")

            # Делаем сокет неблокирующим
            target_sock.setblocking(False)

            # Подключаемся к целевому серверу
            try:
                await asyncio.get_event_loop().sock_connect(target_sock, (host, port))
                logger.info(f"✅ Connected to {host}:{port} via interface {interface}")
            except OSError as e:
                target_sock.close()
                logger.error(f"❌ Failed to connect to {host}:{port}: {e}")
                return web.Response(status=502, text="Connection failed")

            # Получаем транспорт клиента
            client_transport = request.transport
            if not client_transport:
                target_sock.close()
                return web.Response(status=502, text="No client transport")

            # Отправляем клиенту подтверждение установки туннеля
            success_response = b"HTTP/1.1 200 Connection established\r\n\r\n"
            client_transport.write(success_response)
            await asyncio.sleep(0.1)  # Даем время на отправку

            logger.info(f"🚀 Starting bidirectional tunnel for {host}:{port}")

            # Запускаем bidirectional туннель
            await self.run_tunnel(client_transport, target_sock, host, port)

            return web.Response(status=200, text="")

        except Exception as e:
            logger.error(f"❌ Interface tunnel direct error: {e}")
            if 'target_sock' in locals():
                target_sock.close()
            return web.Response(status=502, text="Tunnel creation failed")

    async def create_standard_tunnel_direct(self, request, host: str, port: int):
        """Создание стандартного туннеля (прямая версия)"""
        try:
            # Создаем соединение с целевым сервером
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.setblocking(False)

            try:
                await asyncio.get_event_loop().sock_connect(target_sock, (host, port))
                logger.info(f"✅ Connected to {host}:{port} (standard)")
            except OSError as e:
                target_sock.close()
                logger.error(f"❌ Failed to connect to {host}:{port}: {e}")
                return web.Response(status=502, text="Connection failed")

            # Получаем транспорт клиента
            client_transport = request.transport
            if not client_transport:
                target_sock.close()
                return web.Response(status=502, text="No client transport")

            # Отправляем подтверждение
            success_response = b"HTTP/1.1 200 Connection established\r\n\r\n"
            client_transport.write(success_response)
            await asyncio.sleep(0.1)

            logger.info(f"🚀 Starting standard tunnel for {host}:{port}")

            # Запускаем туннель
            await self.run_tunnel(client_transport, target_sock, host, port)

            return web.Response(status=200, text="")

        except Exception as e:
            logger.error(f"❌ Standard tunnel direct error: {e}")
            if 'target_sock' in locals():
                target_sock.close()
            return web.Response(status=502, text="Connection failed")

    def _get_target_url_from_request(self, request):
        """Получение целевого URL из запроса"""
        try:
            # ИСПРАВЛЕНИЕ: Для CONNECT запросов возвращаем путь как есть
            if request.method == 'CONNECT':
                return request.path_qs  # Например "httpbin.org:443"

            # Для прямых HTTP запросов через прокси
            if request.path_qs.startswith('http://') or request.path_qs.startswith('https://'):
                return request.path_qs

            # Для запросов с Host заголовком
            host = request.headers.get('Host')
            if host:
                # Исключаем запросы к самому прокси-серверу
                proxy_hosts = [
                    f'192.168.1.50:{self.port}',
                    f'127.0.0.1:{self.port}',
                    f'localhost:{self.port}'
                ]

                if host not in proxy_hosts:
                    scheme = 'https' if request.secure else 'http'
                    return f"{scheme}://{host}{request.path_qs}"

            return None

        except Exception as e:
            logger.error(f"Error getting target URL: {e}")
            return None

    async def handle_http_via_device_interface(self, request, target_url, device):
        """Обработка HTTP запросов с использованием интерфейса устройства"""
        try:
            device_type = device.get('type')
            interface = device.get('interface') or device.get('usb_interface')

            logger.info(f"Processing via device type: {device_type}, interface: {interface}")

            # Если Android устройство с USB интерфейсом - используем curl
            if device_type == 'android' and interface and interface != 'unknown':
                logger.info(f"Using Android interface routing via {interface}")

                # Используем ту же логику curl что и в proxy_server.py
                curl_result = await self.force_curl_via_interface(request, target_url, interface)

                if curl_result:
                    return web.Response(
                        text=curl_result.get('body', ''),
                        status=curl_result.get('status', 200),
                        headers={
                            **curl_result.get('headers', {}),
                            'X-Dedicated-Proxy-Device': self.device_id,
                            'X-Dedicated-Proxy-Interface': interface
                        }
                    )

            # Fallback к обычному HTTP запросу
            logger.info("Using fallback HTTP client")
            return await self.handle_http_fallback(request, target_url)

        except Exception as e:
            logger.error(f"Error in handle_http_via_device_interface: {e}")
            return await self.handle_http_fallback(request, target_url)

    async def force_curl_via_interface(self, request, target_url: str, interface_name: str):
        """Копия метода из proxy_server.py для выполнения запроса через интерфейс"""
        try:
            logger.info(f"🔧 DEDICATED PROXY: curl via interface: {interface_name}")
            logger.info(f"🎯 Target URL: {target_url}")

            # Получаем данные запроса
            method = request.method
            headers = dict(request.headers)

            # Получаем тело запроса если есть
            body = None
            if method in ['POST', 'PUT', 'PATCH']:
                body = await request.read()

            # Убираем проблемные заголовки
            headers.pop('Host', None)
            headers.pop('Content-Length', None)
            headers.pop('Proxy-Authorization', None)

            # Базовая команда curl
            cmd = [
                "curl",
                "--interface", interface_name,
                "--silent",
                "--show-error",
                "--fail-with-body",
                "--max-time", "30",
                "--connect-timeout", "10",
                "--location",
                "--compressed",
                "--header", "Accept: application/json, text/plain, */*",
                "--header", "User-Agent: Dedicated-Proxy-Interface/1.0",
                "--write-out", "\\nHTTPSTATUS:%{http_code}\\nTIME:%{time_total}\\n"
            ]

            # Добавляем HTTP метод
            if method.upper() != "GET":
                cmd.extend(["-X", method.upper()])

            # Добавляем заголовки
            for key, value in headers.items():
                if key.lower() not in ['host', 'content-length', 'connection', 'proxy-authorization']:
                    cmd.extend(["--header", f"{key}: {value}"])

            # Добавляем данные для POST/PUT
            if body:
                cmd.extend(["--data-binary", "@-"])

            cmd.append(target_url)

            logger.info(f"🔧 Executing dedicated proxy curl command...")

            # Выполняем команду
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if body else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Отправляем данные если есть
            stdout, stderr = await process.communicate(input=body)

            if process.returncode != 0:
                logger.error(f"❌ Dedicated proxy curl FAILED! Return code: {process.returncode}")
                logger.error(f"❌ stderr: {stderr.decode()}")
                return None

            # Декодируем результат
            output = stdout.decode().strip()
            logger.info(f"🎉 Dedicated proxy curl SUCCESS! Output length: {len(output)}")

            # Парсим результат
            lines = output.split('\n')
            status_code = 200
            response_time = 0.0
            body_lines = []

            # Извлекаем метаданные и тело ответа
            for line in lines:
                if line.startswith('HTTPSTATUS:'):
                    status_code = int(line.split(':')[1])
                elif line.startswith('TIME:'):
                    response_time = float(line.split(':')[1])
                elif line.strip():  # Пропускаем пустые строки
                    body_lines.append(line)

            response_body = '\n'.join(body_lines)

            logger.info(f"🎉 SUCCESS! Dedicated proxy interface {interface_name} -> Status {status_code}")

            return {
                'body': response_body,
                'status': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Proxy-Interface': interface_name,
                    'X-Proxy-Via': 'dedicated-curl'
                },
                'response_time': response_time
            }

        except Exception as e:
            logger.error(f"❌ Exception in dedicated proxy force_curl_via_interface: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return None

    async def handle_http_fallback(self, request, target_url):
        """Fallback HTTP обработчик"""
        try:
            # Подготовка заголовков
            headers = dict(request.headers)
            headers.pop('Proxy-Authorization', None)
            headers.pop('Host', None)

            # Выполнение запроса через обычный HTTP клиент
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=await request.read() if request.content_length else None
                ) as response:
                    # Подготовка ответа
                    body = await response.read()

                    return web.Response(
                        status=response.status,
                        headers={
                            **dict(response.headers),
                            'X-Dedicated-Proxy-Device': self.device_id,
                            'X-Dedicated-Proxy-Fallback': 'true'
                        },
                        body=body
                    )

        except Exception as e:
            logger.error(
                "Error in dedicated proxy fallback",
                device_id=self.device_id,
                target_url=target_url,
                error=str(e)
            )
            return web.Response(
                status=502,
                text="Bad Gateway"
            )


class DedicatedProxyManager:
    """Менеджер индивидуальных прокси-серверов"""

    def __init__(self, device_manager):
        self.device_manager = device_manager
        self.proxy_servers: Dict[str, DedicatedProxyServer] = {}
        self.used_ports: Set[int] = set()
        self.port_range_start = 6001
        self.port_range_end = 7000
        self._running = False

    async def start(self):
        """Запуск менеджера индивидуальных прокси"""
        if self._running:
            return

        logger.info("Starting dedicated proxy manager")

        # Загрузка существующих устройств с настроенными прокси
        await self.load_existing_proxies()

        self._running = True
        logger.info("Dedicated proxy manager started")

    async def stop(self):
        """Остановка менеджера индивидуальных прокси"""
        if not self._running:
            return

        logger.info("Stopping dedicated proxy manager")

        # Остановка всех прокси-серверов
        for proxy_server in self.proxy_servers.values():
            await proxy_server.stop()

        self.proxy_servers.clear()
        self.used_ports.clear()
        self._running = False

        logger.info("Dedicated proxy manager stopped")

    async def load_existing_proxies(self):
        """Загрузка существующих прокси-настроек из базы данных"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice).where(
                    ProxyDevice.proxy_enabled == True,
                    ProxyDevice.dedicated_port.is_not(None)
                )
                result = await db.execute(stmt)
                devices = result.scalars().all()

                logger.info(f"Found {len(devices)} devices with dedicated proxies in database")

                for device in devices:
                    logger.info(f"Loading proxy for device: {device.name} on port {device.dedicated_port}")
                    try:
                        # ИСПРАВЛЕНИЕ: Вызываем правильный метод на правильном объекте
                        await self.create_dedicated_proxy(
                            device_id=device.name,  # Используем name устройства
                            port=device.dedicated_port,
                            username=device.proxy_username,
                            password=device.proxy_password
                        )
                        logger.info(f"✅ Successfully loaded proxy for {device.name}")
                    except Exception as e:
                        logger.error(f"❌ Failed to load proxy for {device.name}: {e}")

        except Exception as e:
            logger.error("Error loading existing proxies", error=str(e))

    async def create_dedicated_proxy(self, device_id: str, port: Optional[int] = None,
                                     username: Optional[str] = None, password: Optional[str] = None):
        """Создание индивидуального прокси для устройства"""
        try:
            # Валидация порта
            if port is not None:
                if not (self.port_range_start <= port <= self.port_range_end):
                    raise ValueError(f"Port must be in range {self.port_range_start}-{self.port_range_end}")

                # Проверка уникальности порта
                if port in self.used_ports or not await self.is_port_available(port):
                    raise ValueError(f"Port {port} is already in use")

            # Генерация параметров если не указаны
            if port is None:
                port = await self.allocate_port()

            if username is None:
                username = f"device_{device_id[:8]}"

            if password is None:
                import secrets
                password = secrets.token_urlsafe(16)

            # Проверка доступности порта (повторная проверка для автоматически выделенного)
            if port in self.used_ports or not await self.is_port_available(port):
                raise ValueError(f"Port {port} is not available")

            # Создание прокси-сервера
            proxy_server = DedicatedProxyServer(
                device_id=device_id,
                port=port,
                username=username,
                password=password,
                device_manager=self.device_manager
            )

            # Запуск сервера
            await proxy_server.start()

            # Сохранение в памяти и базе данных
            self.proxy_servers[device_id] = proxy_server
            self.used_ports.add(port)

            await self.save_proxy_config(device_id, port, username, password)

            logger.info(
                "Dedicated proxy created",
                device_id=device_id,
                port=port,
                username=username
            )

            return {
                "device_id": device_id,
                "port": port,
                "username": username,
                "password": password,
                "proxy_url": f"http://192.168.1.50:{port}",
                "status": "running"
            }

        except Exception as e:
            logger.error(
                "Error creating dedicated proxy",
                device_id=device_id,
                error=str(e)
            )
            raise

    async def remove_dedicated_proxy(self, device_id: str):
        """Удаление индивидуального прокси для устройства"""
        try:
            proxy_server = self.proxy_servers.get(device_id)
            if proxy_server:
                port = proxy_server.port
                await proxy_server.stop()

                del self.proxy_servers[device_id]
                self.used_ports.discard(port)

                # Удаление из базы данных
                await self.remove_proxy_config(device_id)

                logger.info(
                    "Dedicated proxy removed",
                    device_id=device_id,
                    port=port
                )

        except Exception as e:
            logger.error(
                "Error removing dedicated proxy",
                device_id=device_id,
                error=str(e)
            )
            raise

    async def get_device_proxy_info(self, device_id: str):
        """Получение информации о прокси устройства"""
        proxy_server = self.proxy_servers.get(device_id)
        if not proxy_server:
            return None

        return {
            "device_id": device_id,
            "port": proxy_server.port,
            "username": proxy_server.username,
            "password": proxy_server.password,
            "proxy_url": f"http://192.168.1.50:{proxy_server.port}",
            "status": "running" if proxy_server.is_running() else "stopped"
        }

    async def list_all_dedicated_proxies(self):
        """Список всех индивидуальных прокси"""
        proxies = []
        for device_id, proxy_server in self.proxy_servers.items():
            proxy_info = await self.get_device_proxy_info(device_id)
            if proxy_info:
                proxies.append(proxy_info)
        return proxies

    async def allocate_port(self) -> int:
        """Выделение свободного порта"""
        for port in range(self.port_range_start, self.port_range_end + 1):
            if port not in self.used_ports and await self.is_port_available(port):
                return port
        raise RuntimeError("No available ports in range")

    async def is_port_available(self, port: int) -> bool:
        """Проверка доступности порта"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return True
        except OSError:
            return False

    async def save_proxy_config(self, device_id: str, port: int, username: str, password: str):
        """Сохранение конфигурации прокси в базу данных"""
        try:
            async with AsyncSessionLocal() as db:
                # ИСПРАВЛЕНИЕ: Ищем устройство по name, а не пытаемся преобразовать device_id в UUID
                stmt = select(ProxyDevice).where(ProxyDevice.name == device_id)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()

                if not device:
                    raise ValueError(f"Device with name {device_id} not found in database")

                # Используем реальный UUID устройства
                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == device.id  # Используем найденный UUID
                ).values(
                    dedicated_port=port,
                    proxy_username=username,
                    proxy_password=password,
                    proxy_enabled=True
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error(
                "Error saving proxy config",
                device_id=device_id,
                error=str(e)
            )
            raise

    async def remove_proxy_config(self, device_id: str):
        """Удаление конфигурации прокси из базы данных"""
        try:
            async with AsyncSessionLocal() as db:
                # ИСПРАВЛЕНИЕ: Ищем устройство по name
                stmt = select(ProxyDevice).where(ProxyDevice.name == device_id)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()

                if not device:
                    raise ValueError(f"Device with name {device_id} not found in database")

                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == device.id  # Используем найденный UUID
                ).values(
                    dedicated_port=None,
                    proxy_username=None,
                    proxy_password=None,
                    proxy_enabled=False
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error(
                "Error removing proxy config",
                device_id=device_id,
                error=str(e)
            )
            raise

    async def verify_proxy_server_running(self, device_id: str) -> bool:
        """Проверка, что dedicated proxy сервер запущен и отвечает"""
        try:
            proxy_server = self.proxy_servers.get(device_id)
            if not proxy_server or not proxy_server.is_running():
                logger.error(f"Proxy server for {device_id} not running")
                return False

            # Проверяем, что порт слушается
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                result = s.connect_ex(('192.168.1.50', proxy_server.port))
                if result != 0:
                    logger.error(f"Proxy server port {proxy_server.port} not listening")
                    return False

            logger.info(f"Proxy server for {device_id} is running on port {proxy_server.port}")
            return True

        except Exception as e:
            logger.error(f"Error verifying proxy server: {e}")
            return False
