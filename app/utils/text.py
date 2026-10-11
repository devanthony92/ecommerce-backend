import unicodedata


def normalize(text: str) -> str:
    """Minúsculas y sin tildes: "Riñonera" → "rinonera" (búsqueda sin tildes)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))
