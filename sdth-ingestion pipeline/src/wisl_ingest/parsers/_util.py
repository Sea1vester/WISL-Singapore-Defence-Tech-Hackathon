from __future__ import annotations


def parse_kv_pairs(text: str) -> dict[str, float | str]:
    """Parses whitespace-separated key=value tokens, coercing numeric values to float."""
    result: dict[str, float | str] = {}
    for token in text.split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        try:
            result[key] = float(value)
        except ValueError:
            result[key] = value
    return result
