import logging
from typing import Dict, List, Set
from datetime import datetime, timedelta
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import BaseFilter

logger = logging.getLogger(__name__)


class ServiceMessageTracker:
    """Трекер служебных сообщений для каналов"""

    def __init__(self):
        self._tracked_channels: Set[str] = set()  # Каналы для отслеживания
        self._service_messages: Dict[str, List[int]] = {}  # channel_username -> [message_ids]
        self._last_action_time: Dict[str, datetime] = {}  # channel_username -> время последнего действия
        # TODO: добавить фичу с моментальным удалением сообщения
        #  при получении его через трекер, вместо ручного удаления

    def start_tracking(self, channel_username: str):
        """Начать отслеживание служебных сообщений для канала"""
        self._tracked_channels.add(channel_username)
        self._service_messages[channel_username] = []
        self._last_action_time[channel_username] = datetime.now()
        logger.debug(f"Начато отслеживание служебных сообщений для @{channel_username}")

    def stop_tracking(self, channel_username: str) -> List[int]:
        """Остановить отслеживание и вернуть собранные ID"""
        service_ids = self._service_messages.get(channel_username, [])
        self._tracked_channels.discard(channel_username)
        self._service_messages.pop(channel_username, None)
        self._last_action_time.pop(channel_username, None)
        logger.debug(
            f"Остановлено отслеживание для @{channel_username}, найдено {len(service_ids)} служебных сообщений")
        return service_ids

    def add_service_message(self, channel_username: str, message_id: int):
        """Добавить ID служебного сообщения"""
        if channel_username in self._tracked_channels:
            # Проверяем что сообщение появилось недавно после действия
            if channel_username in self._last_action_time:
                time_diff = datetime.now() - self._last_action_time[channel_username]
                if time_diff < timedelta(seconds=10):  # В течение 10 секунд после действия
                    self._service_messages[channel_username].append(message_id)
                    logger.debug(f"Добавлено служебное сообщение {message_id} для @{channel_username}")

    def is_tracking(self, channel_username: str) -> bool:
        """Проверить отслеживается ли канал"""
        return channel_username in self._tracked_channels


# Создаем глобальный трекер
service_tracker = ServiceMessageTracker()


class ServiceMessageFilter(BaseFilter):
    """Фильтр для служебных сообщений"""

    async def __call__(self, message: Message) -> bool:
        # Проверяем что это сообщение из канала
        if not message.chat or message.chat.type != 'channel':
            return False

        # Проверяем что это служебное сообщение
        return self._is_service_message(message)

    def _is_service_message(self, message: Message) -> bool:
        """Проверка является ли сообщение служебным"""
        # Проверяем наличие служебных полей
        service_attributes = [
            'new_chat_title',
            'new_chat_photo',
            'delete_chat_photo',
            'group_chat_created',
            'channel_chat_created',
            'migrate_to_chat_id',
            'migrate_from_chat_id',
            'pinned_message'
        ]

        return any(hasattr(message, attr) and getattr(message, attr) for attr in service_attributes)


# Создаем роутер для служебных сообщений
service_router = Router(name="service_messages")


@service_router.channel_post(ServiceMessageFilter())
async def handle_service_message(message: Message):
    """Обработчик служебных сообщений"""
    try:
        chat = message.chat
        if not chat or not chat.username:
            return

        channel_username = chat.username

        # Если канал отслеживается - добавляем сообщение
        if service_tracker.is_tracking(channel_username):
            service_tracker.add_service_message(channel_username, message.message_id)
            logger.debug(f"Получено служебное сообщение {message.message_id} в канале @{channel_username}")

    except Exception as e:
        logger.error(f"Ошибка обработки служебного сообщения: {e}")