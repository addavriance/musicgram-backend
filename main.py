"""Главное FastAPI приложение"""
import asyncio

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database.connection import DatabaseManager
from app.api import auth, tracks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Запуск
    logger.info("🚀 Запуск FastAPI приложения...")
    try:
        await DatabaseManager.init_database()
        logger.info("✅ База данных инициализирована в lifespan")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise

    try:
        yield
    except asyncio.CancelledError:
        logger.info("🛑 Lifespan получил CancelledError - нормальная остановка")
    finally:
        # Остановка
        logger.info("🛑 Остановка FastAPI приложения...")
        try:
            await DatabaseManager.close_database()
            logger.info("👋 FastAPI приложение остановлено")
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке FastAPI: {e}")


# Создание FastAPI приложения
app = FastAPI(
    title="Spotify Telegram Status API",
    description="API для интеграции Spotify с Telegram каналами",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "https://*.github.io",  # Для GitHub Pages
        "https://*.ngrok-free.app",
        "https://8369-45-82-31-119.ngrok-free.app",
        "https://31df9f8a47d2.ngrok-free.app"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# Глобальный обработчик ошибок
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Глобальный обработчик исключений"""
    logger.error(f"Необработанная ошибка: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Внутренняя ошибка сервера",
            "error": str(exc) if settings.DEBUG else None
        }
    )


# Подключение роутеров
app.include_router(auth.router, prefix="/auth", tags=["Авторизация"])
app.include_router(tracks.router, prefix="/tracks", tags=["Треки"])


@app.get("/", tags=["Главная"])
async def root():
    """Главная страница API"""
    return {
        "message": "Spotify Telegram Status API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled"
    }


@app.get("/health", tags=["Системные"])
async def health_check():
    """Проверка состояния сервиса"""
    try:
        # Можно добавить проверку БД и других сервисов
        return {
            "status": "healthy",
            "database": "connected",
            "spotify_api": "available",
            "telegram_bot": "running"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )