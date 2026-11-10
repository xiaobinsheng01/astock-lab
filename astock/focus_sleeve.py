#!/usr/bin/env python3
"""Watch sleeve for theme, solar, media, and robots.

These names are marks. They do not enter the drive list, do not score, and do
not place an order. A theme with too few limit-up names recommends nobody.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from astock.sector_drive import (
    _earnings_key,
    _fetch,
    _line_key,
    _num,
    fetch_closes,
    fetch_earnings,
    fetch_holders,
    holder_simple,
    ma10_gap_pct,
    main_board,
    near_ma,
    prior_complex,
    state_capital,
)

CAP_YI = 600.0
HELD = {"002081", "601061", "000559", "601868", "600127", "000725", "600330"}
DIRECTIONS = (
    {"name": "光伏", "board": "BK1031", "also": ""},
    {"name": "传媒", "board": "BK0486", "also": ""},
    {"name": "机器人", "board": "BK1090", "also": "BK1237"},
)


def theme_state(first, second) -> str:
    """Limit-up concentration only. Height and a dated catalyst stay outside."""
    top = _num(first)
    nxt = _num(second)
    if top is None or nxt is None:
        return "未核"
    if top >= 15 and top >= 1.5 * nxt:
        return "只数够"
    return "不成立"


def cap_state(cap_yi) -> str:
    value = _num(cap_yi)
    if value is None or value <= 0:
        return "unchecked"
    if value < CAP_YI:
        return "pass"
    return "fail"


def span_pct(closes: list[float], days: int):
    if len(closes) <= days or closes[-1 - days] <= 0:
        return None
    return (closes[-1] / closes[-1 - days] - 1.0) * 100.0


def sleeve_members(board: str, also: str) -> list[dict]:
    """Main board under 600亿. Robots also have to sit in automation equipment."""
    rows = {
        row["code"]: row
        for row in board_members(board)
        if main_board(row["code"]) and cap_state(row["cap_yi"]) == "pass"
    }
    if also:
        keep = {
            row["code"]
            for row in board_members(also)
            if main_board(row["code"]) and cap_state(row["cap_yi"]) == "pass"
        }
        rows = {code: row for code, row in rows.items() if code in keep}
    return list(rows.values())


def miss_counts(rows: list[dict]) -> dict:
    """First failed gate among names already inside the cap."""
    counts = {"near": 0, "holder": 0, "earnings": 0}
    for row in rows:
        if row.get("cap") != "pass":
            continue
        if row.get("near") != "pass":
            counts["near"] += 1
        elif row.get("holder") != "simple":
            counts["holder"] += 1
        elif row.get("earnings") != "pass":
            counts["earnings"] += 1
    return counts


def rank_rows(rows: list[dict]) -> list[dict]:
    passed = []
    for row in rows:
        if row.get("cap") != "pass" or row.get("near") != "pass":
            continue
        if row.get("holder") != "simple" or row.get("earnings") != "pass":
            continue
        if row["code"] in HELD:
            continue
        passed.append(row)
    passed.sort(key=lambda row: (*_earnings_key(row), *_line_key(row.get("ma10_gap_pct"))))
    return passed


_EM_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
)


def _em_json(path: str) -> dict:
    last = None
    for host in _EM_HOSTS:
        for _try in range(2):
            try:
                raw = _fetch(host + path).decode("utf-8", "replace")
                return json.loads(raw)
            except Exception as exc:  # noqa: BLE001 — one 502 does not end the sleeve
                last = exc
    if last:
        raise last
    return {}


def board_members(board: str) -> list[dict]:
    rows = []
    page = 1
    while page <= 20:
        path = (
            "/api/qt/clist/get?pn=%s&pz=100&po=1&np=1&fltt=2&invt=2"
            "&fid=f20&fs=b:%s&fields=f12,f14,f20"
        ) % (page, board)
        data = (_em_json(path).get("data") or {}).get("diff") or []
        if not data:
            break
        for item in data:
            cap = _num(item.get("f20"))
            rows.append(
                {
                    "code": str(item.get("f12") or ""),
                    "name": item.get("f14") or "",
                    "cap_yi": None if cap is None else cap / 1e8,
                }
            )
        if len(data) < 100:
            break
        page += 1
    return rows


def board_closes(board: str) -> list[float]:
    path = (
        "/api/qt/stock/kline/get?secid=90.%s&klt=101&fqt=1"
        "&lmt=12&end=20500101&fields1=f1,f2,f3&fields2=f51,f53"
    ) % board
    raw = _fetch("https://push2his.eastmoney.com" + path).decode("utf-8", "replace")
    klines = ((json.loads(raw).get("data") or {}).get("klines")) or []
    out = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 2:
            continue
        close = _num(parts[1])
        if close is not None:
            out.append(close)
    return out


def shanghai_closes() -> list[float]:
    urls = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,12,qfq",
        "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?param=sh000001,day,,,12,qfq",
    )
    for url in urls:
        try:
            raw = _fetch(url).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        if "=" in raw[:40]:
            raw = raw.split("=", 1)[1]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        node = (payload.get("data") or {}).get("sh000001") or {}
        bars = node.get("qfqday") or node.get("day") or []
        out = []
        for bar in bars:
            close = _num(bar[2]) if len(bar) > 2 else None
            if close is not None:
                out.append(close)
        if out:
            return out
    return []


def limit_up_counts(day: str) -> tuple:
    path = (
        "/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989"
        f"&dpt=wz.ztzt&Pageindex=0&pagesize=500&sort=fbt:asc&date={day}"
    )
    raw = _fetch("https://push2ex.eastmoney.com" + path).decode("utf-8", "replace")
    pool = ((json.loads(raw).get("data") or {}).get("pool")) or []
    counts: dict[str, int] = {}
    for item in pool:
        name = item.get("hybk") or "?"
        counts[name] = counts.get(name, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: -item[1])
    if not ordered:
        return None, None, []
    second = ordered[1][1] if len(ordered) > 1 else 0
    return ordered[0][1], second, ordered[:3]


def _one(row: dict) -> dict:
    closes = []
    try:
        closes = [px for _day, px in fetch_closes(row["code"])]
    except Exception:  # noqa: BLE001
        closes = []
    near = near_ma(closes)
    earned = {"earnings": "unchecked"}
    holders = []
    try:
        earned = fetch_earnings(row["code"])
    except Exception:  # noqa: BLE001
        earned = {"earnings": "unchecked"}
    try:
        holders = fetch_holders(row["code"])
    except Exception:  # noqa: BLE001
        holders = []
    gap = None
    if near.get("ma10") and near.get("close"):
        gap = ma10_gap_pct(near["close"], near["ma10"])
    return {
        **row,
        "cap": cap_state(row.get("cap_yi")),
        "near": near.get("state"),
        "ma5": near.get("ma5"),
        "ma10": near.get("ma10"),
        "close": near.get("close"),
        "ma10_gap_pct": gap,
        "holder": holder_simple(holders),
        "prior_complex": prior_complex(holders),
        "state_capital": state_capital(holders[0] if holders else []),
        **earned,
    }


def _map(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    out = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_one, row): index for index, row in enumerate(rows)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                out[index] = future.result()
            except Exception:  # noqa: BLE001
                out[index] = {**rows[index], "near": "unchecked", "holder": "unchecked", "earnings": "unchecked", "cap": "unchecked"}
    return [row for row in out if row]


def screen(day: str) -> dict:
    sh = shanghai_closes()
    theme_top, theme_second, theme_names = limit_up_counts(day.replace("-", ""))
    sleeves = []
    for item in DIRECTIONS:
        members = sleeve_members(item["board"], item["also"])
        checked = _map(members)
        names = rank_rows(checked)
        misses = miss_counts(checked)
        closes = board_closes(item["board"])
        sleeves.append(
            {
                "name": item["name"],
                "board": item["board"],
                "candidates": len(members),
                "day5": span_pct(closes, 5),
                "day10": span_pct(closes, 10),
                "sh5": span_pct(sh, 5),
                "sh10": span_pct(sh, 10),
                "names": names,
                "misses": misses,
            }
        )
    return {
        "theme": theme_state(theme_top, theme_second),
        "theme_top": theme_names,
        "sleeves": sleeves,
    }


def _fmt(value, digits: int) -> str:
    number = _num(value)
    if number is None:
        return "未核"
    return f"{number:.{digits}f}"


def main() -> int:
    payload = screen("2026-11-09")
    print(f"题材 {payload['theme']}")
    for name, count in payload["theme_top"]:
        print(f"涨停行业 {name} {count}")
    for sleeve in payload["sleeves"]:
        print(
            f"{sleeve['name']} {sleeve['board']} 5日 {_fmt(sleeve['day5'], 2)}% "
            f"10日 {_fmt(sleeve['day10'], 2)}% 上证5日 {_fmt(sleeve['sh5'], 2)}% "
            f"上证10日 {_fmt(sleeve['sh10'], 2)}% 主板小于600亿 {sleeve['candidates']} "
            f"未贴均线 {sleeve['misses']['near']} 结构未过 {sleeve['misses']['holder']} 业绩未过 {sleeve['misses']['earnings']}"
        )
        names = sleeve["names"]
        if not names:
            print(f"{sleeve['name']} 无")
            continue
        for index, row in enumerate(names):
            mark = "最优" if index == 0 else "过线"
            profit = _num(row.get("profit"))
            profit_yi = None if profit is None else profit / 1e8
            print(
                " ".join(
                    [
                        mark,
                        row["code"],
                        row.get("name") or "",
                        "市值",
                        _fmt(row.get("cap_yi"), 2),
                        "收",
                        _fmt(row.get("close"), 2),
                        "5日",
                        _fmt(row.get("ma5"), 2),
                        "10日",
                        _fmt(row.get("ma10"), 2),
                        "距10日",
                        _fmt(row.get("ma10_gap_pct"), 2),
                        "利润亿",
                        _fmt(profit_yi, 2),
                        "净利同比",
                        _fmt(row.get("profit_yoy"), 1),
                        "报告",
                        str(row.get("report") or "未核"),
                    ]
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
