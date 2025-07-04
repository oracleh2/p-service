import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from ..database import AsyncSessionLocal
from ..models.base import ProxyDevice, RequestLog, IpHistory, UsageStats
from ..config import settings

logger = structlog.get_logger()


class StatsCollector:
    """Сборщик статистики системы"""

    def __init__(self, modem_manager):
        self.modem_manager = modem_manager
        self.running = False
        self.collector_task = None
        self.stats_cache = {}
        self.last_collection_time = None

    async def start(self):
        """Запуск сборщика статистики"""
        self.running = True

        # Запуск основного цикла сбора статистики
        self.collector_task = asyncio.create_task(self.collection_loop())

        logger.info("Stats collector started")

    async def stop(self):
        """Остановка сборщика статистики"""
        self.running = False

        if self.collector_task:
            self.collector_task.cancel()
            try:
                await self.collector_task
            except asyncio.CancelledError:
                pass

        logger.info("Stats collector stopped")

    async def collection_loop(self):
        """Основной цикл сбора статистики"""
        while self.running:
            try:
                # Сбор статистики каждые 5 минут
                await asyncio.sleep(300)

                if not self.running:
                    break

                # Сбор различных типов статистики
                await self.collect_request_stats()
                await self.collect_modem_stats()
                await self.collect_ip_stats()
                await self.collect_usage_stats()

                # Обновление кэша
                await self.update_stats_cache()

                # Очистка старых данных
                await self.cleanup_old_stats()

                self.last_collection_time = datetime.now(timezone.utc)

                logger.debug("Stats collection completed")

            except Exception as e:
                logger.error("Error in stats collection loop", error=str(e))
                await asyncio.sleep(60)  # Пауза при ошибке

    async def collect_request_stats(self):
        """Сбор статистики запросов"""
        try:
            async with AsyncSessionLocal() as db:
                # Статистика за последние 24 часа
                yesterday = datetime.now(timezone.utc) - timedelta(days=1)

                # Общие метрики
                stmt = select(
                    func.count(RequestLog.id).label('total_requests'),
                    func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label(
                        'successful_requests'),
                    func.avg(RequestLog.response_time_ms).label('avg_response_time'),
                    func.min(RequestLog.response_time_ms).label('min_response_time'),
                    func.max(RequestLog.response_time_ms).label('max_response_time'),
                    func.sum(RequestLog.request_size + RequestLog.response_size).label('total_bytes')
                ).where(RequestLog.created_at >= yesterday)

                result = await db.execute(stmt)
                row = result.first()

                if row:
                    total_requests = row.total_requests or 0
                    successful_requests = row.successful_requests or 0
                    failed_requests = total_requests - successful_requests

                    self.stats_cache['request_stats'] = {
                        'period': '24h',
                        'total_requests': total_requests,
                        'successful_requests': successful_requests,
                        'failed_requests': failed_requests,
                        'success_rate': (successful_requests / total_requests * 100) if total_requests > 0 else 0,
                        'avg_response_time_ms': int(row.avg_response_time or 0),
                        'min_response_time_ms': int(row.min_response_time or 0),
                        'max_response_time_ms': int(row.max_response_time or 0),
                        'total_bytes': row.total_bytes or 0,
                        'total_mb': (row.total_bytes or 0) / (1024 * 1024),
                        'requests_per_hour': total_requests / 24 if total_requests > 0 else 0
                    }

                # Статистика по часам за последние 24 часа
                hourly_stats = []
                for hour in range(24):
                    hour_start = datetime.now(timezone.utc) - timedelta(hours=hour + 1)
                    hour_end = datetime.now(timezone.utc) - timedelta(hours=hour)

                    stmt = select(
                        func.count(RequestLog.id).label('requests'),
                        func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label('successful'),
                        func.avg(RequestLog.response_time_ms).label('avg_time')
                    ).where(
                        and_(
                            RequestLog.created_at >= hour_start,
                            RequestLog.created_at < hour_end
                        )
                    )

                    result = await db.execute(stmt)
                    row = result.first()

                    if row:
                        hourly_stats.append({
                            'hour': hour_start.strftime('%H:00'),
                            'requests': row.requests or 0,
                            'successful': row.successful or 0,
                            'avg_time_ms': int(row.avg_time or 0)
                        })

                self.stats_cache['hourly_stats'] = hourly_stats

        except Exception as e:
            logger.error("Error collecting request stats", error=str(e))

    async def collect_modem_stats(self):
        """Сбор статистики по модемам"""
        try:
            modems = await self.modem_manager.get_all_modems()
            modem_stats = {}

            async with AsyncSessionLocal() as db:
                yesterday = datetime.now(timezone.utc) - timedelta(days=1)

                for modem_id, modem_info in modems.items():
                    try:
                        device_uuid = uuid.UUID(modem_id)

                        # Статистика запросов для модема
                        stmt = select(
                            func.count(RequestLog.id).label('total_requests'),
                            func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label(
                                'successful_requests'),
                            func.avg(RequestLog.response_time_ms).label('avg_response_time'),
                            func.sum(RequestLog.request_size + RequestLog.response_size).label('total_bytes')
                        ).where(
                            and_(
                                RequestLog.device_id == device_uuid,
                                RequestLog.created_at >= yesterday
                            )
                        )

                        result = await db.execute(stmt)
                        row = result.first()

                        total_requests = row.total_requests or 0
                        successful_requests = row.successful_requests or 0

                        # Получение текущего статуса
                        is_online = await self.modem_manager.is_modem_online(modem_id)
                        external_ip = await self.modem_manager.get_modem_external_ip(modem_id)

                        # Количество уникальных IP
                        stmt = select(func.count(func.distinct(IpHistory.ip_address))).where(
                            IpHistory.device_id == device_uuid
                        )
                        result = await db.execute(stmt)
                        unique_ips = result.scalar() or 0

                        # Информация о последней ротации
                        stmt = select(ProxyDevice.last_ip_rotation).where(
                            ProxyDevice.id == device_uuid
                        )
                        result = await db.execute(stmt)
                        last_rotation = result.scalar()

                        modem_stats[modem_id] = {
                            'type': modem_info['type'],
                            'interface': modem_info['interface'],
                            'status': 'online' if is_online else 'offline',
                            'external_ip': external_ip,
                            'last_rotation': last_rotation,
                            'requests_24h': total_requests,
                            'successful_requests_24h': successful_requests,
                            'failed_requests_24h': total_requests - successful_requests,
                            'success_rate': (successful_requests / total_requests * 100) if total_requests > 0 else 0,
                            'avg_response_time_ms': int(row.avg_response_time or 0),
                            'data_transferred_mb': (row.total_bytes or 0) / (1024 * 1024),
                            'unique_ips': unique_ips,
                            'requests_per_hour': total_requests / 24 if total_requests > 0 else 0
                        }

                    except Exception as e:
                        logger.error(f"Error collecting stats for modem {modem_id}", error=str(e))
                        modem_stats[modem_id] = {
                            'type': modem_info['type'],
                            'interface': modem_info['interface'],
                            'status': 'error',
                            'error': str(e)
                        }

            self.stats_cache['modem_stats'] = modem_stats

        except Exception as e:
            logger.error("Error collecting modem stats", error=str(e))

    async def collect_ip_stats(self):
        """Сбор статистики по IP адресам"""
        try:
            async with AsyncSessionLocal() as db:
                # Общая статистика IP
                stmt = select(
                    func.count(IpHistory.id).label('total_ips'),
                    func.count(func.case((IpHistory.is_blocked == True, 1))).label('blocked_ips'),
                    func.sum(IpHistory.total_requests).label('total_requests_from_ips'),
                    func.count(func.distinct(IpHistory.operator)).label('unique_operators')
                )

                result = await db.execute(stmt)
                row = result.first()

                if row:
                    self.stats_cache['ip_stats'] = {
                        'total_ips': row.total_ips or 0,
                        'blocked_ips': row.blocked_ips or 0,
                        'active_ips': (row.total_ips or 0) - (row.blocked_ips or 0),
                        'block_rate': (row.blocked_ips / row.total_ips * 100) if row.total_ips > 0 else 0,
                        'total_requests_from_ips': row.total_requests_from_ips or 0,
                        'unique_operators': row.unique_operators or 0
                    }

                # Статистика по операторам
                stmt = select(
                    IpHistory.operator,
                    func.count(IpHistory.id).label('ip_count'),
                    func.sum(IpHistory.total_requests).label('total_requests'),
                    func.count(func.case((IpHistory.is_blocked == True, 1))).label('blocked_count')
                ).where(
                    IpHistory.operator.isnot(None)
                ).group_by(IpHistory.operator)

                result = await db.execute(stmt)
                operator_stats = []

                for row in result:
                    operator_stats.append({
                        'operator': row.operator,
                        'ip_count': row.ip_count,
                        'total_requests': row.total_requests,
                        'blocked_count': row.blocked_count,
                        'block_rate': (row.blocked_count / row.ip_count * 100) if row.ip_count > 0 else 0
                    })

                self.stats_cache['operator_stats'] = operator_stats

                # Последние IP адреса
                stmt = select(IpHistory).order_by(IpHistory.last_seen.desc()).limit(10)
                result = await db.execute(stmt)
                recent_ips = []

                for ip_record in result:
                    recent_ips.append({
                        'ip_address': ip_record.ip_address,
                        'operator': ip_record.operator,
                        'city': ip_record.city,
                        'first_seen': ip_record.first_seen,
                        'last_seen': ip_record.last_seen,
                        'total_requests': ip_record.total_requests,
                        'is_blocked': ip_record.is_blocked
                    })

                self.stats_cache['recent_ips'] = recent_ips

        except Exception as e:
            logger.error("Error collecting IP stats", error=str(e))

    async def collect_usage_stats(self):
        """Сбор статистики использования"""
        try:
            async with AsyncSessionLocal() as db:
                # Статистика за последние 7 дней
                week_ago = datetime.now(timezone.utc) - timedelta(days=7)

                daily_stats = []
                for day in range(7):
                    day_start = datetime.now(timezone.utc) - timedelta(days=day + 1)
                    day_end = datetime.now(timezone.utc) - timedelta(days=day)

                    stmt = select(
                        func.count(RequestLog.id).label('requests'),
                        func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label('successful'),
                        func.count(func.distinct(RequestLog.external_ip)).label('unique_ips'),
                        func.sum(RequestLog.request_size + RequestLog.response_size).label('bytes_transferred')
                    ).where(
                        and_(
                            RequestLog.created_at >= day_start,
                            RequestLog.created_at < day_end
                        )
                    )

                    result = await db.execute(stmt)
                    row = result.first()

                    if row:
                        daily_stats.append({
                            'date': day_start.strftime('%Y-%m-%d'),
                            'requests': row.requests or 0,
                            'successful': row.successful or 0,
                            'unique_ips': row.unique_ips or 0,
                            'mb_transferred': (row.bytes_transferred or 0) / (1024 * 1024)
                        })

                self.stats_cache['daily_stats'] = daily_stats

                # Статистика по методам HTTP
                stmt = select(
                    RequestLog.method,
                    func.count(RequestLog.id).label('count')
                ).where(
                    RequestLog.created_at >= week_ago
                ).group_by(RequestLog.method)

                result = await db.execute(stmt)
                method_stats = []

                for row in result:
                    method_stats.append({
                        'method': row.method,
                        'count': row.count
                    })

                self.stats_cache['method_stats'] = method_stats

                # Статистика по кодам ответов
                stmt = select(
                    RequestLog.status_code,
                    func.count(RequestLog.id).label('count')
                ).where(
                    RequestLog.created_at >= week_ago
                ).group_by(RequestLog.status_code).order_by(func.count(RequestLog.id).desc())

                result = await db.execute(stmt)
                status_stats = []

                for row in result:
                    status_stats.append({
                        'status_code': row.status_code,
                        'count': row.count
                    })

                self.stats_cache['status_stats'] = status_stats

        except Exception as e:
            logger.error("Error collecting usage stats", error=str(e))

    async def update_stats_cache(self):
        """Обновление кэша статистики"""
        try:
            # Добавление метаданных
            self.stats_cache['_metadata'] = {
                'last_updated': datetime.now(timezone.utc),
                'collection_time': self.last_collection_time,
                'cache_size': len(self.stats_cache)
            }

            # Сводная статистика
            self.stats_cache['summary'] = await self.generate_summary()

        except Exception as e:
            logger.error("Error updating stats cache", error=str(e))

    async def generate_summary(self) -> dict:
        """Генерация сводной статистики"""
        try:
            summary = {
                'timestamp': datetime.now(timezone.utc)
            }

            # Сводка по модемам
            modem_stats = self.stats_cache.get('modem_stats', {})
            total_modems = len(modem_stats)
            online_modems = sum(1 for stats in modem_stats.values() if stats.get('status') == 'online')

            summary['modems'] = {
                'total': total_modems,
                'online': online_modems,
                'offline': total_modems - online_modems,
                'utilization': (online_modems / total_modems * 100) if total_modems > 0 else 0
            }

            # Сводка по запросам
            request_stats = self.stats_cache.get('request_stats', {})
            summary['requests'] = {
                'total_24h': request_stats.get('total_requests', 0),
                'successful_24h': request_stats.get('successful_requests', 0),
                'failed_24h': request_stats.get('failed_requests', 0),
                'success_rate': request_stats.get('success_rate', 0),
                'avg_response_time_ms': request_stats.get('avg_response_time_ms', 0),
                'requests_per_hour': request_stats.get('requests_per_hour', 0)
            }

            # Сводка по IP
            ip_stats = self.stats_cache.get('ip_stats', {})
            summary['ips'] = {
                'total': ip_stats.get('total_ips', 0),
                'active': ip_stats.get('active_ips', 0),
                'blocked': ip_stats.get('blocked_ips', 0),
                'block_rate': ip_stats.get('block_rate', 0),
                'unique_operators': ip_stats.get('unique_operators', 0)
            }

            # Сводка по трафику
            total_mb = sum(stats.get('data_transferred_mb', 0) for stats in modem_stats.values())
            summary['traffic'] = {
                'total_mb_24h': total_mb,
                'total_gb_24h': total_mb / 1024,
                'avg_mb_per_request': total_mb / request_stats.get('total_requests', 1)
            }

            return summary

        except Exception as e:
            logger.error("Error generating summary", error=str(e))
            return {'error': str(e)}

    async def cleanup_old_stats(self):
        """Очистка старой статистики"""
        try:
            # Здесь можно добавить логику очистки старых данных из кэша
            # Например, удаление данных старше определенного времени

            # Пока просто логируем
            logger.debug("Stats cleanup completed")

        except Exception as e:
            logger.error("Error cleaning up stats", error=str(e))

    async def get_stats(self, category: Optional[str] = None) -> dict:
        """Получение статистики"""
        try:
            if category and category in self.stats_cache:
                return self.stats_cache[category]

            return self.stats_cache

        except Exception as e:
            logger.error("Error getting stats", error=str(e))
            return {'error': str(e)}

    async def get_realtime_stats(self) -> dict:
        """Получение статистики в реальном времени"""
        try:
            # Получение текущих данных без кэширования
            modems = await self.modem_manager.get_all_modems()
            online_modems = sum(1 for modem_id in modems.keys()
                                if await self.modem_manager.is_modem_online(modem_id))

            # Запросы за последние 5 минут
            five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

            async with AsyncSessionLocal() as db:
                stmt = select(
                    func.count(RequestLog.id).label('recent_requests'),
                    func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label(
                        'recent_successful'),
                    func.avg(RequestLog.response_time_ms).label('recent_avg_time')
                ).where(RequestLog.created_at >= five_minutes_ago)

                result = await db.execute(stmt)
                row = result.first()

                recent_requests = row.recent_requests or 0
                recent_successful = row.recent_successful or 0

                return {
                    'timestamp': datetime.now(timezone.utc),
                    'modems': {
                        'total': len(modems),
                        'online': online_modems
                    },
                    'recent_activity': {
                        'requests_5min': recent_requests,
                        'successful_5min': recent_successful,
                        'success_rate': (recent_successful / recent_requests * 100) if recent_requests > 0 else 0,
                        'avg_response_time_ms': int(row.recent_avg_time or 0),
                        'requests_per_minute': recent_requests / 5
                    }
                }

        except Exception as e:
            logger.error("Error getting realtime stats", error=str(e))
            return {'error': str(e)}

    async def export_stats(self, format: str = 'json', period_days: int = 7) -> dict:
        """Экспорт статистики"""
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=period_days)

            async with AsyncSessionLocal() as db:
                # Получение данных для экспорта
                stmt = select(RequestLog).where(
                    RequestLog.created_at.between(start_date, end_date)
                ).order_by(RequestLog.created_at.desc())

                result = await db.execute(stmt)
                logs = result.scalars().all()

                export_data = []
                for log in logs:
                    export_data.append({
                        'timestamp': log.created_at.isoformat(),
                        'modem_id': str(log.device_id) if log.device_id else None,
                        'client_ip': log.client_ip,
                        'target_url': log.target_url,
                        'method': log.method,
                        'status_code': log.status_code,
                        'response_time_ms': log.response_time_ms,
                        'external_ip': log.external_ip,
                        'request_size': log.request_size,
                        'response_size': log.response_size,
                        'error_message': log.error_message
                    })

                return {
                    'format': format,
                    'period_days': period_days,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'total_records': len(export_data),
                    'data': export_data
                }

        except Exception as e:
            logger.error("Error exporting stats", error=str(e))
            return {'error': str(e)}