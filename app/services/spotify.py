import aiohttp
import base64
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class SpotifyService:
    """Сервис для работы с Spotify API"""

    def __init__(self):
        self.client_id = settings.SPOTIFY_CLIENT_ID
        self.client_secret = settings.SPOTIFY_CLIENT_SECRET
        self.redirect_uri = settings.SPOTIFY_REDIRECT_URI

    def get_auth_url(self, user_id: int) -> str:
        """Получение URL для авторизации пользователя"""
        scopes = [
            'user-read-currently-playing',
            'user-read-playback-state',
            'user-read-recently-played'
        ]

        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': ' '.join(scopes),
            'state': str(user_id),  # Передаем ID пользователя
            'show_dialog': 'false'
        }

        return f"{settings.spotify_auth_url}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """Обмен authorization code на access/refresh токены"""
        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    settings.spotify_token_url,
                    headers=headers,
                    data=data
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    logger.error(f"Ошибка получения токенов Spotify: {error}")
                    raise Exception(f"Spotify token error: {response.status}")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Обновление access токена"""
        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    settings.spotify_token_url,
                    headers=headers,
                    data=data
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    logger.error(f"Ошибка обновления токена Spotify: {error}")
                    raise Exception(f"Spotify refresh error: {response.status}")

    async def get_current_track(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Получение текущего трека пользователя"""
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f"{settings.spotify_api_url}/me/player/currently-playing",
                    headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 204:
                    # Ничего не играет
                    return None
                else:
                    logger.warning(f"Spotify API error: {response.status}")
                    return None

    async def get_user_profile(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Получение профиля пользователя Spotify"""
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f"{settings.spotify_api_url}/me",
                    headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Spotify profile error: {response.status}")
                    return None

    @staticmethod
    def parse_track_data(track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Парсинг данных трека в удобный формат"""
        if not track_data or not track_data.get('item'):
            return None

        item = track_data['item']

        return {
            'id': item.get('id'),
            'name': item.get('name'),
            'artist': ', '.join([artist['name'] for artist in item.get('artists', [])]),
            'album': item.get('album', {}).get('name'),
            'duration_ms': item.get('duration_ms'),
            'progress_ms': track_data.get('progress_ms', 0),
            'is_playing': track_data.get('is_playing', False),
            'image_url': (
                item.get('album', {}).get('images', [{}])[0].get('url')
                if item.get('album', {}).get('images')
                else None
            ),
            'external_url': item.get('external_urls', {}).get('spotify'),
            'preview_url': item.get('preview_url')
        }