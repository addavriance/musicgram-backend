import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from app.bot.utils import esc, create_progress_text
from app.config import settings
from app.database.connection import get_session
from app.database.models import User, Channel
from app.services.spotify import SpotifyService

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Callback для кнопки помощи"""
    text = """
📚 *Инструкция*

*1. Подключение Spotify*
• Нажми "Подключить Spotify"
• Авторизуйся в аккаунте

*2. Создание канала*
• Создай новый канал в Telegram
• Добавь бота как админа с правами:
  - Изменять информацию канала
  - Отправлять сообщения
• Отправь: /channel @твой_канал

*3. Добавление в профиль*
• Настройки > Редактировать профиль > Канал

*Команды:*
/start - подключить Spotify
/status - проверить статус
/current - текущий трек
/channel @username - добавить канал
/disconnect - отключить
    """

    await callback.message.edit_text(text)
    await callback.answer()


@router.callback_query(F.data == "current_track")
async def callback_current_track(callback: CallbackQuery):
    """Callback для показа текущего трека"""
    user_id = callback.from_user.id

    async for db in get_session():
        try:
            # Получаем пользователя
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user or not user.is_spotify_connected:
                await callback.answer("❌ Spotify не подключен", show_alert=True)
                return

            # Получаем текущий трек
            spotify_service = SpotifyService()

            try:
                track_data = await spotify_service.get_current_track(user.spotify_access_token)

                if not track_data:
                    await callback.answer("⏸️ Ничего не играет", show_alert=True)
                    return

                parsed_track = spotify_service.parse_track_data(track_data)

                if parsed_track and parsed_track['is_playing']:
                    text = create_progress_text(parsed_track)

                    await callback.message.edit_text(text)
                else:
                    await callback.answer("⏸️ Ничего не играет", show_alert=True)

            except Exception as e:
                logger.error(f"Ошибка получения трека для пользователя {user_id}: {e}")
                await callback.answer("❌ Ошибка получения трека", show_alert=True)

        except Exception as e:
            logger.error(f"Ошибка в callback current_track для пользователя {user_id}: {e}")
            await callback.answer("❌ Ошибка получения трека", show_alert=True)


@router.callback_query(F.data == "settings")
async def callback_settings(callback: CallbackQuery):
    """Callback для настроек"""
    user_id = callback.from_user.id

    async for db in get_session():
        try:
            # Получаем пользователя и канал
            user_result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return

            channel_result = await db.execute(
                select(Channel).where(Channel.user_id == user.id)
            )
            channel = channel_result.scalar_one_or_none()

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Настройки канала", callback_data="channel_settings")],
                [InlineKeyboardButton(text="🔌 Отключить", callback_data="disconnect")],
                [InlineKeyboardButton(text="📖 Помощь", callback_data="help")]
            ])

            info = "⚠️ Канал не настроен"
            if channel:
                info = f"🎯 @{channel.channel_username}\n📅 {channel.created_at.strftime('%d.%m.%Y')}"

            text = f"⚙️ *Настройки*\n\n{esc(info)}"

            await callback.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка в callback settings для пользователя {user_id}: {e}")
            await callback.answer("❌ Ошибка получения настроек", show_alert=True)


@router.callback_query(F.data == "channel_settings")
async def callback_channel_settings(callback: CallbackQuery):
    """Callback для настроек канала"""
    user_id = callback.from_user.id

    async for db in get_session():
        try:
            # Получаем канал пользователя
            user_result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return

            channel_result = await db.execute(
                select(Channel).where(Channel.user_id == user.id)
            )
            channel = channel_result.scalar_one_or_none()

            if not channel:
                await callback.answer("❌ Канал не настроен\n\nИспользуй /help для инструкции", show_alert=True)
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить сейчас", callback_data="update_channel")],
                [InlineKeyboardButton(text="📖 Инструкция", callback_data="create_channel_help")]
            ])

            text = f"""
⚙️ *Канал @{channel.channel_username}*

📅 Создан: {channel.created_at.strftime('%d.%m.%Y')}
🔄 Обновления: каждые 5 сек
            """

            await callback.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка в callback channel_settings для пользователя {user_id}: {e}")
            await callback.answer("❌ Ошибка получения настроек канала", show_alert=True)


@router.callback_query(F.data == "create_channel_help")
async def callback_create_channel_help(callback: CallbackQuery):
    """Callback для инструкции по созданию канала"""
    text = f"""
📚 *Создание канала*

*Шаги:*
1. Telegram > Новый канал
2. Публичный канал с @username
3. Управление > Администраторы
4. Добавить @{settings.TG_BOT_USERNAME}
5. Права: изменять инфо + сообщения
6. В боте: /channel @твой_канал

*Профиль:*
Настройки > Редактировать профиль > Канал
    """

    await callback.message.edit_text(text)
    await callback.answer()


@router.callback_query(F.data == "update_channel")
async def callback_update_channel(callback: CallbackQuery):
    """Callback для обновления канала вручную"""
    user_id = callback.from_user.id

    async for db in get_session():
        try:
            # Получаем пользователя и канал
            user_result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user or not user.is_spotify_connected:
                await callback.answer("❌ Spotify не подключен", show_alert=True)
                return

            channel_result = await db.execute(
                select(Channel).where(Channel.user_id == user.id)
            )
            channel = channel_result.scalar_one_or_none()

            if not channel:
                await callback.answer("❌ Канал не настроен", show_alert=True)
                return

            try:
                from app.services.updater import TrackUpdater
                success = await TrackUpdater().update_user_manually(user_id)

                if success:
                    await callback.answer("✅ Канал обновлен!", show_alert=True)
                else:
                    await callback.answer("❌ Ошибка обновления", show_alert=True)

            except Exception as e:
                logger.error(f"Ошибка обновления канала для пользователя {user_id}: {e}")
                await callback.answer("❌ Ошибка обновления канала", show_alert=True)

        except Exception as e:
            logger.error(f"Ошибка в callback update_channel для пользователя {user_id}: {e}")
            await callback.answer("❌ Ошибка обновления", show_alert=True)


@router.callback_query(F.data == "disconnect")
async def callback_disconnect(callback: CallbackQuery):
    """Callback для отключения Spotify"""
    user_id = callback.from_user.id

    async for db in get_session():
        try:
            # Получаем пользователя
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return

            # Очищаем токены
            user.spotify_access_token = None
            user.spotify_refresh_token = None
            user.token_expires_at = None

            await db.commit()

            text = "🔌 *Spotify отключен*\n\n/start - подключить заново"
            await callback.message.edit_text(text)
            await callback.answer("Spotify отключен")

        except Exception as e:
            logger.error(f"Ошибка отключения Spotify для пользователя {user_id}: {e}")
            await callback.answer("❌ Ошибка отключения", show_alert=True)


@router.callback_query()
async def handle_unknown_callback(callback: CallbackQuery):
    """Обработка неизвестных callback queries"""
    logger.warning(f"Неизвестный callback: {callback.data} от пользователя {callback.from_user.id}")
    await callback.answer("❌ Неизвестная команда", show_alert=True)