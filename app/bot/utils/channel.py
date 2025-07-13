import asyncio
import logging
import aiohttp
from typing import Optional, Dict, Any
from io import BytesIO

from sqlalchemy import select, update

from app.database import Channel
from app.database.connection import get_session

from app.config import settings

logger = logging.getLogger(__name__)


class ChannelManager:
    """Менеджер для работы с каналами Telegram"""

    def __init__(self):
        self.bot_token = settings.TG_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def extract_channel_username(self, channel_input: str) -> Optional[str]:
        """
        Извлечение username канала из различных форматов

        Args:
            channel_input: @username, https://t.me/username, или username

        Returns:
            Чистый username без @
        """
        if not channel_input:
            return None

        channel_input = channel_input.strip()

        # Если начинается с @
        if channel_input.startswith('@'):
            return channel_input[1:]

        # Если это ссылка t.me
        if 't.me/' in channel_input:
            parts = channel_input.split('t.me/')
            if len(parts) > 1:
                username = parts[1].split('?')[0]  # Убираем query параметры
                return username

        return channel_input

    async def check_bot_admin_status(self, channel_username: str) -> bool:
        """
        Проверка статуса администратора бота в канале

        Args:
            channel_username: Username канала без @

        Returns:
            True если бот является администратором с нужными правами
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/getChatMember"
                data = {
                    "chat_id": f"@{channel_username}",
                    "user_id": settings.TG_BOT_ID
                }

                async with session.post(url, json=data) as response:
                    if response.status != 200:
                        logger.warning(f"Не удалось проверить статус бота в канале @{channel_username}")
                        return False

                    result = await response.json()

                    if not result.get('ok'):
                        logger.warning(f"API ошибка при проверке статуса: {result.get('description')}")
                        return False

                    member = result['result']

                    # Проверяем что бот является администратором с нужными правами
                    return (
                            member['status'] == 'administrator' and
                            member.get('can_change_info', False) and
                            member.get('can_post_messages', False) and
                            member.get('can_edit_messages', False)
                    )

        except Exception as e:
            logger.error(f"Ошибка проверки статуса администратора в канале @{channel_username}: {e}")
            return False

    async def update_channel_title(self, channel_username: str, title: str) -> bool:
        """
        Обновление названия канала

        Args:
            channel_username: Username канала
            title: Новое название

        Returns:
            True если успешно обновлено
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/setChatTitle"
                data = {
                    "chat_id": f"@{channel_username}",
                    "title": title
                }

                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('ok'):
                            logger.debug(f"Название канала @{channel_username} обновлено: {title}")
                            return True

                    logger.warning(f"Не удалось обновить название канала @{channel_username}")
                    return False

        except Exception as e:
            logger.error(f"Ошибка обновления названия канала @{channel_username}: {e}")
            return False

    async def update_channel_photo(self, channel_username: str, image_url: str) -> bool:
        """
        Обновление фото канала

        Args:
            channel_username: Username канала
            image_url: URL изображения

        Returns:
            True если успешно обновлено
        """
        try:
            # Загружаем изображение
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as img_response:
                    if img_response.status != 200:
                        logger.warning(f"Не удалось загрузить изображение: {image_url}")
                        return False

                    image_data = await img_response.read()

                # Отправляем фото в канал
                url = f"{self.api_url}/setChatPhoto"

                # Создаем FormData для загрузки файла
                data = aiohttp.FormData()
                data.add_field('chat_id', f"@{channel_username}")
                data.add_field('photo', BytesIO(image_data), filename='cover.jpg', content_type='image/jpeg')

                async with session.post(url, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('ok'):
                            logger.debug(f"Фото канала @{channel_username} обновлено")
                            return True

                    error_text = await response.text()
                    logger.warning(f"Не удалось обновить фото канала @{channel_username}: {error_text}")
                    return False

        except Exception as e:
            logger.error(f"Ошибка обновления фото канала @{channel_username}: {e}")
            return False

    async def send_message(self, channel_username: str, text: str) -> Optional[int]:
        """
        Отправка сообщения в канал

        Args:
            channel_username: Username канала
            text: Текст сообщения

        Returns:
            ID отправленного сообщения или None
        """

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/sendMessage"
                data = {
                    "chat_id": f"@{channel_username}",
                    "text": text or self._create_progress_bar_text({}),  # Невидимый символ если текст пустой
                    "parse_mode": "Markdown"
                }

                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('ok'):
                            return result['result']['message_id']

                    error_text = await response.text()
                    logger.warning(f"Не удалось отправить сообщение в канал @{channel_username}: {error_text}")
                    return None

        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в канал @{channel_username}: {e}")
            return None

    async def edit_message(self, channel_username: str, message_id: int, text: str) -> bool:
        """
        Редактирование сообщения в канале

        Args:
            channel_username: Username канала
            message_id: ID сообщения
            text: Новый текст

        Returns:
            True если успешно отредактировано
        """

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/editMessageText"
                data = {
                    "chat_id": f"@{channel_username}",
                    "message_id": message_id,
                    "text": text or "\u200B",
                    "parse_mode": "Markdown"
                }

                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('ok'):
                            return True

                    # Если сообщение не изменилось, это тоже успех
                    error_text = await response.text()
                    if "message is not modified" in error_text.lower():
                        return True

                    logger.warning(f"Не удалось отредактировать сообщение в канале @{channel_username}: {error_text}")
                    return False

        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения в канале @{channel_username}: {e}")
            return False

    async def delete_message(self, channel_username: str, message_id: int) -> bool:
        """
        Удаление сообщения из канала

        Args:
            channel_username: Username канала
            message_id: ID сообщения

        Returns:
            True если успешно удалено
        """

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/deleteMessage"
                data = {
                    "chat_id": f"@{channel_username}",
                    "message_id": message_id
                }

                async with session.post(url, json=data) as response:
                    json_data = await response.json()
                    # Удаление может не работать для старых сообщений, это нормально
                    return True

        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение {message_id} в канале @{channel_username}: {e}")
            return False

    async def cleanup_channel_messages(self, channel_username: str, around_message_id: int, range_size: int = 5):
        """
        Очистка служебных сообщений вокруг основного сообщения

        Args:
            channel_username: Username канала
            around_message_id: ID основного сообщения
            range_size: Радиус очистки (количество сообщений в каждую сторону)
        """
        if not around_message_id:
            return

        # Удаляем сообщения в диапазоне, кроме основного
        for offset in range(-range_size, range_size + 1):
            if offset == 0:  # Не удаляем основное сообщение
                continue

            message_id = around_message_id + offset
            if message_id > 0:
                await self.delete_message(channel_username, message_id)

        # Небольшая задержка после очистки
        import asyncio
        await asyncio.sleep(0.3)

    async def initialize_channel(self, channel_username: str, user_id: int):
        """
        Инициализация канала при первой настройке

        Args:
            channel_username: Username канала
            user_id: Telegram ID пользователя
        """
        try:
            # Устанавливаем начальное название
            await self.update_channel_title(channel_username, "🎵 Настройка канала...")

            # Отправляем первое сообщение
            message_id = await self.send_message(channel_username, "Канал настраивается...")

            logger.info(f"Канал @{channel_username} инициализирован для пользователя {user_id}")
            return message_id

        except Exception as e:
            logger.error(f"Ошибка инициализации канала @{channel_username}: {e}")
            return None

    async def update_channel_content(self, channel_username: str, user_data: Optional[Dict[str, Any]], track_data: Optional[Dict[str, Any]]):
        """
        Главная функция обновления контента канала С УПРАВЛЕНИЕМ СООБЩЕНИЯМИ
        """
        from app.services.channel_service import service_tracker

        try:
            channel_id = user_data['channel_id']
            last_track_id = user_data['last_track_id']
            last_track_image_url = user_data['last_track_image_url']

            if track_data and track_data.get('is_playing'):
                # ЕСТЬ АКТИВНЫЙ ТРЕК
                current_track_id = track_data.get('id')
                track_changed = current_track_id != last_track_id

                if track_changed:
                    service_tracker.start_tracking(channel_username)

                    # 1. Обновляем название канала
                    artists = track_data.get('artist', 'Unknown Artist')
                    track_name = track_data.get('name', 'Unknown Track')
                    title = f"{track_name} - {artists}"
                    await self.update_channel_title(channel_username, title)

                    # 2. Обновляем фото канала если есть изображение
                    image_url = track_data.get('image_url')
                    if image_url and last_track_image_url != image_url:
                        await self.update_channel_photo(channel_username, image_url)

                    # 2. Ждем применения изменений
                    await asyncio.sleep(1.0)

                    msg_ids = service_tracker.stop_tracking(channel_username)

                    for msg_id in msg_ids:  # TODO: вероятно будет удалено, поскольку будет фича с автоматическим удалением
                        await self.delete_message(channel_username, msg_id)

                    # 3. Получаем или создаем сообщение с прогресс-баром
                    message_id = await self.get_or_create_progress_message(channel_username, channel_id)

                    # # 4. Удаляем служебные сообщения (уведомления о смене)
                    # if message_id:
                    #     await self.cleanup_service_messages_only(channel_username, message_id)
                else:
                    # Трек тот же - просто получаем ID сообщения
                    async for db in get_session():
                        result = await db.execute(
                            select(Channel.last_message_id).where(Channel.id == channel_id)
                        )
                        message_id = result.scalar()

                # 5. Обновляем прогресс-бар
                if message_id:
                    progress_bar = self._create_progress_bar_text(track_data)
                    await self.edit_message(channel_username, message_id, progress_bar)

            else:
                # НЕТ МУЗЫКИ
                music_was_playing = last_track_id is not None

                if music_was_playing:
                    service_tracker.start_tracking(channel_username)

                    # 1. Обновляем канал на "нет музыки"
                    await self.update_channel_title(channel_username, "⏸️ Ничего не играет")
                    await self.set_default_music_photo(channel_username)  # НОВОЕ!

                    # 2. Ждем и очищаем служебные сообщения
                    await asyncio.sleep(1.0)

                    msg_ids = service_tracker.stop_tracking(channel_username)

                    for msg_id in msg_ids:
                        await self.delete_message(channel_username, msg_id)

                    # 3. Получаем или создаем сообщение
                    message_id = await self.get_or_create_progress_message(channel_username, channel_id)

                    # if message_id:
                    #     await self.cleanup_service_messages_only(channel_username, message_id)
                else:
                    # Музыка и так не играла - просто получаем ID
                    async for db in get_session():
                        result = await db.execute(
                            select(Channel.last_message_id).where(Channel.id == channel_id)
                        )
                        message_id = result.scalar()

                # 4. Показываем пустой прогресс-бар
                if message_id:
                    empty_progress = self._create_progress_bar_text({})  # НОВОЕ!
                    await self.edit_message(channel_username, message_id, empty_progress)

        except Exception as e:
            logger.error(f"Ошибка обновления контента канала @{channel_username}: {e}")

    def _create_progress_bar_text(self, track_data: Dict[str, Any]) -> str:
        """Создание текста с прогресс-баром для активного трека"""
        from app.bot.utils.progress import create_progress_bar

        progress_bar = create_progress_bar(
            track_data.get('progress_ms', 0),
            track_data.get('duration_ms', 0)
        )
        return f"`{progress_bar}`"

    async def get_or_create_progress_message(self, channel_username: str, channel_id: int) -> Optional[int]:
        """
        Получить ID сообщения с прогресс-баром или создать новое

        Args:
            channel_username: Username канала
            channel_id: ID канала в БД

        Returns:
            ID сообщения или None
        """
        # Получаем последний message_id из БД
        async for db in get_session():
            result = await db.execute(
                select(Channel.last_message_id).where(Channel.id == channel_id)
            )
            last_message_id = result.scalar()

            if last_message_id:
                # Пробуем отредактировать существующее сообщение
                test_success = await self.edit_message(channel_username, last_message_id, self._create_progress_bar_text({}))
                if test_success:
                    return last_message_id

            # Если сообщение не найдено/не редактируется - создаем новое
            await self.cleanup_all_messages(channel_username, last_message_id)
            new_message_id = await self.send_message(channel_username, self._create_progress_bar_text({}))

            # Сохраняем новый ID в БД
            await db.execute(
                update(Channel)
                .where(Channel.id == channel_id)
                .values(last_message_id=new_message_id)
            )
            await db.commit()

            return new_message_id

    # TODO: методы с очисткой нужно будет удалить поскольку их работа неэффективна
    async def cleanup_all_messages(self, channel_username: str, around_message_id: Optional[int]):
        """
        Удаление всех сообщений в канале (при создании нового)

        Args:
            channel_username: Username канала
            around_message_id: ID около которого удалять (если есть)
        """
        if around_message_id:
            await self.get_updates(channel_username)
            for offset in range(-20, 21):
                message_id = around_message_id + offset
                if message_id > 0:
                    await self.delete_message(channel_username, message_id)

        await asyncio.sleep(0.5)

    async def cleanup_service_messages_only(self, channel_username: str, keep_message_id: int):
        """
        Удаление только служебных сообщений, сохраняя основное

        Args:
            channel_username: Username канала
            keep_message_id: ID сообщения которое НЕ удалять
        """

        await self.get_updates(channel_username)
        for offset in range(-5, 6):
            if offset == 0:  # Не удаляем основное сообщение
                continue

            message_id = keep_message_id + offset
            if message_id > 0:
                await self.delete_message(channel_username, message_id)

        await asyncio.sleep(0.3)

    # TODO: удалить или переиначить логику создания стоковой картинки если fallback не предоставлена (1px пикчи не принимает тг)
    async def set_invisible_channel_photo(self, channel_username: str) -> bool:
        """
        Установка невидимого/прозрачного фото канала
        """
        try:
            from PIL import Image
            import io

            # Создаем прозрачное изображение
            img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            # Отправляем как фото канала
            data = aiohttp.FormData()
            data.add_field('chat_id', f"@{channel_username}")
            data.add_field('photo', img_bytes, filename='invisible.png', content_type='image/png')

            url = f"{self.api_url}/setChatPhoto"

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    json = await response.json()
                    return response.status == 200

        except Exception as e:
            logger.error(f"Не удалось установить невидимое фото для @{channel_username}: {e}")
            # Fallback - используем дефолтное изображение
            return await self.set_default_music_photo(channel_username)

    async def set_default_music_photo(self, channel_username: str) -> bool:
        """
        Установка дефолтного фото "нет музыки"
        """
        try:
            import os
            from pathlib import Path

            assets_path = Path(__file__).parent.parent.parent / "assets" / "no_music.png"

            if not assets_path.exists():
                logger.warning(f"Файл {assets_path} не найден, создаем простое изображение")
                return await self.set_invisible_channel_photo(channel_username)

            with open(assets_path, 'rb') as f:
                image_data = f.read()

            data = aiohttp.FormData()
            data.add_field('chat_id', f"@{channel_username}")
            data.add_field('photo', BytesIO(image_data), filename='no_music.png', content_type='image/png')

            url = f"{self.api_url}/setChatPhoto"

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    return response.status == 200

        except Exception as e:
            logger.error(f"Ошибка установки дефолтного фото: {e}")
            return False