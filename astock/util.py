"""Shared constants and small numeric helpers. Stdlib only.

These were copied into several modules before. Keeping one copy here means a
market-prefix or a rounding rule cannot drift between calculators.
"""

from __future__ import annotations

# Index codes whose first digit does not name the exchange.
SH_INDEX_CODES = frozenset(
    {"000001", "000016", "000300", "000688", "000852", "000685", "000807", "000993", "000941"}
)
MAIN_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")


def num(value):
    """A float, or None. An empty string and a dash are not zero."""
    if value is None or value == "" or value == "-":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def market_prefix(code: str) -> str:
    """`sh` or `sz` for a six-digit code. ETFs and funds on 5xx are Shanghai."""
    text = "".join(ch for ch in str(code) if ch.isdigit())
    if text.startswith(("5", "6", "9")) or text in SH_INDEX_CODES:
        return "sh"
    return "sz"


def market_symbol(code: str) -> str:
    """`sh600000` / `sz000725`, the form the quote host wants."""
    text = "".join(ch for ch in str(code) if ch.isdigit())
    return market_prefix(text) + text


def round_half_up(value: float) -> int:
    """Half away from zero, the 四舍五入 the rules ask for.

    Python's round() is bankers' rounding, so round(0.5) is 0 and a W6 average
    of +0.5 would be written as 0 instead of +1.
    """
    if value >= 0:
        return int(value + 0.5)
    return -int(-value + 0.5)


def round_pct(value: float) -> float:
    """Round a percent to two decimals, half away from zero."""
    return round_half_up(value * 100) / 100.0
