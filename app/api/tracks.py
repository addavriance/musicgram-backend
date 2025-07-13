from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import func
import logging

from app.bot.utils import create_progress_bar
from app.database.connection import get_session
from app.database.models import User
from app.services.spotify import SpotifyService

logger = logging.getLogger(__name__)

router = APIRouter()


class CurrentTrackResponse(BaseModel):
    """Модель ответа с текущим треком"""
    is_playing: bool
    track: Optional[dict] = None
    progress_bar: Optional[str] = None
    message: str


class UserTrackUpdate(BaseModel):
    """Модель для обновления трека пользователя"""
    user_id: int
    track_data: Optional[dict] = None
    is_playing: bool = False


@router.get("/current/{user_id}", response_model=CurrentTrackResponse)
async def get_current_track(
        user_id: int,
        db: AsyncSession = Depends(get_session),
        spotify_service: SpotifyService = Depends(SpotifyService)
):
    """
    Получение текущего трека пользователя

    Args:
        user_id: Telegram ID пользователя
        db: Сессия базы данных
        spotify_service: Сервис Spotify

    Returns:
        Информация о текущем треке
    """
    try:
        # Получаем пользователя из БД
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=404,
                detail="Пользователь не найден"
            )

        if not user.is_spotify_connected:
            return CurrentTrackResponse(
                is_playing=False,
                message="Spotify не подключен"
            )

        # Проверяем и обновляем токен если нужно
        access_token = user.spotify_access_token

        if user.is_token_expired:
            try:
                # Обновляем токен
                new_tokens = await spotify_service.refresh_access_token(user.spotify_refresh_token)

                # Обновляем в БД
                expires_at = datetime.utcnow() + timedelta(seconds=new_tokens['expires_in'])
                await db.execute(
                    update(User)
                    .where(User.telegram_id == user_id)
                    .values(
                        spotify_access_token=new_tokens['access_token'],
                        token_expires_at=expires_at,
                        updated_at=datetime.utcnow()
                    )
                )
                await db.commit()

                access_token = new_tokens['access_token']
                logger.info(f"Токен обновлен для пользователя {user_id}")

            except Exception as e:
                logger.error(f"Ошибка обновления токена для пользователя {user_id}: {e}")
                return CurrentTrackResponse(
                    is_playing=False,
                    message="Ошибка обновления токена. Требуется повторная авторизация"
                )

        # Получаем текущий трек
        try:
            track_data = await spotify_service.get_current_track(access_token)

            if not track_data:
                return CurrentTrackResponse(
                    is_playing=False,
                    message="Ничего не играет"
                )

            # Парсим данные трека
            parsed_track = spotify_service.parse_track_data(track_data)

            if not parsed_track:
                return CurrentTrackResponse(
                    is_playing=False,
                    message="Не удалось получить информацию о треке"
                )

            # Создаем прогресс-бар
            progress_bar = None
            if parsed_track['is_playing'] and parsed_track['duration_ms'] > 0:
                progress_bar = create_progress_bar(
                    parsed_track['progress_ms'],
                    parsed_track['duration_ms']
                )

            return CurrentTrackResponse(
                is_playing=parsed_track['is_playing'],
                track=parsed_track,
                progress_bar=progress_bar,
                message="Трек получен успешно"
            )

        except Exception as e:
            logger.error(f"Ошибка получения трека для пользователя {user_id}: {e}")
            return CurrentTrackResponse(
                is_playing=False,
                message="Ошибка получения трека от Spotify"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении трека для пользователя {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера"
        )


@router.get("/users", response_model=List[int])
async def get_connected_users(
        db: AsyncSession = Depends(get_session)
):
    """
    Получение списка пользователей с подключенным Spotify

    Returns:
        Список Telegram ID пользователей
    """
    try:
        result = await db.execute(
            select(User.telegram_id)
            .where(User.spotify_access_token.isnot(None))
        )
        user_ids = [row[0] for row in result.fetchall()]

        logger.debug(f"Найдено {len(user_ids)} пользователей с подключенным Spotify")
        return user_ids

    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        raise HTTPException(
            status_code=500,
            detail="Ошибка получения списка пользователей"
        )


@router.post("/update-batch")
async def update_tracks_batch(
        updates: List[UserTrackUpdate],
        db: AsyncSession = Depends(get_session)
):
    """
    Пакетное обновление треков для нескольких пользователей
    Используется сервисом обновления треков

    Args:
        updates: Список обновлений треков
        db: Сессия базы данных

    Returns:
        Результат пакетного обновления
    """
    try:
        updated_count = 0
        errors = []

        for update in updates:
            try:
                # Здесь можно добавить логику сохранения последнего трека
                # для каждого пользователя, если понадобится
                updated_count += 1

            except Exception as e:
                logger.error(f"Ошибка обновления трека для пользователя {update.user_id}: {e}")
                errors.append({
                    "user_id": update.user_id,
                    "error": str(e)
                })

        return {
            "updated_count": updated_count,
            "total_count": len(updates),
            "errors": errors,
            "success": len(errors) == 0
        }

    except Exception as e:
        logger.error(f"Ошибка пакетного обновления треков: {e}")
        raise HTTPException(
            status_code=500,
            detail="Ошибка пакетного обновления"
        )


@router.get("/stats")
async def get_stats(
        db: AsyncSession = Depends(get_session)
):
    """
    Получение статистики по пользователям и трекам

    Returns:
        Статистика сервиса
    """
    try:
        # Общее количество пользователей
        total_users_result = await db.execute(
            select(func.count(User.id))
        )
        total_users = total_users_result.scalar()

        # Пользователи с подключенным Spotify
        connected_users_result = await db.execute(
            select(func.count(User.id))
            .where(User.spotify_access_token.isnot(None))
        )
        connected_users = connected_users_result.scalar()

        # Пользователи с истекшими токенами
        expired_tokens_result = await db.execute(
            select(func.count(User.id))
            .where(
                User.spotify_access_token.isnot(None),
                User.token_expires_at < datetime.utcnow()
            )
        )
        expired_tokens = expired_tokens_result.scalar()

        return {
            "total_users": total_users,
            "connected_users": connected_users,
            "expired_tokens": expired_tokens,
            "active_users": connected_users - expired_tokens,
            "connection_rate": round((connected_users / total_users * 100), 2) if total_users > 0 else 0,
            "last_updated": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        raise HTTPException(
            status_code=500,
            detail="Ошибка получения статистики"
        )
