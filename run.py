import asyncio
import signal

import uvicorn
import logging

from app.config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def start_bot():
    """Запуск Telegram бота"""
    try:
        from app.bot.main import start_bot as bot_start
        await bot_start()
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")


async def start_updater():
    """Запуск сервиса обновления треков"""
    try:
        from app.services.updater import TrackUpdater
        updater = TrackUpdater()
        await updater.start()
    except Exception as e:
        logger.error(f"Ошибка запуска обновлятора: {e}")


async def start_api():
    """Запуск FastAPI сервера"""
    try:
        from main import app
        config = uvicorn.Config(
            app,
            host=settings.API_HOST,
            port=settings.API_PORT,
            log_level="info" if settings.DEBUG else "warning"
        )
        server = uvicorn.Server(config)

        # Отключаем встроенную обработку сигналов
        server.install_signal_handlers = lambda: None

        await server.serve()

    except asyncio.CancelledError:
        logger.info("🛑 API сервер остановлен")
    except Exception as e:
        logger.error(f"Ошибка запуска API: {e}")
        raise


async def graceful_shutdown(tasks, timeout=10):
    """Корректная остановка задач с таймаутом"""
    logger.info("🛑 Начинаем корректную остановку...")

    # Сначала пытаемся остановить бота
    try:
        from app.bot.main import on_shutdown as stop_bot
        await stop_bot()
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при остановке бота: {e}")

    # Отменяем все задачи
    for task in tasks:
        if not task.done():
            task.cancel()

    # Ждем завершения с таймаутом
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout
        )
        logger.info("✅ Все задачи корректно остановлены")
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ Таймаут {timeout}с при остановке задач")
        # Принудительно прерываем оставшиеся задачи
        for task in tasks:
            if not task.done():
                task.cancel()
        # Даем еще немного времени
        await asyncio.gather(*tasks, return_exceptions=True)


async def main():
    """Главная функция запуска всех сервисов"""
    logger.info("🚀 Запуск Spotify Telegram Status...")

    # Создаем задачи
    bot_task = asyncio.create_task(start_bot())
    updater_task = asyncio.create_task(start_updater())
    api_task = asyncio.create_task(start_api())

    tasks = [bot_task, updater_task, api_task]

    # Обработчик сигнала
    stop_event = asyncio.Event()

    def shutdown():
        logger.info("🛑 Получен сигнал остановки")
        stop_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    try:
        # Ждем либо завершения любой задачи, либо сигнала остановки
        done, pending = await asyncio.wait(
            tasks + [asyncio.create_task(stop_event.wait())],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Если сработал сигнал остановки или одна из задач завершилась
        await graceful_shutdown(tasks)

    except KeyboardInterrupt:
        logger.info("🛑 Получен KeyboardInterrupt")
        await graceful_shutdown(tasks)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        await graceful_shutdown(tasks)
    finally:
        logger.info("👋 Приложение остановлено")

if __name__ == "__main__":
    # Проверяем основные настройки
    if not settings.TG_BOT_TOKEN:
        logger.error("❌ TG_BOT_TOKEN не задан в переменных окружения")
        exit(1)

    if not settings.SPOTIFY_CLIENT_ID:
        logger.error("❌ SPOTIFY_CLIENT_ID не задан в переменных окружения")
        exit(1)

    logger.info(f"🔧 Режим: {'DEBUG' if settings.DEBUG else 'PRODUCTION'}")
    logger.info(f"🌐 API будет доступен на: http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"🤖 Telegram бот: @{settings.TG_BOT_USERNAME}")

    # Запускаем приложение
    asyncio.run(main())
