import asyncio


def esc(text: str) -> str:
    """Escape markdown symbols in text"""
    if not text:
        return text

    replacements = {
        '_': r'\_',
        '*': r'\*',
        '[': r'\[',
        ']': r'\]',
        '`': r'\`',
        '~': r'\~',
    }

    for char, escaped in replacements.items():
        text = text.replace(char, escaped)

    return text


async def delete_channel_msg(channel_username: str, message_id: int):
    """Attempts to delete a channel message via ChannelManager with one retry on failure"""

    from .channel import ChannelManager
    success = await ChannelManager().delete_message(channel_username, message_id)

    if not success:
        await asyncio.sleep(1)
        await ChannelManager().delete_message(channel_username, message_id)
