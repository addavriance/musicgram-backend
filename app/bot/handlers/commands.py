import logging
from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select

from app.bot.utils import esc
from app.config import settings
from app.database.connection import get_session
from app.database.models import User, Channel
from app.services.spotify import SpotifyService
from app.bot.utils.progress import create_progress_text

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start - начало работы с ботом"""
    user_id = message.from_user.id
    auth_url = SpotifyService().get_auth_url(user_id)

    # Создаем кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎧 Подключить Spotify",
                url=auth_url  # Замени на твой домен
            )
        ],
        [
            InlineKeyboardButton(text="❓ Помощь", callback_data="help")
        ]
    ])

    text = """
🎵 *Spotify Status Bot*

Отображай музыку в профиле Telegram через канал.

*Возможности:*
• Автообновление каждые 5 секунд
• Прогресс-бар трека
• Обложка как аватар канала

👇 *Начни с подключения Spotify*
    """

    await message.answer(text, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help - подробная инструкция"""
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

    await message.answer(text)


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Команда /status - проверка статуса подключения"""
    user_id = message.from_user.id

    async for db in get_session():
        try:
            # Получаем пользователя
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )

            user = result.scalar_one_or_none()
            auth_url = SpotifyService().get_auth_url(user_id)

            if not user or not user.is_spotify_connected:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🎧 Подключить Spotify",
                            url=auth_url
                        )
                    ]
                ])

                await message.answer(
                    "❌ *Spotify не подключен*\n\nДля работы нужно подключить аккаунт Spotify.",
                    reply_markup=keyboard
                )
                return

            # Получаем канал пользователя
            channel_result = await db.execute(
                select(Channel).where(Channel.user_id == user.id)
            )
            channel = channel_result.scalar_one_or_none()

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🎵 Текущий трек", callback_data="current_track"),
                    InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
                ]
            ])

            channel_info = f"🎯 Канал: @{channel.channel_username}" if channel else "⚠️ Канал не настроен. Используй /channel"

            text = f"""
✅ *Spotify подключен*

📅 Подключен: {user.created_at.strftime('%d.%m.%Y')}
{esc(channel_info)}
🔄 Обновления: каждые 5 сек
            """

            await message.answer(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка в команде /status для пользователя {user_id}: {e}")
            await message.answer("❌ Ошибка проверки статуса. Попробуй позже.")


@router.message(Command("current"))
async def cmd_current(message: Message):
    """Команда /current - показать текущий трек"""
    user_id = message.from_user.id

    async for db in get_session():
        try:
            # Получаем пользователя
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user or not user.is_spotify_connected:
                await message.answer("❌ Spotify не подключен. Используй /start")
                return

            # Получаем текущий трек через API
            spotify_service = SpotifyService()

            try:
                track_data = await spotify_service.get_current_track(user.spotify_access_token)

                if not track_data:
                    await message.answer("⏸️ Ничего не играет")
                    return

                parsed_track = spotify_service.parse_track_data(track_data)

                if parsed_track and parsed_track['is_playing']:
                    text = create_progress_text(parsed_track)

                    await message.answer(text)
                else:
                    await message.answer("⏸️ Ничего не играет")

            except Exception as e:
                logger.error(f"Ошибка получения трека для пользователя {user_id}: {e}")
                await message.answer("❌ Ошибка получения трека. Попробуй переподключить: /start")

        except Exception as e:
            logger.error(f"Ошибка в команде /current для пользователя {user_id}: {e}")
            await message.answer("❌ Ошибка получения трека. Попробуй позже.")


@router.message(Command("disconnect"))
async def cmd_disconnect(message: Message):
    """Команда /disconnect - отключение Spotify"""
    user_id = message.from_user.id

    async for db in get_session():
        try:
            # Получаем пользователя
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                await message.answer("❌ Пользователь не найден")
                return

            # Очищаем токены
            user.spotify_access_token = None
            user.spotify_refresh_token = None
            user.token_expires_at = None

            await db.commit()

            await message.answer("🔌 *Spotify отключен*\n\n/start - подключить заново")

        except Exception as e:
            logger.error(f"Ошибка отключения Spotify для пользователя {user_id}: {e}")
            await message.answer("❌ Ошибка отключения. Попробуй позже.")


@router.message(Command("channel"))
async def cmd_channel(message: Message):
    """Команда /channel - добавление канала"""
    user_id = message.from_user.id

    # Получаем аргумент команды
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if not args:
        await message.answer("""
❌ *Неверный формат команды*

Используй: `/channel @твой_канал`
Или: `/channel https://t.me/твой_канал`

Перед этим:
1. Создай канал в Telegram
2. Добавь @{} как администратора
3. Дай права на изменение информации и отправку сообщений
        """.format(settings.TG_BOT_USERNAME))
        return

    channel_url = args[0]

    async for db in get_session():
        try:
            # Получаем пользователя
            result = await db.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user or not user.is_spotify_connected:
                await message.answer("❌ Сначала подключи Spotify через /start")
                return

            # Извлекаем username канала
            from app.bot.utils import ChannelManager
            channel_manager = ChannelManager()
            channel_username = channel_manager.extract_channel_username(channel_url)

            if not channel_username:
                await message.answer("❌ *Неверная ссылка на канал*\n\nФормат: /channel @твой_канал")
                return

            # Проверяем права бота в канале
            is_admin = await channel_manager.check_bot_admin_status(channel_username)

            if not is_admin:
                await message.answer(f"""
❌ *Нет прав админа*

Добавь бота в канал @{channel_username} как администратора с правами:
• Изменять информацию канала
• Отправлять сообщения
• Редактировать сообщения
                """)
                return

            # Сохраняем или обновляем канал
            channel_result = await db.execute(
                select(Channel).where(Channel.user_id == user.id)
            )
            channel = channel_result.scalar_one_or_none()

            if channel:
                channel.channel_username = channel_username
            else:
                channel = Channel(
                    user_id=user.id,
                    channel_username=channel_username
                )
                db.add(channel)

            await db.commit()

            # Инициализируем канал
            await channel_manager.initialize_channel(channel_username, user_id)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🎵 Обновить", callback_data="update_channel"),
                    InlineKeyboardButton(text="⚙️ Настройки", callback_data="channel_settings")
                ]
            ])

            text = f"""
✅ *Канал настроен*

🎯 @{channel_username}
⏱️ Обновления каждые 5 сек

*Добавь канал в профиль*"""

            await message.answer(esc(text), reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка настройки канала для пользователя {user_id}: {e}")
            await message.answer("❌ Ошибка настройки канала")


@router.message()
async def handle_unknown_message(message: Message):
    """Обработка неизвестных сообщений"""
    text = """
🤖 *Команды:*

/start - подключить Spotify
/help - инструкция
/status - статус подключения
/current - текущий трек
/channel @username - настроить канал
/disconnect - отключить

❓ /help для подробностей
    """

    await message.answer(text)