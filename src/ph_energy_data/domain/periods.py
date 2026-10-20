def previous_period(period: str) -> str:
    """Previous billing month for a `YYYY-MM` period."""
    year, month = int(period[:4]), int(period[5:])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"
