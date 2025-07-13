from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""

    # Основные настройки
    DEBUG: bool = True
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # База данных
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "spotify_user"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "spotify_telegram"

    # Spotify API
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
    SPOTIFY_REDIRECT_URI: str = "http://localhost:3000/auth/callback"

    # Telegram Bot
    TG_BOT_TOKEN: str = ""
    TG_BOT_USERNAME: str = ""
    TG_BOT_ID: str = ""

    # Фронтенд
    FRONTEND_URL: str = "http://localhost:3000"

    # Обновления
    UPDATE_INTERVAL: int = 5  # секунды

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def database_url(self) -> str:
        """URL для подключения к MySQL"""
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"

    @property
    def spotify_auth_url(self) -> str:
        """Базовый URL для авторизации Spotify"""
        return "https://accounts.spotify.com/authorize"

    @property
    def spotify_token_url(self) -> str:
        """URL для получения токенов Spotify"""
        return "https://accounts.spotify.com/api/token"

    @property
    def spotify_api_url(self) -> str:
        """Базовый URL Spotify API"""
        return "https://api.spotify.com/v1"


settings = Settings()
