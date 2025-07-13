from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.database.models import Base
import logging

logger = logging.getLogger(__name__)

# Создание асинхронного движка
engine = create_async_engine(
    settings.database_url,
    # echo=settings.DEBUG,  # Логирование SQL запросов в режиме отладки (оооочень часто логирует)
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600,  # Переподключение каждый час
)

# Фабрика сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def create_tables():
    """Создание всех таблиц в базе данных"""
    try:
        async with engine.begin() as conn:
            # Создаем все таблицы
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Таблицы базы данных созданы успешно")
    except Exception as e:
        logger.error(f"Ошибка создания таблиц: {e}")
        raise


async def get_session() -> AsyncSession:
    """Получение асинхронной сессии базы данных"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка в сессии БД: {e}")
            raise
        finally:
            await session.close()


class DatabaseManager:
    """Менеджер для работы с базой данных"""

    @staticmethod
    async def init_database():
        """Инициализация базы данных"""
        await create_tables()

    @staticmethod
    async def close_database():
        """Закрытие соединения с базой данных"""
        await engine.dispose()
        logger.info("Соединение с базой данных закрыто")
