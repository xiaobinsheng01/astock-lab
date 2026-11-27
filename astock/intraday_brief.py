#!/usr/bin/env python3
"""One quote batch for the written path and the written sector groups.

Prints the Shanghai segment and whether bank and electronics point opposite ways.
Does not screen constituents, does not read the ledger, does not score, and does
not place an order.
"""

from __future__ import annotations

import argparse

import astock.holdings as holdings
from astock.close_inputs import favored_path
from astock.sector_drive import _fetch, _num
from astock.util import market_symbol

BASKET = (
    "000001",
    "399006",
    "000688",
    "000852",
    "399986",
    "399811",
    "000685",
    "399389",
    "000993",
    "000807",
    "399998",
)

# Prior-session low and high per code, used only to say which band the live
# price sits in. The date is written next to the number: a stale band is a
# dated band, not a silently wrong one. Codes missing here print 未核.
BANDS: dict[str, tuple[str, float, float]] = {
    "000725": ("2026-11-25", 4.39, 4.52),
    "002081": ("2026-11-25", 3.87, 4.24),
    "000559": ("2026-11-25", 9.77, 10.79),
    "601061": ("2026-11-25", 8.08, 8.39),
    "600715": ("2026-11-25", 2.83, 3.22),
    "600327": ("2026-11-25", 4.77, 5.39),
    "601188": ("2026-11-25", 4.11, 4.66),
}


def prefix(code: str) -> str:
    return market_symbol(code)


def segment(px: float, low: float, high: float) -> str:
    mid = (low + high) / 2.0
    if px > high:
        return "昨日高点之上"
    if px > mid:
        return "中点到昨日高点"
    if px >= low:
        return "昨日低点到中点"
    return "昨日低点之下"


def pair(bank, electronics) -> str:
    if bank is None or electronics is None:
        return "未核"
    if bank == 0 or electronics == 0 or (bank > 0) == (electronics > 0):
        return "同向或平盘"
    return "相反"


def path_text(prior_high: float, session_high, above_older: bool, w3_negative: bool, a50_gap: bool) -> str:
    kind = favored_path(prior_high, session_high, above_older, w3_negative, a50_gap)
    if kind == "above_prior_high":
        return f"收在{prior_high:.2f}之上"
    if kind == "narrow_lower":
        return "窄区间"
    return "未改主路径"


def live_quotes(codes: list[str]) -> dict:
    """Quotes for the given codes. An unreachable host returns an empty map.

    Callers print 未挂 for a name that has no row, so a dead network is a dated
    gap in the output rather than a traceback.
    """
    if not codes:
        return {}
    try:
        raw = _fetch("https://qt.gtimg.cn/q=" + ",".join(prefix(code) for code in codes)).decode("gbk", "replace")
    except Exception:  # noqa: BLE001 — an unreachable quote host is not fatal here
        return {}
    out = {}
    for chunk in raw.split(";"):
        if "~" not in chunk:
            continue
        parts = chunk.split('"', 1)[-1].split("~")
        if len(parts) < 35:
            continue
        out[parts[2]] = {
            "name": parts[1].replace(" ", ""),
            "px": _num(parts[3]),
            "open": _num(parts[5]),
            "pct": _num(parts[32]),
            "high": _num(parts[33]),
            "low": _num(parts[34]),
            "ts": parts[30],
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact intraday path quotes")
    parser.add_argument("--low", type=float, required=True)
    parser.add_argument("--high", type=float, required=True)
    parser.add_argument("--prev-close-above-older", action="store_true")
    parser.add_argument("--w3-negative", action="store_true")
    parser.add_argument("--a50-gap", action="store_true")
    args = parser.parse_args()
    basket = live_quotes(list(BASKET))
    if not basket:
        print("未挂：行情主机没有返回，落点、主路径和银行对电子本轮不写")
    rows = holdings.book()
    held = live_quotes([str(row["代码"]) for row in rows]) if rows else {}
    sh = basket.get("000001") or {}
    px, high, low = sh.get("px"), sh.get("high"), sh.get("low")
    bank = (basket.get("399986") or {}).get("pct")
    elec = (basket.get("399811") or {}).get("pct")
    print(f"上证 {px} 涨跌 {sh.get('pct')} 高 {high} 低 {low} 开 {sh.get('open')} 时点 {sh.get('ts')}")
    if px is not None:
        print(f"落点 {segment(px, args.low, args.high)} 中点 {(args.low + args.high) / 2:.2f}")
    else:
        print("落点 未挂")
    print(f"主路径 {path_text(args.high, high, args.prev_close_above_older, args.w3_negative, args.a50_gap)}")
    print(f"银行与电子 {pair(bank, elec)}")
    for code in ("399986", "399811", "000685", "000993", "399389", "000688", "399006", "000852", "000807", "399998"):
        row = basket.get(code) or {}
        print(f"{code} {row.get('name')} {row.get('px')} {row.get('pct')} 高 {row.get('high')} 低 {row.get('low')}")
    print("持仓")
    if not rows:
        print(f"无。{holdings.clock() or '未提供'}没有持仓文件")
    for row in rows:
        code = str(row["代码"])
        quote = held.get(code) or {}
        band = BANDS.get(code)
        if band is None:
            place = "未核"
        else:
            band_day, hard_low, hard_high = band
            place = f"{segment(quote['px'], hard_low, hard_high)} {band_day}" if quote.get("px") is not None else "未核"
        crossed = ""
        if band is not None and quote.get("high") is not None and quote["high"] > band[2]:
            crossed = f" 高点越过{band[2]}"
        print(
            f"{code} {quote.get('name') or row.get('名称')} {quote.get('px')} {quote.get('pct')} "
            f"高 {quote.get('high')} 低 {quote.get('low')} {place}{crossed}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
