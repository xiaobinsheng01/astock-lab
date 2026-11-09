#!/usr/bin/env python3
"""Cross-year limit-up sleeve. Classifies a close and ranks the pre-market five.

The sleeve is separate from the desk behavior score. This module does not
change a weight, does not read the ledger, and does not place an order.
Live overnight queues start on 2026-12-01 and stop before 2027-02-06.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from astock.close_inputs import round_fen

WINDOW_OPEN = "2026-12-01"
WINDOW_SHUT = "2027-02-06"
MAIN_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")
# Desk hard gates. These names never enter the overnight queue.
BLOCKED = {
    "002081": "金螳螂",
    "601061": "中信金属",
    "000559": "万向钱潮",
    "601868": "中国能建",
}
VR_OVERNIGHT = 1.3
VR_VETO = 2.2

# 2026-11-09 close. Seed of the monitor, not a live tier.
SEED: tuple[dict[str, Any], ...] = (
    {"code": "002310", "name": "东方新能", "board": 2, "close": 2.55, "vr": 0.66, "seed_tier": "持仓"},
    {"code": "603366", "name": "日出东方", "board": 2, "close": 9.89, "vr": 0.10, "seed_tier": "持仓"},
    {"code": "002037", "name": "保利联合", "board": 1, "close": 7.23, "vr": 0.68, "seed_tier": "持仓"},
    {"code": "601188", "name": "龙江交通", "board": 2, "close": 4.19, "vr": 0.41, "seed_tier": "隔夜"},
    {"code": "600327", "name": "大东方", "board": 2, "close": 5.40, "vr": 0.95, "seed_tier": "隔夜"},
    {"code": "002578", "name": "闽发铝业", "board": 6, "close": 5.51, "vr": 1.19, "seed_tier": "观察"},
    {"code": "000525", "name": "红太阳", "board": 2, "close": 5.52, "vr": 1.78, "seed_tier": "观察"},
    {"code": "600278", "name": "东方创业", "board": 2, "close": 7.83, "vr": 1.50, "seed_tier": "观察"},
    {"code": "002124", "name": "天邦食品", "board": 1, "close": 2.20, "vr": 1.17, "seed_tier": "观察"},
    {"code": "600715", "name": "文投控股", "board": 1, "close": 2.59, "vr": 0.82, "seed_tier": "观察"},
    {"code": "600408", "name": "安泰集团", "board": 1, "close": 3.32, "vr": 1.24, "seed_tier": "观察"},
    {"code": "600609", "name": "金杯汽车", "board": 1, "close": 3.48, "vr": 3.67, "seed_tier": "观察"},
    {"code": "002596", "name": "海南瑞泽", "board": 1, "close": 3.48, "vr": 1.25, "seed_tier": "观察"},
    {"code": "600853", "name": "龙建股份", "board": 1, "close": 3.85, "vr": 1.76, "seed_tier": "观察"},
    {"code": "600792", "name": "云煤能源", "board": 1, "close": 4.20, "vr": 4.79, "seed_tier": "观察"},
    {"code": "002638", "name": "勤上股份", "board": 1, "close": 4.33, "vr": 1.63, "seed_tier": "观察"},
    {"code": "600121", "name": "郑州煤电", "board": 1, "close": 4.73, "vr": 1.81, "seed_tier": "观察"},
    {"code": "600892", "name": "大晟文化", "board": 1, "close": 5.09, "vr": 1.41, "seed_tier": "观察"},
    {"code": "002172", "name": "澳洋健康", "board": 1, "close": 6.18, "vr": 0.91, "seed_tier": "观察"},
    {"code": "002347", "name": "泰尔股份", "board": 1, "close": 7.00, "vr": 0.73, "seed_tier": "观察"},
    {"code": "002488", "name": "金固股份", "board": 1, "close": 7.48, "vr": 0.99, "seed_tier": "观察"},
    {"code": "603660", "name": "苏州科达", "board": 1, "close": 9.26, "vr": 0.39, "seed_tier": "观察"},
    {"code": "000530", "name": "冰山冷热", "board": 1, "close": 9.57, "vr": 0.49, "seed_tier": "观察"},
)


def orders_allowed(day: str) -> bool:
    """True only inside the 2026-12-01 window, before the 2027 festival halt."""
    return WINDOW_OPEN <= day < WINDOW_SHUT


def limit_up_price(prev_close: float) -> float:
    return round_fen(prev_close * 1.1)


def shape_of(open_: float, high: float, low: float, close: float, prev_close: float) -> str:
    """一字, T字, or 换手. 一字 is a range of at most 1 fen or 0.15% of the close."""
    span = high - low
    if span <= 0.01 or span <= close * 0.0015:
        return "一字"
    if open_ >= limit_up_price(prev_close) - 0.001:
        return "T字"
    return "换手"


def _first_close(row: dict[str, Any]) -> float | None:
    if row.get("first_close") is not None:
        return float(row["first_close"])
    board = int(row["board"])
    if board == 1:
        return float(row["close"])
    return None


def _mainboard(code: str) -> bool:
    return code.startswith(MAIN_PREFIXES)


def _blocked_name(name: str) -> bool:
    text = name.upper()
    return "ST" in text or "退" in name


def classify(row: dict[str, Any]) -> dict[str, Any]:
    """One limit-up close. Missing first-board price above board 1 stays out of the pool."""
    code = str(row["code"])
    name = str(row["name"])
    board = int(row["board"])
    close = float(row["close"])
    prev_close = float(row["prev_close"])
    open_ = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    volume = float(row["volume"])
    prev_volume = row.get("prev_volume")
    vr = None if not prev_volume else volume / float(prev_volume)
    shape = shape_of(open_, high, low, close, prev_close)
    first = _first_close(row)
    out = {
        "code": code,
        "name": name,
        "board": board,
        "close": close,
        "shape": shape,
        "vr": None if vr is None else round(vr, 4),
        "first_close": first,
        "tier": "池外",
    }
    if code in BLOCKED or not _mainboard(code) or _blocked_name(name):
        return out
    if first is None or first >= 10:
        return out
    if shape == "一字" and board in (1, 2, 3):
        out["tier"] = "持仓"
    elif board == 2 and shape == "换手" and vr is not None and vr >= VR_VETO:
        out["tier"] = "否决"
    elif board in (2, 3) and shape == "换手" and vr is not None and vr < VR_OVERNIGHT:
        out["tier"] = "隔夜"
    else:
        out["tier"] = "观察"
    return out


def _attention_key(item: dict[str, Any]) -> tuple[int, float, str] | None:
    tier = item["tier"]
    board = item["board"]
    if tier == "隔夜":
        rank = 0
    elif tier == "持仓" and board in (2, 3):
        rank = 1
    elif tier == "持仓" and board == 1:
        rank = 2
    else:
        return None
    vr = item["vr"]
    return (rank, 999.0 if vr is None else float(vr), item["code"])


def top5(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Up to five names. 隔夜, then board 2–3 一字, then board 1 一字. 观察 does not fill a seat."""
    ranked = []
    for row in rows:
        item = row if "tier" in row and "shape" in row else classify(row)
        key = _attention_key(item)
        if key is not None:
            ranked.append((key, item))
    ranked.sort(key=lambda pair: pair[0])
    return [item for _, item in ranked[:5]]


def format_monitor() -> str:
    lines = [f"初始监控 {len(SEED)} 只，种子日 2026-11-09"]
    for row in SEED:
        lines.append(
            f"{row['seed_tier']}\t{row['code']}\t{row['name']}\t{row['board']}板\t{row['close']:.2f}\t量比{row['vr']:.2f}"
        )
    return "\n".join(lines)


def format_report(day: str, rows: list[dict[str, Any]]) -> str:
    picked = top5(rows)
    gate = "可排队" if orders_allowed(day) else "窗口未开，不排队"
    lines = [f"{day} 盘前五只 {gate}"]
    if not picked:
        lines.append("五只：无")
        return "\n".join(lines)
    for index, item in enumerate(picked, start=1):
        vr = "缺" if item["vr"] is None else f"{item['vr']:.2f}"
        lines.append(
            f"{index}\t{item['tier']}\t{item['code']}\t{item['name']}\t{item['board']}板\t{item['shape']}\t收盘{item['close']:.2f}\t量比{vr}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="妖股收盘分类和盘前五只。不下单。")
    parser.add_argument("--monitor", action="store_true", help="打印 2026-11-09 初始监控")
    parser.add_argument("--day", default="", help="交易日 YYYY-MM-DD")
    parser.add_argument("--rows", default="", help="涨停收盘 JSON 列表")
    args = parser.parse_args(argv)
    if args.monitor:
        print(format_monitor())
        return 0
    if not args.day or not args.rows:
        parser.error("分类需要 --day 和 --rows")
    payload = json.loads(sys.stdin.read() if args.rows == "-" else open(args.rows, encoding="utf-8").read())
    classified = [classify(row) for row in payload]
    print(format_report(args.day, classified))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
