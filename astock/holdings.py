#!/usr/bin/env python3
"""Positions read from one book. No score, no order.

`runtime/lake/hot/snapshots/手写持仓.json` is the only place a position lives.
The quote basket and the intraday band table read it. Nothing here invents a
share count, and a missing file is an empty book.

The four hard-gate codes are not read from this file: the rules name them by
code, so a position that leaves the book stays gated.
"""

from __future__ import annotations

import json
from pathlib import Path

from astock.paths import HOLDINGS_FILE

# Hard gates the rules name by code, not by whatever the book says today.
# 金螳螂 sells only, 中信 below 9.55 still cuts 1000, 万向 and 能建 never add.
HARD_GATE = {
    "002081": "金螳螂",
    "601061": "中信金属",
    "000559": "万向钱潮",
    "601868": "中国能建",
}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def book(path: Path | None = None) -> list[dict]:
    """Every position row. A row without a code is dropped."""
    payload = _load(path or HOLDINGS_FILE)
    rows = [row for row in payload.get("持仓") or [] if isinstance(row, dict) and row.get("代码")]
    return rows


def codes(path: Path | None = None) -> list[str]:
    """Held codes, in book order, without duplicates."""
    seen: list[str] = []
    for row in book(path):
        code = str(row["代码"])
        if code not in seen:
            seen.append(code)
    return seen


def held_set(path: Path | None = None) -> set[str]:
    return set(codes(path))


def clock(path: Path | None = None) -> str:
    """When the user handed over this book. Empty when the file is missing."""
    return str(_load(path or HOLDINGS_FILE).get("北京时间") or "")
