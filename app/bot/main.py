import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.bot.handlers import commands, callbacks
from app.services.channel_service import service_router

logger = logging.getLogger(__name__)

# Создание бота
bot = Bot(
    token=settings.TG_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)

# Создание диспетчера
dp = Dispatcher()

# dp.message.middleware(AutoEscapeMiddleware(auto_escape=True, preserve_entities=True))
# dp.callback_query.middleware(AutoEscapeMiddleware(auto_escape=True, preserve_entities=True))

# ВАЖНО: Регистрируем роутер для служебных сообщений ПЕРВЫМ
dp.include_router(service_router)
dp.include_router(commands.router)
dp.include_router(callbacks.router)


async def on_startup():
    """Функция запуска бота"""
    logger.info(f"🤖 Telegram бот @{settings.TG_BOT_USERNAME} запускается...")

    # Проверяем доступность бота
    try:
        bot_info = await bot.get_me()
        logger.info(f"✅ Бот {bot_info.first_name} (@{bot_info.username}) готов к работе")
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о боте: {e}")
        raise

    # Устанавливаем команды бота
    from aiogram.types import BotCommand
    commands = [
        BotCommand(command="start", description="🎵 Начать работу с ботом"),
        BotCommand(command="help", description="📚 Подробная инструкция"),
        BotCommand(command="status", description="📊 Проверить статус подключения"),
        BotCommand(command="current", description="🎧 Показать текущий трек"),
        BotCommand(command="channel", description="🔗 Добавить канал"),
        BotCommand(command="disconnect", description="🔌 Отключить Spotify"),
    ]

    try:
        await bot.set_my_commands(commands)
        logger.info("✅ Команды бота установлены")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить команды бота: {e}")


async def on_shutdown():
    """Функция остановки бота"""
    logger.info("🛑 Остановка Telegram бота...")
    await bot.session.close()
    logger.info("👋 Telegram бот остановлен")


async def start_bot():
    """Запуск бота с обработкой ошибок"""
    try:
        await on_startup()

        # Запускаем polling
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "channel_post"],
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            handle_signals=False
        )
    except Exception as e:
        logger.error(f"❌ Критическая ошибка бота: {e}")
        raise
    finally:
        await on_shutdown()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(start_bot())