def format_time(ms: int) -> str:
    """
    Форматирование времени из миллисекунд в MM:SS

    Args:
        ms: Время в миллисекундах

    Returns:
        Отформатированное время в формате MM:SS
    """
    if ms < 0:
        ms = 0

    minutes = ms // 60000
    seconds = (ms % 60000) // 1000
    return f"{minutes}:{seconds:02d}"


def create_progress_bar(current_ms: int, total_ms: int, length: int = 15) -> str:
    """
    Создание прогресс-бара трека

    Args:
        current_ms: Текущее время воспроизведения в миллисекундах
        total_ms: Общая длительность трека в миллисекундах
        length: Длина прогресс-бара в символах

    Returns:
        Строка с прогресс-баром
    """
    if total_ms <= 0:
        return "-:- " + "─" * length + " -:-"

    current_ms = max(0, min(current_ms, total_ms))

    progress = current_ms / total_ms
    filled_length = int(length * progress)

    filled = "━" * filled_length
    dot = "●" if filled_length < length else ""
    empty = "─" * max(0, length - filled_length - (1 if dot else 0))

    current_time = format_time(current_ms)
    remaining_time = format_time(total_ms - current_ms)

    return f"{current_time} {filled}{dot}{empty} -{remaining_time}"


def create_progress_text(track_data: dict) -> str:
    """
    Создание полного текста с информацией о треке и прогресс-баром

    Args:
        track_data: Данные трека со всеми полями

    Returns:
        Отформатированный текст для отправки в канал
    """

    if not track_data or not track_data.get('is_playing'):
        return "⏸️ Ничего не играет"

    from app.bot.utils.utils import esc
    track_name = esc(track_data.get('name', 'Unknown Track'))
    artist = esc(track_data.get('artist', 'Unknown Artist'))

    # Создаем прогресс-бар если есть данные о времени
    progress_bar = ""
    if track_data.get('duration_ms', 0) > 0:
        progress_bar = create_progress_bar(
            track_data.get('progress_ms', 0),
            track_data['duration_ms']
        )
        progress_bar = f"\n\n`{progress_bar}`"

    return f"🎵 *{track_name}*\n👤 {artist}{progress_bar}"


def create_simple_progress_bar(current_ms: int, total_ms: int) -> str:
    """
    Создание простого прогресс-бара без времени (для коротких сообщений)

    Args:
        current_ms: Текущее время в миллисекундах
        total_ms: Общее время в миллисекундах

    Returns:
        Простой прогресс-бар
    """

    if total_ms <= 0:
        return "⏸️"

    progress = max(0, min(current_ms / total_ms, 1))
    length = 15  # Короткий бар
    filled_length = int(length * progress)

    filled = "━" * filled_length
    dot = "●" if filled_length < length else ""
    empty = "─" * max(0, length - filled_length - (1 if dot else 0))

    return f"{filled}{dot}{empty}"


def get_track_emoji(track_data: dict) -> str:
    """
    Получение эмодзи для трека на основе его данных

    Args:
        track_data: Данные трека

    Returns:
        Подходящий эмодзи
    """

    if not track_data or not track_data.get('is_playing'):
        return "⏸️"

    # TODO: increase variety of emojis depending on track genre, etc.
    return "🎵"


def create_channel_title(track_data: dict) -> str:
    """
    Создание названия канала на основе трека

    Args:
        track_data: Данные трека

    Returns:
        Название для канала
    """
    if not track_data or not track_data.get('is_playing'):
        return "⏸ Ничего не играет"

    track_name = track_data.get('name', 'Unknown Track')
    artist = track_data.get('artist', 'Unknown Artist')

    # Ограничиваем длину названия канала (Telegram лимит ~255 символов)
    max_length = 100
    title = f"🎵 {track_name} - {artist}"

    if len(title) > max_length:
        # Обрезаем с сохранением важной части
        available_length = max_length - 7  # "🎵  - " + "..."
        track_part = min(len(track_name), available_length // 2)
        artist_part = available_length - track_part

        title = f"🎵 {track_name[:track_part]} - {artist[:artist_part]}..."

    return title
