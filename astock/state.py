#!/usr/bin/env python3
"""Portable desk state: the info cursor and the W1–W5 cells.

Unlike the machine-local ledger (``runtime/info-ledger.md``), these files are
tracked by git, so a fresh machine keeps the cursor and the official numbers
already written into weights. This module does not place an order.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astock.paths import CURSOR_FILE, WEIGHTS_FILE

BEIJING = timezone(timedelta(hours=8))
WEIGHT_KEYS = ("W1", "W2", "W3", "W4", "W5")


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_cursor() -> str:
    return str(_load(CURSOR_FILE, {}).get("cursor") or "")


def write_cursor(cursor: str, *, force: bool = False) -> dict:
    """Advance the cursor. It only moves forward unless `force` is set."""
    current = read_cursor()
    if current and cursor < current and not force:
        return {"status": "未推进", "cursor": current, "asked": cursor}
    _dump(CURSOR_FILE, {"cursor": cursor, "updated_at": beijing_now()})
    return {"status": "已推进", "cursor": cursor, "previous": current}


def beijing_now() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def read_weights() -> dict:
    payload = _load(WEIGHTS_FILE, {})
    cells = payload.get("cells") or {}
    return {key: cells.get(key) for key in WEIGHT_KEYS}


def set_weight(key: str, value, reason: str, source: str, *, clock: str = "") -> dict:
    """Write one official number into a W1–W5 cell.

    This is the entry point that was missing: facts can be recorded in the
    ledger and still leave the score untouched; here a confirmed number is
    attached to its weight with a source and timestamp.
    """
    if key not in WEIGHT_KEYS:
        raise ValueError(f"只能写 W1–W5: {key}")
    number = value
    if value not in (None, ""):
        number = float(value)
    payload = _load(WEIGHTS_FILE, {"cells": {}, "history": []})
    cells = payload.get("cells") or {}
    history = payload.get("history") or []
    previous = cells.get(key)
    cells[key] = {
        "value": number,
        "reason": reason,
        "source": source,
        "clock": clock or beijing_now(),
    }
    history.append(
        {
            "key": key,
            "from": None if previous is None else previous.get("value"),
            "to": number,
            "source": source,
            "clock": clock or beijing_now(),
        }
    )
    _dump(WEIGHTS_FILE, {"cells": cells, "history": history[-200:]})
    return {"key": key, "previous": previous, "current": cells[key]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="可移植游标与 W1–W5 权重。不下单。")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cursor = sub.add_parser("cursor")
    cursor.add_argument("--set", default="", help="推进到这个北京时间")
    cursor.add_argument("--now", action="store_true", help="推进到当前北京时间")
    cursor.add_argument("--force", action="store_true")

    weight = sub.add_parser("weight")
    weight.add_argument("--key", required=True)
    weight.add_argument("--value", required=True)
    weight.add_argument("--reason", default="")
    weight.add_argument("--source", default="")
    weight.add_argument("--clock", default="")

    show = sub.add_parser("show")

    args = parser.parse_args(argv)
    if args.cmd == "cursor":
        if args.now:
            target = beijing_now()
        elif args.set:
            target = args.set
        else:
            target = read_cursor()
            print(json.dumps({"cursor": target}, ensure_ascii=False))
            return 0
        result = write_cursor(target, force=args.force)
    elif args.cmd == "weight":
        try:
            result = set_weight(
                args.key,
                args.value,
                args.reason,
                args.source,
                clock=args.clock,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        result = {"cursor": read_cursor(), "weights": read_weights()}
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
