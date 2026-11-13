#!/usr/bin/env python3
"""9:00 cash prices. One missing price is a gap. No score, no order."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

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


def clock_from_parts(parts: list[str]) -> str:
    """A Tencent clock is often one field, `2026-11-13 11:51:21`, not two."""
    for item in parts:
        found = re.search(r"(20\d{2}-\d{2}-\d{2})[ T](\d{2}:\d{2})", item)
        if found:
            return f"{found.group(1)} {found.group(2)}"
    day = next((item for item in parts if len(item) == 10 and item[4:5] == "-"), "")
    time_text = next((item for item in parts if len(item) == 8 and item[2:3] == ":"), "")
    if day and time_text:
        return f"{day} {time_text[:5]}"
    return ""


def _us_one(symbol: str, label: str) -> dict:
    """One US cash index. The three indexes share the name 美股现金."""
    parts = _split_tencent(symbol)
    if len(parts) < 5 or not parts[3] or parts[4] in ("", "0"):
        return {"symbol": label, "price": None, "prev": None, "clock": ""}
    return {
        "symbol": label,
        "price": parts[3],
        "prev": parts[4],
        "clock": clock_from_parts(parts),
    }


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


def parse_shanghai_copper(body: str) -> dict:
    """Sina nf_CU0. Field 8 is the last price and field 10 is the prior settle.

    Tencent hf_CAD is London copper. It is not this row.
    """
    fields = [item.strip() for item in body.split(",")]
    if len(fields) < 18 or not fields[8]:
        return {"price": None, "prev": None, "clock": ""}
    prev = fields[10]
    digits = "".join(ch for ch in fields[1] if ch.isdigit()).zfill(6)
    date = fields[17]
    clock = f"{date} {digits[0:2]}:{digits[2:4]}" if len(date) >= 10 else ""
    if prev in ("", "0", "0.000"):
        return {"price": fields[8], "prev": None, "clock": clock}
    return {"price": fields[8], "prev": prev, "clock": clock}


def _shanghai_copper() -> dict:
    req = urllib.request.Request(
        "https://hq.sinajs.cn/list=nf_CU0",
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
    )
    raw = urllib.request.urlopen(req, timeout=12).read().decode("gbk", "replace")
    body = raw.split('"', 1)[1].split('"', 1)[0] if '"' in raw else ""
    return parse_shanghai_copper(body)


def fetch_all() -> list[dict]:
    """Build the five rows. A source with no public price stays a gap."""
    rows = []
    for symbol, label in (("usDJI", "道指"), ("usINX", "标普500"), ("usIXIC", "纳指")):
        try:
            got = _us_one(symbol, label)
        except Exception as exc:  # noqa: BLE001 — a dead source is a gap, not a zero
            got = {"symbol": label, "price": None, "prev": None, "clock": "", "error": type(exc).__name__}
        rows.append({"name": "美股现金", **got})
    rows.append({"name": "美债", "status": "未挂", "text": "美债 公开报价未挂"})
    builders = (("原油", lambda: _hf("hf_CL")), ("沪铜", _shanghai_copper), ("美元", _usd))
    for name, builder in builders:
        try:
            got = builder()
        except Exception as exc:  # noqa: BLE001
            got = {"price": None, "prev": None, "clock": "", "error": type(exc).__name__}
        rows.append({"name": name, **got})
    return rows


def assess_one(name: str, price, previous, clock: str, symbol: str = "") -> dict:
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
        out = {"name": name, "status": "缺口", "text": f"{name} {gap}"}
        if symbol:
            out["symbol"] = symbol
        if not missing_price:
            out["price"] = float(price)
        return out
    out = {
        "name": name,
        "status": "已核",
        "price": float(price),
        "prev": float(previous),
        "clock": clock,
    }
    if symbol:
        out["symbol"] = symbol
    return out


def assess_all(rows: list[dict]) -> dict:
    if not rows:
        return {"status": "未挂", "items": []}
    items = []
    for row in rows:
        if row.get("status") == "未挂":
            items.append(
                {
                    "name": row.get("name", ""),
                    "status": "未挂",
                    "text": row.get("text") or f"{row.get('name', '')} 未挂",
                }
            )
            continue
        try:
            items.append(
                assess_one(
                    row.get("name", ""),
                    row.get("price"),
                    row.get("prev"),
                    row.get("clock") or "",
                    symbol=str(row.get("symbol") or ""),
                )
            )
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
