#!/usr/bin/env python3
"""A-share ETF turnover, then the sector indexes that actually moved.

Amount comes from Tencent bars that print turnover. Volume is never converted
into amount. A wide ETF does not name an industry. A sector ETF that did not
expand does not become an anomaly. This does not score and does not place an order.
"""

from __future__ import annotations

import json

from astock.sector_drive import _fetch, _num

EXPAND = 1.30
SHRINK = 0.70
TOL_YI = 0.05
SH_PREFIX = {
    "000001",
    "000016",
    "000300",
    "000688",
    "000852",
    "000685",
    "000807",
    "000905",
    "000819",
    "000991",
    "000993",
}

# kind, code, label, index code or "", limit printed beside an anomaly.
BASKET = (
    ("wide", "510050", "上证50ETF", "000016", ""),
    ("wide", "510300", "沪深300ETF", "000300", ""),
    ("wide", "510500", "中证500ETF", "000905", ""),
    ("wide", "512100", "中证1000ETF", "000852", ""),
    ("wide", "159915", "创业板ETF", "399006", ""),
    ("wide", "588000", "科创50ETF", "000688", ""),
    ("sector", "512480", "半导体ETF", "000685", ""),
    ("sector", "515260", "电子ETF", "399811", ""),
    ("sector", "515880", "通信ETF", "399389", ""),
    ("sector", "512800", "银行ETF", "399986", "不进修复"),
    ("sector", "515170", "食品饮料ETF", "000807", "不改第二托"),
    ("sector", "515220", "煤炭ETF", "399998", "不进托住"),
    ("sector", "512690", "酒ETF", "399997", "不升托"),
    ("sector", "512010", "医药ETF", "000991", "不进互斥"),
    ("sector", "512880", "证券ETF", "399975", "不进发力"),
    ("sector", "512400", "有色金属ETF", "000819", "不升成托"),
    ("sector", "516160", "新能源ETF", "399808", "不进发力"),
    ("sector", "512660", "军工ETF", "399967", "不进发力，不进托住"),
    ("sector", "512200", "房地产ETF", "399393", "不进互斥，不进托住"),
    ("sector", "515790", "光伏ETF", "", "没有对照指数"),
)


def prefix(code: str) -> str:
    if code.startswith(("5", "6", "9")) or code in SH_PREFIX:
        return "sh" + code
    return "sz" + code


def volume_state(ratio) -> str:
    value = _num(ratio)
    if value is None:
        return "未核"
    if value >= EXPAND:
        return "放量"
    if value <= SHRINK:
        return "缩量"
    return "平量"


def price_pct(last, prev):
    last_px = _num(last)
    prev_px = _num(prev)
    if last_px is None or prev_px is None or prev_px <= 0:
        return None
    return (last_px / prev_px - 1.0) * 100.0


def anomaly(kind: str, index_code: str, index_pct, shanghai_pct, state: str) -> str:
    """Sector move only after that ETF expanded. Wide ETFs stay on the index."""
    if kind == "wide":
        return "宽基"
    if not index_code:
        return "不写异动"
    if state != "放量":
        return "不写异动"
    if index_pct is None or shanghai_pct is None:
        return "未核"
    if index_pct > 0 and index_pct - shanghai_pct >= 1.0:
        return "异动偏多"
    if index_pct <= -1.0:
        return "异动偏空"
    return "有量无异动"


def classify_amount(bars: list[tuple[str, float]], quote_date: str, quote_yi) -> dict:
    """Match the quote, then divide by the prior five sessions."""
    empty = {"state": "未核", "ratio": None, "today_yi": None, "avg5_yi": None}
    amount = _num(quote_yi)
    if amount is None or amount <= 0 or not quote_date or len(bars) < 6:
        return empty
    if bars[-1][0] != quote_date:
        return empty
    bar_yi = bars[-1][1] / 10000.0
    if abs(bar_yi - amount) > TOL_YI:
        return empty | {"bar_yi": round(bar_yi, 2)}
    prior = [bars[-6 + i][1] / 10000.0 for i in range(5)]
    avg5 = sum(prior) / 5.0
    if avg5 <= 0:
        return empty
    ratio = amount / avg5
    return {
        "state": volume_state(ratio),
        "ratio": ratio,
        "today_yi": amount,
        "avg5_yi": avg5,
    }


def quote_day(ts: str) -> str:
    digits = "".join(ch for ch in ts if ch.isdigit())
    if len(digits) < 8:
        return ""
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def amount_bars(code: str) -> list[tuple[str, float]]:
    key = prefix(code)
    url = (
        "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
        f"?param={key},day,,,12,qfq"
    )
    raw = _fetch(url).decode("utf-8", "replace")
    if "=" in raw[:20]:
        raw = raw.split("=", 1)[1]
    node = (json.loads(raw).get("data") or {}).get(key) or {}
    rows = node.get("qfqday") or node.get("day") or []
    out = []
    for row in rows:
        if len(row) < 9:
            continue
        amount = _num(row[8])
        if amount is None:
            continue
        out.append((str(row[0]), amount))
    return out


def fetch_quotes(codes: list[str]) -> dict:
    raw = _fetch("https://qt.gtimg.cn/q=" + ",".join(prefix(code) for code in codes)).decode("gbk", "replace")
    out = {}
    for chunk in raw.split(";"):
        if "~" not in chunk:
            continue
        parts = chunk.split('"', 1)[-1].split("~")
        if len(parts) < 35:
            continue
        amount_wan = _num(parts[37]) if len(parts) > 37 else None
        out[parts[2]] = {
            "name": parts[1].replace(" ", ""),
            "px": _num(parts[3]),
            "prev": _num(parts[4]),
            "pct": price_pct(parts[3], parts[4]),
            "amount_yi": None if amount_wan is None else amount_wan / 10000.0,
            "day": quote_day(parts[30]),
        }
    return out


def _fmt(value, digits: int) -> str:
    number = _num(value)
    if number is None:
        return "未核"
    return f"{number:.{digits}f}"


def screen() -> list[dict]:
    codes = ["000001"]
    for _kind, code, _label, index, _limit in BASKET:
        codes.append(code)
        if index:
            codes.append(index)
    quotes = fetch_quotes(codes)
    shanghai = (quotes.get("000001") or {}).get("pct")
    rows = []
    for kind, code, label, index, limit in BASKET:
        quote = quotes.get(code) or {}
        try:
            bars = amount_bars(code)
        except Exception:  # noqa: BLE001 — one failed bar stays unchecked
            bars = []
        amount = classify_amount(bars, quote.get("day") or "", quote.get("amount_yi"))
        index_pct = (quotes.get(index) or {}).get("pct") if index else None
        rows.append(
            {
                "kind": kind,
                "code": code,
                "label": label,
                "index": index,
                "limit": limit,
                "state": amount["state"],
                "ratio": amount["ratio"],
                "today_yi": amount["today_yi"],
                "avg5_yi": amount["avg5_yi"],
                "index_pct": index_pct,
                "shanghai_pct": shanghai,
                "move": anomaly(kind, index, index_pct, shanghai, amount["state"]),
            }
        )
    return rows


def main() -> int:
    rows = screen()
    if not rows:
        print("未核")
        return 0
    shanghai = rows[0]["shanghai_pct"]
    print(f"上证涨跌 {_fmt(shanghai, 2)}%")
    print("宽基")
    for row in rows:
        if row["kind"] != "wide":
            continue
        print(
            f"{row['code']} {row['label']} {row['state']} 当日 {_fmt(row['today_yi'], 2)}亿 "
            f"前5日均 {_fmt(row['avg5_yi'], 2)}亿 比值 {_fmt(row['ratio'], 3)} "
            f"对照 {row['index']} {_fmt(row['index_pct'], 2)}%"
        )
    print("行业")
    for row in rows:
        if row["kind"] != "sector":
            continue
        extra = f" {row['limit']}" if row["limit"] and row["move"].startswith("异动") else ""
        if row["index"]:
            beside = f"对照 {row['index']} {_fmt(row['index_pct'], 2)}%"
        else:
            beside = "无对照指数"
        print(
            f"{row['code']} {row['label']} {row['state']} 当日 {_fmt(row['today_yi'], 2)}亿 "
            f"前5日均 {_fmt(row['avg5_yi'], 2)}亿 比值 {_fmt(row['ratio'], 3)} "
            f"{beside} {row['move']}{extra}"
        )
    print("异动")
    moved = [row for row in rows if row["move"] in {"异动偏多", "异动偏空"}]
    if not moved:
        print("无")
        return 0
    for row in moved:
        gap = None
        if row["index_pct"] is not None and row["shanghai_pct"] is not None:
            gap = row["index_pct"] - row["shanghai_pct"]
        limit = f" {row['limit']}" if row["limit"] else ""
        print(
            f"{row['code']} {row['label']} {row['move']} 对照 {row['index']} {_fmt(row['index_pct'], 2)}% "
            f"相对上证 {_fmt(gap, 2)} 个百分点 比值 {_fmt(row['ratio'], 3)}{limit}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
