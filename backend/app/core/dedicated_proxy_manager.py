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
import subprocess
import os

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
        """Запуск индивидуального прокси-сервера с правильной настройкой middleware"""
        if self._running:
            logger.info(f"Dedicated proxy server for {self.device_id} already running on port {self.port}")
            return

        try:
            logger.info(f"🚀 Starting dedicated proxy server for device {self.device_id} on port {self.port}")

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

            # ГЛАВНЫЙ MIDDLEWARE для аутентификации и CONNECT обработки
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

                # 🔥 ГЛАВНОЕ ИСПРАВЛЕНИЕ: Специальная обработка CONNECT
                if request.method == 'CONNECT':
                    logger.info(f"🔗 CONNECT intercepted in middleware - creating tunnel!")

                    try:
                        # Запускаем proxy_handler в фоне
                        asyncio.create_task(self.proxy_handler(request))

                        # Возвращаем заглушку, чтобы aiohttp не обрабатывал дальше
                        logger.info("🔄 CONNECT handler started in background")

                        # Возвращаем минимальный ответ
                        return web.Response(status=200, text="")

                    except Exception as e:
                        logger.error(f"❌ CONNECT handler error: {e}")
                        return web.Response(status=502, text="Bad Gateway")

                # Для остальных запросов передаем в роутер
                return await handler(request)

            # КРИТИЧНО: Добавляем middleware в правильном порядке
            self.app.middlewares.append(auth_and_connect_middleware)

            # МАКСИМАЛЬНО ПРОСТЫЕ РОУТЫ
            # Один универсальный обработчик
            async def universal_handler(request):
                logger.info(f"🎯 UNIVERSAL HANDLER: {request.method} '{request.path_qs}'")
                return await self.proxy_handler(request)

            # Регистрируем роуты для всех HTTP методов
            for method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']:
                self.app.router.add_route(method, '/{path:.*}', universal_handler)
                self.app.router.add_route(method, '/', universal_handler)

            logger.info(f"📋 Registered universal route for {self.device_id}")

            # Запуск сервера с улучшенными настройками сокета
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(
                self.runner,
                '0.0.0.0',
                self.port,
                reuse_address=True,
                reuse_port=True
            )
            await self.site.start()

            self._running = True

            # Проверяем запуск с более детальной диагностикой
            await asyncio.sleep(0.2)

            # Проверка через socket
            test_success = False
            for attempt in range(3):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(2)
                        result = s.connect_ex(('127.0.0.1', self.port))
                        if result == 0:
                            test_success = True
                            break
                        else:
                            logger.warning(f"Connection test failed (attempt {attempt + 1}): {result}")
                            await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Connection test error (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(0.5)

            if test_success:
                logger.info(f"✅ Dedicated proxy server started and verified on port {self.port}")
            else:
                logger.error(f"❌ Dedicated proxy server started but connection test failed on port {self.port}")

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
        """Отладочная версия обработчика с настоящим туннелем"""
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

                # НАСТОЯЩИЙ ТУННЕЛЬ вместо простого ответа
                return await self.handle_connect_direct(request, device, target)

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

    async def handle_connect_direct(self, request, device, target: str):
        """CONNECT обработка с дублированием сокета для обхода transport контроля"""
        try:
            # Парсим хост и порт из target
            if ':' in target:
                host, port = target.rsplit(':', 1)
                port = int(port)
            else:
                host = target
                port = 443

            logger.info(f"🔗 RAW CONNECT tunnel: {host}:{port} via device {self.device_id}")

            # Получаем интерфейс устройства для туннелирования
            interface = device.get('interface') or device.get('usb_interface')

            # Создаем соединение с целевым сервером
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Привязываем к интерфейсу если возможно
            if interface and interface != 'unknown':
                try:
                    target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
                    logger.info(f"✅ Socket bound to interface: {interface}")
                except OSError as e:
                    logger.warning(f"⚠️  Failed to bind to interface {interface}: {e}")

            # Подключаемся к целевому серверу
            target_sock.setblocking(False)
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

            # КРИТИЧНО: Отправляем ответ 200 через transport
            success_response = b"HTTP/1.1 200 Connection established\r\n\r\n"
            client_transport.write(success_response)

            logger.info(f"🚀 Starting RAW tunnel relay")

            # НОВЫЙ ПОДХОД: Дублируем сокет для независимого управления
            await self.create_socket_tunnel(client_transport, target_sock, host, port)

            return None

        except Exception as e:
            logger.error(f"❌ RAW CONNECT error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return web.Response(status=502, text="Bad Gateway")

    async def create_socket_tunnel(self, client_transport, target_sock, host: str, port: int):
        """Создание туннеля с дублированием клиентского сокета"""
        try:
            logger.info(f"🔧 Creating socket tunnel to {host}:{port}")

            # Получаем исходный сокет из транспорта
            original_sock = client_transport.get_extra_info('socket')
            if not original_sock:
                raise Exception("No client socket in transport")

            logger.info(f"✅ Original socket: {original_sock}")

            # КЛЮЧЕВОЕ РЕШЕНИЕ: Дублируем file descriptor
            try:
                # Получаем file descriptor
                original_fd = original_sock.fileno()
                logger.info(f"✅ Original FD: {original_fd}")

                # Дублируем file descriptor
                new_fd = os.dup(original_fd)
                logger.info(f"✅ Duplicated FD: {new_fd}")

                # Создаем новый сокет из дублированного FD
                new_sock = socket.fromfd(new_fd, socket.AF_INET, socket.SOCK_STREAM)
                new_sock.setblocking(False)

                logger.info(f"✅ New independent socket: {new_sock}")

            except Exception as e:
                logger.error(f"❌ Socket duplication failed: {e}")
                # Fallback: попробуем использовать transport напрямую
                return await self.create_transport_tunnel(client_transport, target_sock, host, port)

            # Ждем немного чтобы aiohttp обработал ответ 200
            await asyncio.sleep(0.2)

            # Теперь запускаем туннель с новым независимым сокетом
            await self.run_independent_tunnel(new_sock, target_sock, host, port)

        except Exception as e:
            logger.error(f"❌ Socket tunnel error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")

            try:
                target_sock.close()
            except:
                pass

    async def run_independent_tunnel(self, client_sock, target_sock, host: str, port: int):
        """Туннель с полностью независимыми сокетами"""
        try:
            logger.info(f"🔄 Starting INDEPENDENT tunnel to {host}:{port}")
            logger.info(f"✅ Client socket: {client_sock}")
            logger.info(f"✅ Target socket: {target_sock}")

            # Функция передачи данных между независимыми сокетами
            async def forward_data_independent(from_sock, to_sock, direction):
                try:
                    total_bytes = 0
                    buffer_size = 8192

                    while True:
                        try:
                            # Читаем данные через asyncio
                            data = await asyncio.get_event_loop().sock_recv(from_sock, buffer_size)
                            if not data:
                                logger.debug(f"📤 IND {direction}: EOF")
                                break

                            # Отправляем данные через asyncio
                            await asyncio.get_event_loop().sock_sendall(to_sock, data)
                            total_bytes += len(data)

                            # Логируем SSL handshake
                            if total_bytes < 1024:  # Первые 1KB
                                logger.debug(f"🔐 SSL {direction}: {len(data)} bytes, total: {total_bytes}")

                        except (ConnectionResetError, BrokenPipeError, OSError) as e:
                            if e.errno in (9, 104, 32, 107):  # Различные ошибки закрытия
                                logger.debug(f"📤 IND {direction}: connection closed ({e})")
                            else:
                                logger.warning(f"📤 IND {direction}: socket error {e}")
                            break

                    logger.info(f"✅ IND {direction}: finished, {total_bytes} bytes total")

                except asyncio.CancelledError:
                    logger.debug(f"🚫 IND {direction}: cancelled")
                except Exception as e:
                    logger.error(f"❌ IND {direction}: error {e}")

            # Создаем задачи для передачи в обе стороны
            client_to_server = asyncio.create_task(
                forward_data_independent(client_sock, target_sock, f"client -> {host}:{port}")
            )
            server_to_client = asyncio.create_task(
                forward_data_independent(target_sock, client_sock, f"{host}:{port} -> client")
            )

            # Ждем завершения любой из задач
            try:
                done, pending = await asyncio.wait(
                    [client_to_server, server_to_client],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=600  # 10 минут таймаут
                )

                logger.info(f"🔚 Independent tunnel completed for {host}:{port}")

            except asyncio.TimeoutError:
                logger.info(f"⏰ Independent tunnel timeout for {host}:{port}")
            finally:
                # Отменяем оставшиеся задачи
                for task in [client_to_server, server_to_client]:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                # Закрываем сокеты
                try:
                    client_sock.close()
                except:
                    pass
                try:
                    target_sock.close()
                except:
                    pass

            logger.info(f"🏁 Independent tunnel ended for {host}:{port}")

        except Exception as e:
            logger.error(f"❌ Independent tunnel error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")

            # Закрываем сокеты при ошибке
            try:
                client_sock.close()
            except:
                pass
            try:
                target_sock.close()
            except:
                pass

    async def create_transport_tunnel(self, client_transport, target_sock, host: str, port: int):
        """Fallback туннель используя transport напрямую"""
        try:
            logger.info(f"🔄 Starting TRANSPORT tunnel to {host}:{port}")

            # Ждем чтобы ответ 200 отправился
            await asyncio.sleep(0.3)

            # Читаем данные из transport и отправляем в target
            async def read_from_transport():
                try:
                    total_bytes = 0
                    while True:
                        try:
                            # Пытаемся прочитать из transport
                            # Это может не работать, но попробуем
                            await asyncio.sleep(0.1)  # Небольшая задержка

                            # Если transport закрылся, завершаем
                            if client_transport.is_closing():
                                logger.info("📤 Transport closed")
                                break

                        except Exception as e:
                            logger.info(f"📤 Transport read error: {e}")
                            break

                    logger.info(f"✅ Transport reader finished: {total_bytes} bytes")

                except Exception as e:
                    logger.error(f"❌ Transport reader error: {e}")

            # Читаем данные из target и отправляем в transport
            async def read_from_target():
                try:
                    total_bytes = 0
                    buffer_size = 8192

                    while True:
                        try:
                            data = await asyncio.get_event_loop().sock_recv(target_sock, buffer_size)
                            if not data:
                                logger.info("📤 Target EOF")
                                break

                            # Пытаемся отправить через transport
                            client_transport.write(data)
                            total_bytes += len(data)

                            if total_bytes < 1024:
                                logger.debug(f"🔐 Target->Client: {len(data)} bytes")

                        except Exception as e:
                            logger.info(f"📤 Target read error: {e}")
                            break

                    logger.info(f"✅ Target reader finished: {total_bytes} bytes")

                except Exception as e:
                    logger.error(f"❌ Target reader error: {e}")

            # Запускаем обе задачи
            transport_task = asyncio.create_task(read_from_transport())
            target_task = asyncio.create_task(read_from_target())

            try:
                await asyncio.wait(
                    [transport_task, target_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=300
                )
            except asyncio.TimeoutError:
                logger.info("⏰ Transport tunnel timeout")
            finally:
                transport_task.cancel()
                target_task.cancel()

                try:
                    target_sock.close()
                except:
                    pass

            logger.info(f"🏁 Transport tunnel ended for {host}:{port}")

        except Exception as e:
            logger.error(f"❌ Transport tunnel error: {e}")

    async def hijack_connection_for_tunnel(self, client_transport, target_sock, host: str, port: int):
        """Захват соединения и отключение HTTP протокола для raw туннеля"""
        try:
            logger.info(f"🔧 Hijacking connection for tunnel to {host}:{port}")

            # Получаем сокет из транспорта
            client_sock = client_transport.get_extra_info('socket')
            if not client_sock:
                raise Exception("No client socket in transport")

            logger.info(f"✅ Client socket extracted: {client_sock}")

            # КРИТИЧНО: Полностью отключаем HTTP протокол
            try:
                # Останавливаем transport и освобождаем сокет
                if hasattr(client_transport, '_protocol'):
                    protocol = client_transport._protocol

                    # Отключаем все HTTP парсеры
                    if hasattr(protocol, '_request_parser'):
                        protocol._request_parser = None
                    if hasattr(protocol, '_upgrade'):
                        protocol._upgrade = True
                    if hasattr(protocol, '_message_tail'):
                        protocol._message_tail = b''

                    # Отключаем протокол от сокета (но не закрываем сокет)
                    if hasattr(protocol, 'transport'):
                        protocol.transport = None

                    logger.info("🔧 HTTP protocol completely disabled")

            except Exception as e:
                logger.warning(f"⚠️  Error disabling HTTP protocol: {e}")

            # Ждем немного чтобы aiohttp завершил текущую обработку
            await asyncio.sleep(0.1)

            # Устанавливаем сокеты в неблокирующий режим
            client_sock.setblocking(False)
            target_sock.setblocking(False)

            logger.info(f"🚀 Starting raw TCP tunnel")

            # Запускаем чистый TCP туннель БЕЗ участия aiohttp
            await self.run_pure_tcp_tunnel(client_sock, target_sock, host, port)

        except Exception as e:
            logger.error(f"❌ Connection hijack error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")

            # Закрываем сокеты при ошибке
            try:
                target_sock.close()
            except:
                pass

    async def run_pure_tcp_tunnel(self, client_sock, target_sock, host: str, port: int):
        """Чистый TCP туннель без участия aiohttp"""
        try:
            logger.info(f"🔄 Starting PURE TCP tunnel to {host}:{port}")

            # Функция передачи данных
            async def forward_data_pure(from_sock, to_sock, direction):
                try:
                    total_bytes = 0
                    buffer_size = 8192

                    while True:
                        try:
                            # Читаем данные через asyncio loop
                            data = await asyncio.get_event_loop().sock_recv(from_sock, buffer_size)
                            if not data:
                                logger.debug(f"📤 PURE {direction}: EOF")
                                break

                            # Отправляем данные через asyncio loop
                            await asyncio.get_event_loop().sock_sendall(to_sock, data)
                            total_bytes += len(data)

                            # Логируем SSL handshake
                            if total_bytes < 1024:  # Первые 1KB (SSL handshake)
                                logger.debug(f"🔐 SSL {direction}: {len(data)} bytes, total: {total_bytes}")

                        except (ConnectionResetError, BrokenPipeError, OSError) as e:
                            if e.errno in (9, 104, 32, 107):  # EBADF, ECONNRESET, EPIPE, ENOTCONN
                                logger.debug(f"📤 PURE {direction}: connection closed ({e})")
                            else:
                                logger.warning(f"📤 PURE {direction}: socket error {e}")
                            break

                    logger.info(f"✅ PURE {direction}: finished, {total_bytes} bytes total")

                except asyncio.CancelledError:
                    logger.debug(f"🚫 PURE {direction}: cancelled")
                except Exception as e:
                    logger.error(f"❌ PURE {direction}: error {e}")

            # Создаем задачи для передачи в обе стороны
            client_to_server = asyncio.create_task(
                forward_data_pure(client_sock, target_sock, f"client -> {host}:{port}")
            )
            server_to_client = asyncio.create_task(
                forward_data_pure(target_sock, client_sock, f"{host}:{port} -> client")
            )

            # Ждем завершения любой из задач
            try:
                done, pending = await asyncio.wait(
                    [client_to_server, server_to_client],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=600  # 10 минут таймаут
                )

                logger.info(f"🔚 Pure TCP tunnel completed for {host}:{port}")

            except asyncio.TimeoutError:
                logger.info(f"⏰ Pure TCP tunnel timeout for {host}:{port}")
            finally:
                # Отменяем оставшиеся задачи
                for task in [client_to_server, server_to_client]:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                # Закрываем сокеты
                try:
                    client_sock.close()
                except:
                    pass
                try:
                    target_sock.close()
                except:
                    pass

            logger.info(f"🏁 Pure TCP tunnel ended for {host}:{port}")

        except Exception as e:
            logger.error(f"❌ Pure TCP tunnel error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")

            # Закрываем сокеты при ошибке
            try:
                client_sock.close()
            except:
                pass
            try:
                target_sock.close()
            except:
                pass

    async def run_raw_tunnel_transport(self, client_transport, target_sock, host: str, port: int):
        """Запуск сырого TCP туннеля используя transport напрямую"""
        client_sock = None
        try:
            logger.info(f"🔄 Starting RAW TCP tunnel to {host}:{port} via transport")

            # Получаем клиентский сокет из транспорта
            client_sock = client_transport.get_extra_info('socket')
            if not client_sock:
                raise Exception("No client socket in transport")

            # Устанавливаем сокеты в неблокирующий режим
            client_sock.setblocking(False)
            target_sock.setblocking(False)

            logger.info(f"✅ Client socket: {client_sock}")
            logger.info(f"✅ Target socket: {target_sock}")

            # Пытаемся закрыть HTTP протокол
            try:
                if hasattr(client_transport, '_protocol'):
                    protocol = client_transport._protocol
                    if hasattr(protocol, 'close'):
                        # НЕ закрываем протокол полностью, а только отключаем HTTP парсер
                        if hasattr(protocol, '_request_parser'):
                            protocol._request_parser = None
                        logger.info("🔧 Disabled HTTP parser in protocol")
            except Exception as e:
                logger.warning(f"⚠️  Failed to disable HTTP parser: {e}")

            # Функция передачи данных
            async def forward_data_transport(from_sock, to_sock, direction):
                try:
                    total_bytes = 0
                    buffer_size = 8192

                    while True:
                        try:
                            # Читаем данные
                            data = await asyncio.get_event_loop().sock_recv(from_sock, buffer_size)
                            if not data:
                                logger.debug(f"📤 {direction}: EOF")
                                break

                            # Отправляем данные
                            await asyncio.get_event_loop().sock_sendall(to_sock, data)
                            total_bytes += len(data)

                            # Логируем SSL handshake
                            if total_bytes < 1024:  # Первые 1KB
                                logger.debug(f"🔐 SSL {direction}: {len(data)} bytes, total: {total_bytes}")

                        except (ConnectionResetError, BrokenPipeError, OSError) as e:
                            if e.errno in (9, 104, 32):  # EBADF, ECONNRESET, EPIPE
                                logger.debug(f"📤 {direction}: connection closed ({e})")
                            else:
                                logger.warning(f"📤 {direction}: socket error {e}")
                            break

                    logger.info(f"✅ {direction}: finished, {total_bytes} bytes total")

                except asyncio.CancelledError:
                    logger.debug(f"🚫 {direction}: cancelled")
                except Exception as e:
                    logger.error(f"❌ {direction}: error {e}")

            # Создаем задачи для передачи в обе стороны
            client_to_server = asyncio.create_task(
                forward_data_transport(client_sock, target_sock, f"client -> {host}:{port}")
            )
            server_to_client = asyncio.create_task(
                forward_data_transport(target_sock, client_sock, f"{host}:{port} -> client")
            )

            # Ждем завершения любой из задач
            try:
                done, pending = await asyncio.wait(
                    [client_to_server, server_to_client],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=600  # 10 минут таймаут
                )

                logger.info(f"🔚 Transport tunnel completed for {host}:{port}")

            except asyncio.TimeoutError:
                logger.info(f"⏰ Transport tunnel timeout for {host}:{port}")
            finally:
                # Отменяем оставшиеся задачи
                for task in [client_to_server, server_to_client]:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

        except Exception as e:
            logger.error(f"❌ Transport tunnel error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
        finally:
            # Закрываем сокеты
            try:
                if client_sock:
                    client_sock.close()
            except:
                pass
            try:
                target_sock.close()
            except:
                pass
            try:
                client_transport.close()
            except:
                pass

            logger.info(f"🏁 Transport tunnel ended for {host}:{port}")

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

    def is_running(self):
        """Проверка статуса работы сервера"""
        return self._running

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
        """Загрузка существующих прокси-настроек из базы данных с принудительной очисткой портов"""
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
                        port = device.dedicated_port

                        # Проверяем доступность порта
                        port_available = await self.is_port_available(port)

                        if not port_available:
                            logger.warning(f"Port {port} is not available, trying to force cleanup...")

                            # Попробуем принудительно освободить порт
                            freed = await self.force_free_port(port)

                            if not freed:
                                logger.error(f"❌ Could not free port {port}, skipping device {device.name}")
                                continue

                        # Создаем прокси с небольшой задержкой
                        await asyncio.sleep(0.5)  # Даем время на освобождение порта

                        await self.create_dedicated_proxy(
                            device_id=device.name,
                            port=port,
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
        """Создание индивидуального прокси для устройства с улучшенной проверкой портов"""
        try:
            # Валидация порта
            if port is not None:
                if not (self.port_range_start <= port <= self.port_range_end):
                    raise ValueError(f"Port must be in range {self.port_range_start}-{self.port_range_end}")

                # Проверка уникальности порта
                if port in self.used_ports:
                    logger.warning(f"Port {port} already in used_ports set, removing...")
                    self.used_ports.discard(port)  # Убираем из памяти

                # Двойная проверка доступности
                if not await self.is_port_available(port):
                    logger.warning(f"Port {port} is not available, trying to free it...")
                    freed = await self.force_free_port(port)
                    if not freed:
                        raise ValueError(f"Port {port} is not available and cannot be freed")

            # Генерация параметров если не указаны
            if port is None:
                port = await self.allocate_port()

            if username is None:
                username = f"device_{device_id[:8]}"

            if password is None:
                import secrets
                password = secrets.token_urlsafe(16)

            # Финальная проверка порта перед созданием сервера
            if not await self.is_port_available(port):
                raise ValueError(f"Port {port} is not available for creating proxy server")

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
        """Улучшенная проверка доступности порта"""
        try:
            # Проверяем через socket bind
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(('0.0.0.0', port))
                    logger.debug(f"Port {port} is available via socket bind")
                    return True
                except OSError as e:
                    logger.debug(f"Port {port} bind failed: {e}")

                    # Дополнительная проверка через netstat
                    try:
                        import subprocess
                        result = subprocess.run(
                            ['netstat', '-tuln'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if f":{port} " in result.stdout:
                            logger.debug(f"Port {port} is in use according to netstat")
                            return False
                        else:
                            logger.debug(f"Port {port} not found in netstat, may be available")
                            # Попробуем с SO_REUSEPORT
                            try:
                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                                    s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                                    s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                                    s2.bind(('0.0.0.0', port))
                                    logger.debug(f"Port {port} available with SO_REUSEPORT")
                                    return True
                            except OSError:
                                logger.debug(f"Port {port} still not available with SO_REUSEPORT")
                                return False
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        logger.debug(f"netstat check failed for port {port}")
                        return False

                    return False

        except Exception as e:
            logger.error(f"Error checking port {port} availability: {e}")
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

    async def force_free_port(self, port: int) -> bool:
        """Принудительное освобождение порта"""
        try:
            logger.info(f"🔧 Trying to force free port {port}")

            # Найдем процессы, использующие порт
            try:
                import subprocess

                # Используем lsof для поиска процессов
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    logger.info(f"Found processes using port {port}: {pids}")

                    for pid in pids:
                        if pid.strip():
                            try:
                                logger.info(f"Attempting to kill process {pid}")
                                subprocess.run(['kill', '-TERM', pid.strip()], timeout=5)
                                await asyncio.sleep(1)  # Даем время на graceful shutdown

                                # Проверяем, что процесс завершился
                                check_result = subprocess.run(
                                    ['kill', '-0', pid.strip()],
                                    capture_output=True,
                                    timeout=2
                                )

                                if check_result.returncode == 0:
                                    logger.warning(f"Process {pid} still running, force killing")
                                    subprocess.run(['kill', '-KILL', pid.strip()], timeout=5)

                            except subprocess.TimeoutExpired:
                                logger.warning(f"Timeout killing process {pid}")
                            except Exception as e:
                                logger.warning(f"Error killing process {pid}: {e}")

                # Ждем немного и проверяем снова
                await asyncio.sleep(2)
                return await self.is_port_available(port)

            except (subprocess.TimeoutExpired, FileNotFoundError):
                logger.warning(f"lsof not available or timeout, trying alternative method")

                # Альтернативный метод через netstat + grep
                try:
                    result = subprocess.run(
                        ['sh', '-c', f'netstat -tulpn | grep ":{port} " | awk \'{{print $7}}\' | cut -d/ -f1'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )

                    if result.stdout.strip():
                        pids = [pid.strip() for pid in result.stdout.strip().split('\n') if
                                pid.strip() and pid.strip() != '-']
                        for pid in pids:
                            try:
                                subprocess.run(['kill', '-TERM', pid], timeout=5)
                            except:
                                pass

                        await asyncio.sleep(2)
                        return await self.is_port_available(port)

                except Exception as e:
                    logger.warning(f"Alternative port cleanup method failed: {e}")

                return False

        except Exception as e:
            logger.error(f"Error in force_free_port for port {port}: {e}")
            return False
