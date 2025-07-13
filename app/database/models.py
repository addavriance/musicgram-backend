from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import datetime

Base = declarative_base()


class User(Base):
    """Пользователь с подключенным Spotify"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)

    # Spotify токены
    spotify_access_token = Column(Text, nullable=True)
    spotify_refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    # Временные метки
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Связи
    channels = relationship("Channel", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id})>"

    @property
    def is_spotify_connected(self):
        """Проверка подключения Spotify"""
        return self.spotify_access_token is not None

    @property
    def is_token_expired(self):
        """Проверка истечения токена"""
        if not self.token_expires_at:
            return True
        return datetime.datetime.utcnow() >= self.token_expires_at


class Channel(Base):
    """Канал пользователя в Telegram"""
    __tablename__ = 'channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    # Информация о канале
    channel_username = Column(String(255), nullable=False)
    last_message_id = Column(Integer, nullable=True)

    # Информация о последнем треке
    last_track_id = Column(String(255), nullable=True)
    last_track_name = Column(String(500), nullable=True)
    last_track_artist = Column(String(500), nullable=True)
    last_track_image_url = Column(Text, nullable=True)

    # Временные метки
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Связи
    user = relationship("User", back_populates="channels")

    def __repr__(self):
        return f"<Channel(username={self.channel_username}, user_id={self.user_id})>"

    @property
    def telegram_channel_id(self):
        """ID канала для Telegram API"""
        return f"@{self.channel_username}"
