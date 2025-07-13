from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging

from app.database.connection import get_session
from app.database.models import User
from app.services.spotify import SpotifyService

logger = logging.getLogger(__name__)

router = APIRouter()


class AuthCallbackRequest(BaseModel):
    """Модель запроса для обработки OAuth callback"""
    code: str
    state: str


class AuthResponse(BaseModel):
    """Модель ответа авторизации"""
    success: bool
    message: str
    user_id: int = None


@router.get("/url/{user_id}")
async def get_auth_url(
        user_id: int,
        spotify_service: SpotifyService = Depends(SpotifyService)
):
    """
    Получение URL для авторизации пользователя в Spotify

    Args:
        user_id: Telegram ID пользователя

    Returns:
        URL для авторизации в Spotify
    """
    try:
        auth_url = spotify_service.get_auth_url(user_id)

        logger.info(f"Создан auth URL для пользователя {user_id}")

        return {
            "auth_url": auth_url,
            "expires_in": 600  # 10 минут на авторизацию
        }
    except Exception as e:
        logger.error(f"Ошибка создания auth URL для пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Ошибка создания ссылки авторизации"
        )


@router.post("/callback", response_model=AuthResponse)
async def handle_auth_callback(
        request: AuthCallbackRequest,
        db: AsyncSession = Depends(get_session),
        spotify_service: SpotifyService = Depends(SpotifyService)
):
    """
    Обработка OAuth callback от Spotify

    Args:
        request: Данные callback (code и state)
        db: Сессия базы данных
        spotify_service: Сервис Spotify

    Returns:
        Результат авторизации
    """
    try:
        # Извлекаем user_id из state
        try:
            user_id = int(request.state)
        except ValueError:
            logger.warning(f"Неверный state в callback: {request.state}")
            raise HTTPException(
                status_code=400,
                detail="Неверный state параметр"
            )

        # Обмениваем code на токены
        try:
            tokens = await spotify_service.exchange_code_for_tokens(request.code)
        except Exception as e:
            logger.error(f"Ошибка обмена code на токены для пользователя {user_id}: {e}")
            raise HTTPException(
                status_code=400,
                detail="Ошибка получения токенов от Spotify"
            )

        # Вычисляем время истечения токена
        expires_at = datetime.utcnow() + timedelta(seconds=tokens['expires_in'])

        # Найти или создать пользователя
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if user:
            # Обновляем существующего пользователя
            await db.execute(
                update(User)
                .where(User.telegram_id == user_id)
                .values(
                    spotify_access_token=tokens['access_token'],
                    spotify_refresh_token=tokens['refresh_token'],
                    token_expires_at=expires_at,
                    updated_at=datetime.utcnow()
                )
            )
            logger.info(f"Обновлены токены для существующего пользователя {user_id}")
        else:
            # Создаем нового пользователя
            user = User(
                telegram_id=user_id,
                spotify_access_token=tokens['access_token'],
                spotify_refresh_token=tokens['refresh_token'],
                token_expires_at=expires_at
            )
            db.add(user)
            logger.info(f"Создан новый пользователь {user_id}")

        await db.commit()

        # Получаем профиль пользователя для проверки
        try:
            profile = await spotify_service.get_user_profile(tokens['access_token'])
            if profile:
                logger.info(f"Успешная авторизация пользователя {user_id}: {profile.get('display_name', 'Unknown')}")
        except Exception as e:
            logger.warning(f"Не удалось получить профиль пользователя {user_id}: {e}")

        return AuthResponse(
            success=True,
            message="Spotify успешно подключен!",
            user_id=user_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка в auth callback: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера"
        )


@router.get("/status/{user_id}")
async def get_auth_status(
        user_id: int,
        db: AsyncSession = Depends(get_session)
):
    """
    Проверка статуса авторизации пользователя

    Args:
        user_id: Telegram ID пользователя
        db: Сессия базы данных

    Returns:
        Статус авторизации
    """
    try:
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return {
                "is_connected": False,
                "message": "Пользователь не найден"
            }

        if not user.is_spotify_connected:
            return {
                "is_connected": False,
                "message": "Spotify не подключен"
            }

        is_expired = user.is_token_expired

        return {
            "is_connected": True,
            "is_token_expired": is_expired,
            "connected_at": user.created_at.isoformat(),
            "expires_at": user.token_expires_at.isoformat() if user.token_expires_at else None,
            "message": "Spotify подключен и активен" if not is_expired else "Токен истек, требуется обновление"
        }

    except Exception as e:
        logger.error(f"Ошибка проверки статуса авторизации для пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Ошибка проверки статуса"
        )


@router.delete("/disconnect/{user_id}")
async def disconnect_spotify(
        user_id: int,
        db: AsyncSession = Depends(get_session)
):
    """
    Отключение Spotify для пользователя

    Args:
        user_id: Telegram ID пользователя
        db: Сессия базы данных

    Returns:
        Результат отключения
    """
    try:
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Пользователь не найден"
            )

        # Очищаем токены
        await db.execute(
            update(User)
            .where(User.telegram_id == user_id)
            .values(
                spotify_access_token=None,
                spotify_refresh_token=None,
                token_expires_at=None,
                updated_at=datetime.utcnow()
            )
        )

        await db.commit()

        logger.info(f"Spotify отключен для пользователя {user_id}")

        return {
            "success": True,
            "message": "Spotify успешно отключен"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка отключения Spotify для пользователя {user_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Ошибка отключения Spotify"
        )