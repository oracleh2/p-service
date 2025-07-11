# backend/app/core/dedicated_proxy_server.py

import asyncio
import base64
import socket
import os
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class DedicatedProxyServer:
    """Индивидуальный прокси-сервер для конкретного устройства на чистом TCP"""

    def __init__(self, device_id: str, port: int, username: str, password: str, device_manager, modem_manager=None):
        self.device_id = device_id
        self.port = port
        self.username = username
        self.password = password
        self.device_manager = device_manager
        self.modem_manager = modem_manager
        self.server = None
        self._running = False

    async def start(self):
        """Запуск RAW TCP прокси-сервера"""
        if self._running:
            logger.info(f"Dedicated proxy server for {self.device_id} already running on port {self.port}")
            return

        try:
            logger.info(f"🚀 Starting RAW TCP proxy server for device {self.device_id} on port {self.port}")

            # Создаем RAW TCP сервер вместо aiohttp
            await self.start_raw_tcp_server()

            self._running = True

            # Проверяем запуск
            await asyncio.sleep(0.2)
            test_success = await self.verify_server_listening()

            if test_success:
                logger.info(f"✅ RAW TCP proxy server started and verified on port {self.port}")
            else:
                logger.error(f"❌ RAW TCP proxy server started but not responding on port {self.port}")

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

    async def start_raw_tcp_server(self):
        """Запуск сырого TCP сервера для полного контроля"""
        try:
            # Создаем TCP сервер
            self.server = await asyncio.start_server(
                self.handle_raw_connection,
                '0.0.0.0',
                self.port,
                reuse_address=True,
                reuse_port=True
            )

            logger.info(f"🔧 Raw TCP server listening on port {self.port}")

            # Запускаем сервер в фоне
            asyncio.create_task(self.server.serve_forever())

        except Exception as e:
            logger.error(f"❌ Failed to start raw TCP server: {e}")
            raise

    async def verify_server_listening(self):
        """Проверка, что сервер слушает на порту"""
        try:
            for attempt in range(3):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(2)
                        result = s.connect_ex(('127.0.0.1', self.port))
                        if result == 0:
                            return True
                        else:
                            logger.debug(f"Connection test failed (attempt {attempt + 1}): {result}")
                            await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug(f"Connection test error (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(0.5)
            return False
        except Exception as e:
            logger.error(f"Error verifying server: {e}")
            return False

    async def handle_raw_connection(self, reader, writer):
        """Обработка сырого TCP соединения"""
        try:
            client_addr = writer.get_extra_info('peername')
            logger.debug(f"🔌 New raw connection from {client_addr}")

            # Читаем первый HTTP запрос
            request_data = await self.read_http_request(reader)
            if not request_data:
                writer.close()
                return

            # Парсим HTTP запрос
            request_info = self.parse_http_request(request_data)
            if not request_info:
                await self.send_http_error(writer, 400, "Bad Request")
                return

            logger.debug(f"📝 Request: {request_info['method']} {request_info['path']}")

            # Проверяем аутентификацию
            if not self.authenticate_request(request_info.get('headers', {})):
                logger.info(f"❌ Authentication failed for {client_addr}")
                await self.send_http_error(writer, 407, "Proxy Authentication Required")
                return

            logger.debug(f"✅ Authentication successful for {client_addr}")

            # Обрабатываем запрос
            if request_info['method'] == 'CONNECT':
                await self.handle_raw_connect(reader, writer, request_info)
            else:
                await self.handle_raw_http(reader, writer, request_info)

        except Exception as e:
            logger.error(f"❌ Raw connection error: {e}")
            try:
                writer.close()
            except:
                pass

    async def read_http_request(self, reader):
        """Чтение HTTP запроса из сырого TCP соединения"""
        try:
            request_lines = []

            # Читаем строки до пустой строки (конец заголовков)
            while True:
                line = await reader.readline()
                if not line:
                    break

                request_lines.append(line)

                # Если строка пустая (только \r\n), заголовки закончились
                if line == b'\r\n':
                    break

            if request_lines:
                return b''.join(request_lines)

            return None

        except Exception as e:
            logger.error(f"❌ Error reading HTTP request: {e}")
            return None

    def parse_http_request(self, request_data):
        """Парсинг HTTP запроса"""
        try:
            request_str = request_data.decode('utf-8', errors='ignore')
            lines = request_str.strip().split('\r\n')

            if not lines:
                return None

            # Парсим первую строку (REQUEST LINE)
            request_line = lines[0].split(' ')
            if len(request_line) < 3:
                return None

            method = request_line[0]
            path = request_line[1]
            version = request_line[2]

            # Парсим заголовки
            headers = {}
            for line in lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip().lower()] = value.strip()

            return {
                'method': method,
                'path': path,
                'version': version,
                'headers': headers
            }

        except Exception as e:
            logger.error(f"❌ Error parsing HTTP request: {e}")
            return None

    def authenticate_request(self, headers):
        """Проверка аутентификации"""
        try:
            auth_header = headers.get('proxy-authorization', '')

            if not auth_header.startswith('Basic '):
                return False

            encoded_credentials = auth_header[6:]
            decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
            username, password = decoded_credentials.split(':', 1)

            return username == self.username and password == self.password

        except Exception as e:
            logger.debug(f"❌ Authentication error: {e}")
            return False

    async def send_http_error(self, writer, status_code, message):
        """Отправка HTTP ошибки"""
        try:
            response = f"HTTP/1.1 {status_code} {message}\r\n"
            if status_code == 407:
                response += "Proxy-Authenticate: Basic realm=\"Proxy\"\r\n"
            response += "Content-Length: 0\r\n"
            response += "Connection: close\r\n"
            response += "\r\n"

            writer.write(response.encode())
            await writer.drain()
            writer.close()

        except Exception as e:
            logger.error(f"❌ Error sending HTTP error: {e}")

    async def handle_raw_connect(self, reader, writer, request_info):
        """Обработка CONNECT запроса в сыром TCP режиме"""
        try:
            target = request_info['path']  # например "httpbin.org:443"

            if ':' in target:
                host, port = target.rsplit(':', 1)
                port = int(port)
            else:
                host = target
                port = 443

            logger.info(f"🔗 RAW CONNECT: {host}:{port}")

            # Получаем информацию об устройстве
            device = None
            # Сначала пробуем найти в device_manager (Android)
            if self.device_manager:
                device = await self.device_manager.get_device_by_id(self.device_id)
                if device:
                    logger.debug(f"Device found in device_manager: {self.device_id}")

            # Если не найдено, ищем в modem_manager (USB модемы)
            if not device and self.modem_manager:
                device = await self.modem_manager.get_device_by_id(self.device_id)
                if device:
                    logger.debug(f"Device found in modem_manager: {self.device_id}")

            if not device or device.get('status') != 'online':
                logger.error(f"Device {self.device_id} not available or not online")
                await self.send_http_error_to_writer(writer, 503, "Device not available")
                return

            # Создаем соединение с целевым сервером
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Привязываем к интерфейсу устройства
            interface = device.get('interface') or device.get('usb_interface')
            if interface and interface != 'unknown':
                try:
                    target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
                    logger.debug(f"✅ Socket bound to interface: {interface}")
                except OSError as e:
                    logger.warning(f"⚠️  Failed to bind to interface {interface}: {e}")

            # Подключаемся к целевому серверу
            target_sock.setblocking(False)
            try:
                await asyncio.get_event_loop().sock_connect(target_sock, (host, port))
                logger.debug(f"✅ Connected to {host}:{port} via interface {interface}")
            except OSError as e:
                target_sock.close()
                logger.error(f"❌ Failed to connect to {host}:{port}: {e}")
                await self.send_http_error_to_writer(writer, 502, "Connection failed")
                return

            # Отправляем успешный ответ CONNECT
            success_response = b"HTTP/1.1 200 Connection established\r\n\r\n"
            writer.write(success_response)
            await writer.drain()

            logger.info(f"🚀 Starting pure TCP tunnel to {host}:{port}")

            # Запускаем чистый TCP туннель
            await self.run_pure_tcp_tunnel_raw(reader, writer, target_sock, host, port)

        except Exception as e:
            logger.error(f"❌ Raw CONNECT error: {e}")
            try:
                await self.send_http_error_to_writer(writer, 502, "Bad Gateway")
            except:
                pass

    async def send_http_error_to_writer(self, writer, status_code, message):
        """Отправка HTTP ошибки через writer"""
        try:
            response = f"HTTP/1.1 {status_code} {message}\r\n"
            if status_code == 407:
                response += "Proxy-Authenticate: Basic realm=\"Proxy\"\r\n"
            response += "Content-Length: 0\r\n"
            response += "Connection: close\r\n"
            response += "\r\n"

            writer.write(response.encode())
            await writer.drain()

        except Exception as e:
            logger.error(f"❌ Error sending HTTP error to writer: {e}")

    async def run_pure_tcp_tunnel_raw(self, reader, writer, target_sock, host, port):
        """Чистый TCP туннель без HTTP обработки"""
        try:
            logger.debug(f"🔄 Starting PURE TCP tunnel: client <-> {host}:{port}")

            # Получаем сокет клиента
            client_sock = writer.get_extra_info('socket')
            client_sock.setblocking(False)
            target_sock.setblocking(False)

            async def forward_client_to_target():
                """Клиент -> Сервер"""
                try:
                    total_bytes = 0
                    while True:
                        data = await reader.read(8192)
                        if not data:
                            logger.debug("📤 Client->Target: EOF")
                            break

                        await asyncio.get_event_loop().sock_sendall(target_sock, data)
                        total_bytes += len(data)

                        if total_bytes < 1024:
                            logger.debug(f"🔐 Client->Target: {len(data)} bytes")

                    logger.debug(f"✅ Client->Target finished: {total_bytes} bytes")

                except Exception as e:
                    logger.debug(f"❌ Client->Target error: {e}")
                finally:
                    try:
                        target_sock.close()
                    except:
                        pass

            async def forward_target_to_client():
                """Сервер -> Клиент"""
                try:
                    total_bytes = 0
                    while True:
                        data = await asyncio.get_event_loop().sock_recv(target_sock, 8192)
                        if not data:
                            logger.debug("📤 Target->Client: EOF")
                            break

                        writer.write(data)
                        await writer.drain()
                        total_bytes += len(data)

                        if total_bytes < 1024:
                            logger.debug(f"🔐 Target->Client: {len(data)} bytes")

                    logger.debug(f"✅ Target->Client finished: {total_bytes} bytes")

                except Exception as e:
                    logger.debug(f"❌ Target->Client error: {e}")
                finally:
                    try:
                        writer.close()
                    except:
                        pass

            # Запускаем передачу в обе стороны
            client_task = asyncio.create_task(forward_client_to_target())
            target_task = asyncio.create_task(forward_target_to_client())

            # Ждем завершения любой из задач
            try:
                done, pending = await asyncio.wait(
                    [client_task, target_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=600
                )

                logger.debug(f"🔚 Pure TCP tunnel completed: {host}:{port}")

            except asyncio.TimeoutError:
                logger.info(f"⏰ Pure TCP tunnel timeout: {host}:{port}")
            finally:
                # Отменяем задачи
                for task in [client_task, target_task]:
                    if not task.done():
                        task.cancel()

                # Закрываем соединения
                try:
                    target_sock.close()
                except:
                    pass
                try:
                    writer.close()
                except:
                    pass

            logger.debug(f"🏁 Pure TCP tunnel ended: {host}:{port}")

        except Exception as e:
            logger.error(f"❌ Pure TCP tunnel error: {e}")

    async def handle_raw_http(self, reader, writer, request_info):
        """Обработка обычных HTTP запросов"""
        try:
            # Для HTTP запросов можем использовать простую заглушку
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/plain\r\n"
                "Content-Length: 13\r\n"
                "Connection: close\r\n"
                "\r\n"
                "Proxy working"
            )

            writer.write(response.encode())
            await writer.drain()
            writer.close()

        except Exception as e:
            logger.error(f"❌ Raw HTTP error: {e}")

    async def stop(self):
        """Остановка сервера"""
        if not self._running:
            return

        try:
            if self.server:
                self.server.close()
                await self.server.wait_closed()
                self.server = None

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
