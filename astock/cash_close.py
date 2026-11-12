#!/usr/bin/env python3
"""9:00 cash prices. One missing price is a gap. No score, no order."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

NAMES = ("美股现金", "美债", "原油", "沪铜", "美元")

QUOTE_URL = "https://qt.gtimg.cn/q="


def _split_tencent(raw_symbol: str) -> list[str]:
    raw = urllib.request.urlopen(
        urllib.request.Request(
            QUOTE_URL + raw_symbol, headers={"User-Agent": "Mozilla/5.0"}
        ),
        timeout=12,
    ).read().decode("gbk", "replace")
    return raw.split("=", 1)[1].strip().strip(";").strip('"').split("~")


def _comma_symbol(raw_symbol: str) -> list[str]:
    raw = urllib.request.urlopen(
        urllib.request.Request(
            QUOTE_URL + raw_symbol, headers={"User-Agent": "Mozilla/5.0"}
        ),
        timeout=12,
    ).read().decode("gbk", "replace")
    body = raw.split("=", 1)[1].strip().strip(";").strip('"')
    return body.split(",")


def _hf(row_symbol: str) -> dict:
    """Tencent overseas futures (comma fields): last, prior settle, Beijing clock."""
    fields = _comma_symbol(row_symbol)
    if len(fields) < 13 or not fields[0] or fields[7] in ("", "0"):
        return {"price": None, "prev": None, "clock": ""}
    clock = f"{fields[12]} {fields[6][:5]}"
    return {"price": fields[0], "prev": fields[7], "clock": clock}


def _us_index() -> dict:
    """US cash index: last/prev close and the quote clock."""
    parts = _split_tencent("usDJI")
    if len(parts) < 6 or not parts[3]:
        return {"price": None, "prev": None, "clock": ""}
    day = next((item for item in parts if len(item) == 10 and item[4] == "-"), "")
    time_text = next(
        (item for item in parts if len(item) == 8 and item[2] == ":"), ""
    )
    clock = f"{day} {time_text[:5]}" if day and time_text else ""
    return {"price": parts[3], "prev": parts[4], "clock": clock}


def _usd() -> dict:
    """Dollar index whUSDX: last is field 3, prior reference field 6."""
    parts = _split_tencent("whUSDX")
    stamp = parts[5] if len(parts) > 5 else ""
    clock = ""
    if len(stamp) >= 12 and stamp.isdigit():
        clock = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[8:10]}:{stamp[10:12]}"
    if len(parts) < 7 or not parts[3] or parts[6] in ("", "0"):
        return {"price": None, "prev": None, "clock": clock}
    return {"price": parts[3], "prev": parts[6], "clock": clock}


def fetch_all() -> list[dict]:
    """Build the five rows. A source with no public price stays a gap."""
    builders = {
        "美股现金": _us_index,
        "原油": lambda: _hf("hf_CL"),
        "沪铜": lambda: _hf("hf_CAD"),
        "美元": _usd,
    }
    rows = []
    for name in NAMES:
        builder = builders.get(name)
        if builder is None:
            # No public host found for this name on the allowed channel list.
            rows.append({"name": name, "price": None, "prev": None, "clock": ""})
            continue
        try:
            got = builder()
        except Exception as exc:  # noqa: BLE001 — a dead source is a gap, not a zero
            got = {"price": None, "prev": None, "clock": "", "error": type(exc).__name__}
        rows.append({"name": name, **got})
    return rows


def assess_one(name: str, price, previous, clock: str) -> dict:
    if name not in NAMES:
        raise ValueError(f"不在 9:00 现金价名单里: {name}")
    missing_price = price in (None, "")
    missing_prev = previous in (None, "")
    if missing_price or missing_prev or not clock:
        if missing_price:
            gap = "缺收盘价"
        elif missing_prev:
            gap = "收盘价已核，缺前结"
        else:
            gap = "缺报价时间"
        return {"name": name, "status": "缺口", "text": f"{name} {gap}"}
    return {
        "name": name,
        "status": "已核",
        "price": float(price),
        "prev": float(previous),
        "clock": clock,
    }


def assess_all(rows: list[dict]) -> dict:
    if not rows:
        return {"status": "未挂", "items": []}
    items = []
    for row in rows:
        try:
            items.append(assess_one(row.get("name", ""), row.get("price"), row.get("prev"), row.get("clock") or ""))
        except ValueError as exc:
            items.append({"name": row.get("name", ""), "status": "未挂", "text": str(exc)})
    return {"status": "已列", "items": items}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="9:00 现金价。缺价格写缺口。不下单。")
    parser.add_argument("--json", default="", help="[{name, price, prev, clock}] 文件")
    parser.add_argument("--live", action="store_true", help="自己取价（无参数时默认自取）")
    args = parser.parse_args(argv)
    if args.live or not args.json:
        result = assess_all(fetch_all())
    else:
        try:
            rows = json.loads(open(args.json, encoding="utf-8").read())
            result = assess_all(rows)
        except (OSError, json.JSONDecodeError, ValueError):
            result = {"status": "未挂", "items": []}
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
