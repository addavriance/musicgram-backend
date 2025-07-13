import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.config import settings
from app.database.connection import get_session
from app.database.models import User, Channel
from app.services.spotify import SpotifyService
from app.bot.utils.channel import ChannelManager

logger = logging.getLogger(__name__)


class TrackUpdater:
    """Сервис для автоматического обновления треков пользователей"""

    def __init__(self):
        self.spotify_service = SpotifyService()
        self.channel_manager = ChannelManager()
        self.update_interval = settings.UPDATE_INTERVAL
        self.is_running = False
        self._task = None
        self._stats = {
            'total_updates': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'last_update_time': None,
            'active_users': 0
        }

    async def start(self):
        """Запуск сервиса обновления"""
        if self.is_running:
            logger.warning("TrackUpdater уже запущен")
            return

        self.is_running = True
        logger.info(f"🔄 Запуск TrackUpdater (интервал: {self.update_interval}с)")

        try:
            # Запускаем основной цикл
            await self._run_update_loop()
        except Exception as e:
            logger.error(f"Критическая ошибка в TrackUpdater: {e}")
            self.is_running = False
            raise

    async def stop(self):
        """Остановка сервиса обновления"""
        if not self.is_running:
            return

        logger.info("🛑 Остановка TrackUpdater...")
        self.is_running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("✅ TrackUpdater остановлен")

    async def _run_update_loop(self):
        """Основной цикл обновления"""
        logger.info("🚀 TrackUpdater запущен, начинаем обновления...")

        while self.is_running:
            cycle_start = datetime.utcnow()

            try:
                # Выполняем цикл обновления всех пользователей
                await self._update_cycle()

                # Обновляем статистику
                self._stats['last_update_time'] = cycle_start

                # Вычисляем время выполнения
                execution_time = (datetime.utcnow() - cycle_start).total_seconds()

                if execution_time > self.update_interval:
                    logger.warning(
                        f"Цикл обновления занял {execution_time:.2f}с (больше интервала {self.update_interval}с)")
                else:
                    logger.debug(f"Цикл обновления выполнен за {execution_time:.2f}с")

                # Ждем до следующего обновления
                sleep_time = max(0.5, self.update_interval - execution_time)
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                logger.info("Получен сигнал остановки TrackUpdater")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле обновления: {e}", exc_info=True)
                self._stats['failed_updates'] += 1

                # Ждем перед повторной попыткой
                await asyncio.sleep(min(30, self.update_interval))

        logger.info("TrackUpdater завершил работу")

    async def _update_cycle(self):
        """Один цикл обновления всех пользователей"""
        async for db in get_session():
            try:
                # Получаем активных пользователей с каналами
                users_data = await self._get_active_users(db)

                if not users_data:
                    logger.debug("Нет активных пользователей для обновления")
                    return

                self._stats['active_users'] = len(users_data)
                logger.debug(f"Обновляем {len(users_data)} пользователей")

                # Обрабатываем пользователей пакетами для лучшей производительности
                batch_size = 5  # Уменьшили размер пакета для стабильности

                for i in range(0, len(users_data), batch_size):
                    if not self.is_running:
                        break

                    batch = users_data[i:i + batch_size]

                    # Создаем задачи для параллельного выполнения
                    tasks = []
                    for user_data in batch:
                        task = asyncio.create_task(
                            self._update_single_user(db, user_data)
                        )
                        tasks.append(task)

                    # Выполняем пакет с таймаутом
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*tasks, return_exceptions=True),
                            timeout=30.0  # Таймаут на пакет
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Таймаут при обработке пакета пользователей")
                        for task in tasks:
                            if not task.done():
                                task.cancel()

                    # Пауза между пакетами для снижения нагрузки на API
                    if i + batch_size < len(users_data):
                        await asyncio.sleep(0.2)

            except Exception as e:
                logger.error(f"Ошибка в цикле обновления: {e}", exc_info=True)
                raise

    async def _get_active_users(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Получение списка активных пользователей с каналами

        Returns:
            Список словарей с данными пользователей и каналов
        """
        try:
            result = await db.execute(
                select(
                    User.id,
                    User.telegram_id,
                    User.spotify_access_token,
                    User.spotify_refresh_token,
                    User.token_expires_at,
                    Channel.id.label('channel_id'),
                    Channel.channel_username,
                    Channel.last_track_id,
                    Channel.last_track_image_url,
                    Channel.last_message_id
                )
                .join(Channel, User.id == Channel.user_id)
                .where(
                    User.spotify_access_token.isnot(None),
                    Channel.channel_username.isnot(None)
                )
                .order_by(User.id)
            )

            users_data = []
            for row in result.fetchall():
                users_data.append({
                    'user_id': row.id,
                    'telegram_id': row.telegram_id,
                    'access_token': row.spotify_access_token,
                    'refresh_token': row.spotify_refresh_token,
                    'token_expires_at': row.token_expires_at,
                    'channel_id': row.channel_id,
                    'channel_username': row.channel_username,
                    'last_track_id': row.last_track_id,
                    'last_track_image_url': row.last_track_image_url,
                    'last_message_id': row.last_message_id
                })

            return users_data

        except Exception as e:
            logger.error(f"Ошибка получения активных пользователей: {e}")
            return []

    async def _update_single_user(self, db: AsyncSession, user_data: Dict[str, Any]):
        """
        Обновление трека для одного пользователя

        Args:
            db: Сессия базы данных
            user_data: Данные пользователя и канала
        """
        telegram_id = user_data['telegram_id']
        channel_username = user_data['channel_username']

        try:
            self._stats['total_updates'] += 1

            # Проверяем и обновляем токен если нужно
            access_token = await self._ensure_valid_token(db, user_data)
            if not access_token:
                logger.warning(f"Не удалось получить валидный токен для пользователя {telegram_id}")
                return

            # Получаем текущий трек из Spotify
            current_track = await self._get_user_current_track(access_token, telegram_id)

            # Определяем нужно ли обновлять канал
            should_update = await self._should_update_channel(user_data, current_track)

            if should_update:
                # Обновляем канал в Telegram
                success = await self._update_user_channel(
                    channel_username,
                    current_track,
                    user_data
                )

                if success:
                    # Сохраняем новое состояние в БД
                    await self._save_channel_state(db, user_data, current_track)
                    self._stats['successful_updates'] += 1

                    track_name = current_track.get('name', 'Нет музыки') if current_track else 'Нет музыки'
                    logger.debug(f"Обновлен канал @{channel_username} для пользователя {telegram_id}: {track_name}")
                else:
                    logger.warning(f"Не удалось обновить канал @{channel_username} для пользователя {telegram_id}")
            else:
                logger.debug(f"Обновление канала @{channel_username} не требуется (трек не изменился)")
                self._stats['successful_updates'] += 1

        except Exception as e:
            logger.error(f"Ошибка обновления пользователя {telegram_id}: {e}")
            self._stats['failed_updates'] += 1

    async def _ensure_valid_token(self, db: AsyncSession, user_data: Dict[str, Any]) -> Optional[str]:
        """
        Проверка и обновление токена пользователя при необходимости

        Args:
            db: Сессия базы данных
            user_data: Данные пользователя

        Returns:
            Валидный access_token или None
        """
        access_token = user_data['access_token']
        token_expires_at = user_data['token_expires_at']

        # Проверяем не истек ли токен
        if token_expires_at and datetime.utcnow() < token_expires_at:
            return access_token

        # Токен истек, пытаемся обновить
        refresh_token = user_data['refresh_token']
        if not refresh_token:
            logger.warning(f"Нет refresh_token для пользователя {user_data['telegram_id']}")
            return None

        try:
            new_tokens = await self.spotify_service.refresh_access_token(refresh_token)

            # Обновляем токены в БД
            expires_at = datetime.utcnow() + timedelta(seconds=new_tokens['expires_in'])

            await db.execute(
                update(User)
                .where(User.id == user_data['user_id'])
                .values(
                    spotify_access_token=new_tokens['access_token'],
                    token_expires_at=expires_at,
                    updated_at=datetime.utcnow()
                )
            )
            await db.commit()

            logger.info(f"Токен обновлен для пользователя {user_data['telegram_id']}")
            return new_tokens['access_token']

        except Exception as e:
            logger.error(f"Ошибка обновления токена для пользователя {user_data['telegram_id']}: {e}")
            return None

    async def _get_user_current_track(self, access_token: str, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение текущего трека пользователя из Spotify

        Args:
            access_token: Токен доступа Spotify
            telegram_id: ID пользователя для логирования

        Returns:
            Данные трека или None
        """
        try:
            track_data = await self.spotify_service.get_current_track(access_token)

            if track_data:
                parsed_track = self.spotify_service.parse_track_data(track_data)
                return parsed_track

            return None

        except Exception as e:
            logger.warning(f"Ошибка получения трека из Spotify для пользователя {telegram_id}: {e}")
            return None

    async def _should_update_channel(self, user_data: Dict[str, Any], current_track: Optional[Dict[str, Any]]) -> bool:
        """
        Определение необходимости обновления канала

        Args:
            user_data: Данные пользователя и канала
            current_track: Текущий трек или None

        Returns:
            True если нужно обновить канал
        """
        last_track_id = user_data['last_track_id']
        current_track_id = current_track.get('id') if current_track else None

        # Если это первое обновление (нет истории)
        if last_track_id is None:
            return True

        # Если трек изменился (включая переход от музыки к отсутствию музыки)
        if current_track_id != last_track_id:
            return True

        # Если трек тот же и играет
        if current_track and current_track.get('is_playing'):
            return True

        return False

    async def _update_user_channel(
            self,
            channel_username: str,
            track_data: Optional[Dict[str, Any]],
            user_data: Dict[str, Any]
    ) -> bool:
        """
        Обновление канала пользователя в Telegram

        Args:
            channel_username: Username канала
            track_data: Данные трека или None
            user_data: Данные пользователя

        Returns:
            True если обновление прошло успешно
        """
        try:
            await self.channel_manager.update_channel_content(
                channel_username,
                user_data,
                track_data,
            )

            return True

        except Exception as e:
            logger.error(f"Ошибка обновления канала @{channel_username}: {e}")
            return False

    async def _save_channel_state(
            self,
            db: AsyncSession,
            user_data: Dict[str, Any],
            track_data: Optional[Dict[str, Any]]
    ):
        """
        Сохранение текущего состояния канала в БД

        Args:
            db: Сессия базы данных
            user_data: Данные пользователя
            track_data: Данные трека или None
        """
        try:
            channel_id = user_data['channel_id']

            if track_data:
                await db.execute(
                    update(Channel)
                    .where(Channel.id == channel_id)
                    .values(
                        last_track_id=track_data.get('id'),
                        last_track_name=track_data.get('name'),
                        last_track_artist=track_data.get('artist'),
                        last_track_image_url=track_data.get('image_url'),
                        updated_at=datetime.utcnow()
                    )
                )
            else:
                # Очищаем данные трека если музыка не играет
                await db.execute(
                    update(Channel)
                    .where(Channel.id == channel_id)
                    .values(
                        last_track_id=None,
                        last_track_name=None,
                        last_track_artist=None,
                        last_track_image_url=None,
                        updated_at=datetime.utcnow()
                    )
                )

            await db.commit()

        except Exception as e:
            logger.error(f"Ошибка сохранения состояния канала: {e}")
            await db.rollback()

    async def update_user_manually(self, telegram_id: int) -> bool:
        """
        Ручное обновление трека конкретного пользователя (для команд бота)

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            True если обновление прошло успешно
        """
        async for db in get_session():
            try:
                # Получаем данные пользователя
                result = await db.execute(
                    select(
                        User.id,
                        User.telegram_id,
                        User.spotify_access_token,
                        User.spotify_refresh_token,
                        User.token_expires_at,
                        Channel.id.label('channel_id'),
                        Channel.channel_username,
                        Channel.last_track_id,
                        Channel.last_track_image_url,
                        Channel.last_message_id
                    )
                    .join(Channel, User.id == Channel.user_id)
                    .where(User.telegram_id == telegram_id)
                )

                row = result.first()
                if not row:
                    logger.warning(f"Пользователь {telegram_id} или его канал не найден для ручного обновления")
                    return False

                user_data = {
                    'user_id': row.id,
                    'telegram_id': row.telegram_id,
                    'access_token': row.spotify_access_token,
                    'refresh_token': row.spotify_refresh_token,
                    'token_expires_at': row.token_expires_at,
                    'channel_id': row.channel_id,
                    'channel_username': row.channel_username,
                    'last_track_id': row.last_track_id,
                    'last_track_image_url': row.last_track_image_url,
                    'last_message_id': row.last_message_id
                }

                # Принудительно обновляем пользователя
                await self._update_single_user(db, user_data)
                return True

            except Exception as e:
                logger.error(f"Ошибка ручного обновления пользователя {telegram_id}: {e}")
                return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики работы сервиса

        Returns:
            Словарь со статистикой
        """
        return {
            'is_running': self.is_running,
            'update_interval': self.update_interval,
            'total_updates': self._stats['total_updates'],
            'successful_updates': self._stats['successful_updates'],
            'failed_updates': self._stats['failed_updates'],
            'success_rate': (
                    self._stats['successful_updates'] / max(1, self._stats['total_updates']) * 100
            ),
            'active_users': self._stats['active_users'],
            'last_update_time': self._stats['last_update_time'].isoformat() if self._stats[
                'last_update_time'] else None,
            'uptime_seconds': (datetime.utcnow() - self._stats['last_update_time']).total_seconds() if self._stats[
                'last_update_time'] else 0
        }

    async def health_check(self) -> Dict[str, Any]:
        """
        Проверка здоровья сервиса

        Returns:
            Состояние сервиса
        """
        last_update = self._stats['last_update_time']
        is_healthy = True
        issues = []

        # Проверяем что сервис запущен
        if not self.is_running:
            is_healthy = False
            issues.append("Service is not running")

        # Проверяем что недавно были обновления
        if last_update:
            time_since_update = (datetime.utcnow() - last_update).total_seconds()
            if time_since_update > self.update_interval * 3:  # Более 3 интервалов
                is_healthy = False
                issues.append(f"No updates for {time_since_update:.0f} seconds")

        # Проверяем успешность обновлений
        if self._stats['total_updates'] > 10:  # Только если есть статистика
            success_rate = self._stats['successful_updates'] / self._stats['total_updates'] * 100
            if success_rate < 80:  # Менее 80% успешных обновлений
                is_healthy = False
                issues.append(f"Low success rate: {success_rate:.1f}%")

        return {
            'healthy': is_healthy,
            'issues': issues,
            'stats': self.get_stats()
        }