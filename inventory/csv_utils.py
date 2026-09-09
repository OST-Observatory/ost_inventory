"""CSV formula-injection helpers (CWE-1236)."""

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value) -> str:
    """Neutralize spreadsheet formulas after optional leading whitespace."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    stripped = text.lstrip(" \t")
    if stripped[:1] in _DANGEROUS_PREFIXES:
        return "'" + text
    return text
