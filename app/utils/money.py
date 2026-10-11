def format_cop(amount: int) -> str:
    """120000 → "$120.000" (mismo formato que el frontend, sin decimales)."""
    return f"${amount:,}".replace(",", ".")
