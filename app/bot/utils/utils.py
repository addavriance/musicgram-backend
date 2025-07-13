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