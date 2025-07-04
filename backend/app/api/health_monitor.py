import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal, get_system_config
from ..models.base import ProxyDevice, RequestLog
from ..config import settings

logger = structlog.get_logger()


class HealthMonitor:
    """Мониторинг здоровья системы и модемов"""

    def __init__(self, modem_manager):
        self.modem_manager = modem_manager
        self.running = False
        self.monitor_task = None
        self.alert_tasks = []
        self.health_history = {}

    async def start(self):
        """Запуск мониторинга здоровья"""
        self.running = True

        # Запуск основного цикла мониторинга
        self.monitor_task = asyncio.create_task(self.monitor_loop())

        # Запуск проверки алертов
        alert_task = asyncio.create_task(self.alert_loop())
        self.alert_tasks.append(alert_task)

        logger.info("Health monitor started")

    async def stop(self):
        """Остановка мониторинга"""
        self.running = False

        # Остановка основного цикла
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        # Остановка алертов
        for task in self.alert_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.alert_tasks.clear()

        logger.info("Health monitor stopped")

    async def monitor_loop(self):
        """Основной цикл мониторинга"""
        while self.running:
            try:
                # Получение интервала мониторинга
                interval = await get_system_config('health_check_interval', 30)

                # Проверка здоровья всех модемов
                await self.check_all_modems_health()

                # Проверка общего здоровья системы
                await self.check_system_health()

                # Очистка старых данных
                await self.cleanup_old_data()

                # Ожидание до следующей проверки
                await asyncio.sleep(interval)

            except Exception as e:
                logger.error("Error in health monitor loop", error=str(e))
                await asyncio.sleep(30)  # Пауза при ошибке

    async def alert_loop(self):
        """Цикл проверки алертов"""
        while self.running:
            try:
                # Проверка алертов каждые 2 минуты
                await asyncio.sleep(120)

                if not self.running:
                    break

                # Проверка алертов
                await self.check_alerts()

            except Exception as e:
                logger.error("Error in alert loop", error=str(e))
                await asyncio.sleep(60)

    async def check_all_modems_health(self):
        """Проверка здоровья всех модемов"""
        try:
            modems = await self.modem_manager.get_all_modems()

            for modem_id, modem_info in modems.items():
                await self.check_modem_health(modem_id, modem_info)

        except Exception as e:
            logger.error("Error checking modems health", error=str(e))

    async def check_modem_health(self, modem_id: str, modem_info: dict):
        """Проверка здоровья конкретного модема"""
        try:
            health_data = {
                'modem_id': modem_id,
                'timestamp': datetime.now(timezone.utc),
                'checks': {}
            }

            # Проверка доступности
            is_online = await self.modem_manager.is_modem_online(modem_id)
            health_data['checks']['online'] = is_online

            # Проверка внешнего IP
            external_ip = await self.modem_manager.get_modem_external_ip(modem_id)
            health_data['checks']['has_external_ip'] = external_ip is not None
            health_data['external_ip'] = external_ip

            # Проверка времени последнего использования
            last_request_time = await self.get_last_request_time(modem_id)
            health_data['checks']['recently_used'] = (
                    last_request_time and
                    (datetime.now(timezone.utc) - last_request_time).total_seconds() < 3600
            )

            # Проверка успешности запросов
            success_rate = await self.get_success_rate(modem_id)
            health_data['checks']['good_success_rate'] = success_rate >= 85.0
            health_data['success_rate'] = success_rate

            # Проверка времени ответа
            avg_response_time = await self.get_avg_response_time(modem_id)
            health_data['checks']['good_response_time'] = avg_response_time < 10000  # 10 секунд
            health_data['avg_response_time_ms'] = avg_response_time

            # Общая оценка здоровья
            health_score = sum(1 for check in health_data['checks'].values() if check)
            total_checks = len(health_data['checks'])
            health_data['health_score'] = health_score / total_checks if total_checks > 0 else 0

            # Определение статуса
            if health_data['health_score'] >= 0.8:
                health_data['status'] = 'healthy'
            elif health_data['health_score'] >= 0.6:
                health_data['status'] = 'warning'
            else:
                health_data['status'] = 'critical'

            # Сохранение в историю
            self.health_history[modem_id] = health_data

            logger.debug(
                "Modem health check completed",
                modem_id=modem_id,
                status=health_data['status'],
                score=health_data['health_score']
            )

        except Exception as e:
            logger.error(
                "Error checking modem health",
                modem_id=modem_id,
                error=str(e)
            )

    async def check_system_health(self):
        """Проверка общего здоровья системы"""
        try:
            system_health = {
                'timestamp': datetime.now(timezone.utc),
                'checks': {}
            }

            # Проверка доступности модемов
            modems = await self.modem_manager.get_all_modems()
            online_modems = sum(1 for modem_id in modems.keys()
                                if await self.modem_manager.is_modem_online(modem_id))

            system_health['checks']['has_online_modems'] = online_modems > 0
            system_health['checks']['sufficient_modems'] = online_modems >= 2
            system_health['total_modems'] = len(modems)
            system_health['online_modems'] = online_modems

            # Проверка базы данных
            try:
                async with AsyncSessionLocal() as db:
                    await db.execute(select(1))
                system_health['checks']['database_accessible'] = True
            except:
                system_health['checks']['database_accessible'] = False

            # Проверка объема данных
            try:
                async with AsyncSessionLocal() as db:
                    from sqlalchemy import func

                    # Количество запросов за последний час
                    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                    stmt = select(func.count(RequestLog.id)).where(
                        RequestLog.created_at >= one_hour_ago
                    )
                    result = await db.execute(stmt)
                    requests_last_hour = result.scalar() or 0

                    system_health['checks']['active_traffic'] = requests_last_hour > 0
                    system_health['requests_last_hour'] = requests_last_hour

            except Exception as e:
                logger.error("Error checking traffic", error=str(e))
                system_health['checks']['active_traffic'] = False
                system_health['requests_last_hour'] = 0

            # Общая оценка здоровья системы
            health_score = sum(1 for check in system_health['checks'].values() if check)
            total_checks = len(system_health['checks'])
            system_health['health_score'] = health_score / total_checks if total_checks > 0 else 0

            # Определение статуса
            if system_health['health_score'] >= 0.8:
                system_health['status'] = 'healthy'
            elif system_health['health_score'] >= 0.6:
                system_health['status'] = 'warning'
            else:
                system_health['status'] = 'critical'

            # Сохранение в историю
            self.health_history['system'] = system_health

            logger.debug(
                "System health check completed",
                status=system_health['status'],
                score=system_health['health_score']
            )

        except Exception as e:
            logger.error("Error checking system health", error=str(e))

    async def get_last_request_time(self, modem_id: str) -> Optional[datetime]:
        """Получение времени последнего запроса для модема"""
        try:
            import uuid

            async with AsyncSessionLocal() as db:
                from sqlalchemy import func

                stmt = select(func.max(RequestLog.created_at)).where(
                    RequestLog.device_id == uuid.UUID(modem_id)
                )
                result = await db.execute(stmt)
                return result.scalar()

        except Exception as e:
            logger.error("Error getting last request time", modem_id=modem_id, error=str(e))
            return None

    async def get_success_rate(self, modem_id: str) -> float:
        """Получение процента успешных запросов для модема"""
        try:
            import uuid

            async with AsyncSessionLocal() as db:
                from sqlalchemy import func

                # Общее количество запросов за последние 24 часа
                yesterday = datetime.now(timezone.utc) - timedelta(days=1)

                stmt = select(func.count(RequestLog.id)).where(
                    RequestLog.device_id == uuid.UUID(modem_id),
                    RequestLog.created_at >= yesterday
                )
                result = await db.execute(stmt)
                total_requests = result.scalar() or 0

                if total_requests == 0:
                    return 100.0

                # Успешные запросы
                stmt = select(func.count(RequestLog.id)).where(
                    RequestLog.device_id == uuid.UUID(modem_id),
                    RequestLog.created_at >= yesterday,
                    RequestLog.status_code.between(200, 299)
                )
                result = await db.execute(stmt)
                successful_requests = result.scalar() or 0

                return (successful_requests / total_requests) * 100

        except Exception as e:
            logger.error("Error getting success rate", modem_id=modem_id, error=str(e))
            return 0.0

    async def get_avg_response_time(self, modem_id: str) -> int:
        """Получение среднего времени ответа для модема"""
        try:
            import uuid

            async with AsyncSessionLocal() as db:
                from sqlalchemy import func

                # Среднее время ответа за последние 24 часа
                yesterday = datetime.now(timezone.utc) - timedelta(days=1)

                stmt = select(func.avg(RequestLog.response_time_ms)).where(
                    RequestLog.device_id == uuid.UUID(modem_id),
                    RequestLog.created_at >= yesterday,
                    RequestLog.response_time_ms.isnot(None)
                )
                result = await db.execute(stmt)
                avg_time = result.scalar()

                return int(avg_time or 0)

        except Exception as e:
            logger.error("Error getting avg response time", modem_id=modem_id, error=str(e))
            return 0

    async def check_alerts(self):
        """Проверка условий для алертов"""
        try:
            alerts_enabled = await get_system_config('enable_alerts', True)
            if not alerts_enabled:
                return

            # Проверка алертов по модемам
            await self.check_modem_alerts()

            # Проверка системных алертов
            await self.check_system_alerts()

        except Exception as e:
            logger.error("Error checking alerts", error=str(e))

    async def check_modem_alerts(self):
        """Проверка алертов по модемам"""
        try:
            success_rate_threshold = await get_system_config('alert_success_rate_threshold', 85)
            offline_alert_minutes = await get_system_config('device_offline_alert_minutes', 5)

            for modem_id, health_data in self.health_history.items():
                if modem_id == 'system':
                    continue

                # Алерт о низкой успешности
                if 'success_rate' in health_data and health_data['success_rate'] < success_rate_threshold:
                    await self.send_alert(
                        'low_success_rate',
                        f"Modem {modem_id} has low success rate: {health_data['success_rate']:.1f}%",
                        {'modem_id': modem_id, 'success_rate': health_data['success_rate']}
                    )

                # Алерт об офлайн статусе
                if not health_data['checks'].get('online', False):
                    time_since_check = (datetime.now(timezone.utc) - health_data['timestamp']).total_seconds()
                    if time_since_check > offline_alert_minutes * 60:
                        await self.send_alert(
                            'modem_offline',
                            f"Modem {modem_id} has been offline for {time_since_check / 60:.1f} minutes",
                            {'modem_id': modem_id, 'offline_minutes': time_since_check / 60}
                        )

                # Алерт о медленном ответе
                if 'avg_response_time_ms' in health_data and health_data['avg_response_time_ms'] > 15000:
                    await self.send_alert(
                        'slow_response',
                        f"Modem {modem_id} has slow response time: {health_data['avg_response_time_ms']}ms",
                        {'modem_id': modem_id, 'response_time_ms': health_data['avg_response_time_ms']}
                    )

        except Exception as e:
            logger.error("Error checking modem alerts", error=str(e))

    async def check_system_alerts(self):
        """Проверка системных алертов"""
        try:
            system_health = self.health_history.get('system')
            if not system_health:
                return

            # Алерт о критическом состоянии системы
            if system_health['status'] == 'critical':
                await self.send_alert(
                    'system_critical',
                    f"System health is critical (score: {system_health['health_score']:.2f})",
                    {'health_score': system_health['health_score']}
                )

            # Алерт о недостатке онлайн модемов
            if system_health['online_modems'] == 0:
                await self.send_alert(
                    'no_online_modems',
                    "No modems are online",
                    {'online_modems': system_health['online_modems']}
                )

            # Алерт о недостатке трафика
            if system_health['requests_last_hour'] == 0:
                await self.send_alert(
                    'no_traffic',
                    "No requests in the last hour",
                    {'requests_last_hour': system_health['requests_last_hour']}
                )

        except Exception as e:
            logger.error("Error checking system alerts", error=str(e))

    async def send_alert(self, alert_type: str, message: str, data: dict):
        """Отправка алерта"""
        try:
            alert_data = {
                'type': alert_type,
                'message': message,
                'data': data,
                'timestamp': datetime.now(timezone.utc)
            }

            # Логирование алерта
            logger.warning(
                "Health alert triggered",
                alert_type=alert_type,
                message=message,
                data=data
            )

            # Здесь можно добавить отправку в Telegram, Slack, email и т.д.
            # Пока просто логируем

        except Exception as e:
            logger.error("Error sending alert", error=str(e))

    async def cleanup_old_data(self):
        """Очистка старых данных мониторинга"""
        try:
            # Очистка истории здоровья старше 24 часов
            current_time = datetime.now(timezone.utc)

            for modem_id, health_data in list(self.health_history.items()):
                if 'timestamp' in health_data:
                    age = (current_time - health_data['timestamp']).total_seconds()
                    if age > 24 * 3600:  # 24 часа
                        del self.health_history[modem_id]

        except Exception as e:
            logger.error("Error cleaning up old data", error=str(e))

    async def get_health_summary(self) -> dict:
        """Получение сводки здоровья системы"""
        try:
            summary = {
                'timestamp': datetime.now(timezone.utc),
                'system': self.health_history.get('system', {}),
                'modems': {},
                'alerts': []
            }

            # Сводка по модемам
            for modem_id, health_data in self.health_history.items():
                if modem_id != 'system':
                    summary['modems'][modem_id] = {
                        'status': health_data.get('status', 'unknown'),
                        'health_score': health_data.get('health_score', 0),
                        'online': health_data.get('checks', {}).get('online', False),
                        'success_rate': health_data.get('success_rate', 0),
                        'response_time_ms': health_data.get('avg_response_time_ms', 0)
                    }

            return summary

        except Exception as e:
            logger.error("Error getting health summary", error=str(e))
            return {
                'timestamp': datetime.now(timezone.utc),
                'error': str(e)
            }

    async def get_modem_health(self, modem_id: str) -> dict:
        """Получение детальной информации о здоровье модема"""
        try:
            health_data = self.health_history.get(modem_id, {})

            if not health_data:
                return {
                    'modem_id': modem_id,
                    'status': 'unknown',
                    'message': 'No health data available'
                }

            return health_data

        except Exception as e:
            logger.error("Error getting modem health", modem_id=modem_id, error=str(e))
            return {
                'modem_id': modem_id,
                'status': 'error',
                'error': str(e)
            }