#!/usr/bin/env python3
"""Shanghai Composite box. Swings, averages, and the next session's label.

The arithmetic is the operation order: the last 40 completed sessions for
swings, the 20-day and 60-day simple averages, and the base cap. This module
does not change W1–W8 and does not place an order. A short or dead fetch does
not replace a snapshot that was already written.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astock.csi300 import Product, parse_eastmoney_kline, parse_ifzq, parse_newfq, parse_sina_kline
from astock.lake import write_bars
from astock.net import context as net_context
from astock.paths import LAKE

CODE = "000001"
NAME = "上证指数"
NEED = 60
WINDOW = 40
SIDE = 3
FETCH = 80
KEEP = 80
BEIJING = timezone(timedelta(hours=8))
SH = Product(CODE, NAME, "sh000001", "1.000001", 100, 2)

IFZQ_URL = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    f"?param=sh000001,day,,,{FETCH},qfq"
)
NEWFQ_URL = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    f"?param=sh000001,day,,,{FETCH},qfq"
)
SINA_KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen="
    f"{FETCH}"
)
EM_KLINE_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000001"
    f"&klt=101&fqt=1&lmt={FETCH}&end=20500101"
    "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
)


def _round(value: float, digits: int) -> float:
    factor = 10 ** digits
    nudged = value * factor + (0.5 if value >= 0 else -0.5)
    return int(nudged) / factor


def _avg(bars: list[dict], end: int, length: int) -> float:
    chunk = bars[end - length + 1 : end + 1]
    return sum(item["close"] for item in chunk) / length


def completed_bars(rows: list[dict], now: datetime) -> list[dict]:
    """Sessions through the last close. A bar dated today stays out before 15:00."""
    day = now.strftime("%Y-%m-%d")
    take_today = (now.hour, now.minute) >= (15, 0)
    by_date: dict[str, dict] = {}
    for row in rows:
        date = str(row.get("date") or "")
        if not date or date > day:
            continue
        if date == day and not take_today:
            continue
        if row.get("close") is None or row.get("high") is None or row.get("low") is None:
            continue
        by_date[date] = row
    return [by_date[key] for key in sorted(by_date)]


def swings(bars: list[dict]) -> tuple[list[dict], list[dict]]:
    """Confirmed swings whose own day sits in the last 40 sessions.

    The three days before that day may sit just outside the window. A day
    whose next three sessions are not complete is not confirmed.
    """
    start = len(bars) - WINDOW
    highs: list[dict] = []
    lows: list[dict] = []
    for index in range(start, len(bars)):
        if index < SIDE or index + SIDE >= len(bars):
            continue
        high = bars[index]["high"]
        low = bars[index]["low"]
        prev = bars[index - SIDE : index]
        nxt = bars[index + 1 : index + SIDE + 1]
        if high > max(item["high"] for item in prev) and high > max(item["high"] for item in nxt):
            highs.append(bars[index])
        if low < min(item["low"] for item in prev) and low < min(item["low"] for item in nxt):
            lows.append(bars[index])
    return highs, lows


def decide(close: float, prev_close: float, pressure: float, support: float, slope: float, ma60: float) -> str:
    """One label. A close under the 60-day average cannot be 多头."""
    above = prev_close > pressure and close > pressure
    below = prev_close < support and close < support
    bull = above and slope > 0.003
    bear = below and slope < -0.003
    if bull and close < ma60:
        bull = False
    if bull and close >= ma60:
        return "多头"
    if bear:
        return "空头"
    return "震荡"


def base_cap(label: str, close: float, ma60: float) -> str:
    if label == "多头":
        return "80%"
    if label == "空头":
        return "30%"
    if close < ma60:
        return "30%"
    return "60%"


def _fact(row: dict) -> str:
    status = row.get("状态")
    if status == "未挂":
        return "上证箱体未挂。不进权重，不下单。"
    if status == "未够":
        return f"上证日线 {row.get('根数') or 0} 根，不足 {NEED} 根，箱体未核。不进权重，不下单。"
    if row.get("箱体") == "无效":
        return (
            f"上证箱体未核，{row.get('原因')}。截至 {row.get('截至')} 收 {row.get('收')} "
            f"20日均线 {row.get('20日均线')} 60日均线 {row.get('60日均线')} "
            f"标签 {row.get('标签')} 基础总上限 {row.get('基础总上限')}。不进权重，不下单。"
        )
    wide = "宽箱" if row.get("宽箱") else "非宽箱"
    side = "不低于" if row.get("收盘相对60日") == "不低于" else "低于"
    return (
        f"上证箱体 截至 {row['截至']} 收 {row['收']} "
        f"压力 {row['压力价']}（{row['压力日']}）支撑 {row['支撑价']}（{row['支撑日']}）"
        f"箱宽 {row['箱宽'] * 100:.2f}% {wide} "
        f"20日均线 {row['20日均线']} 60日均线 {row['60日均线']} "
        f"斜率 {row['斜率'] * 100:.4f}% 收盘{side}60日均线 "
        f"标签 {row['标签']} 基础总上限 {row['基础总上限']}。不进权重，不下单。"
    )


def compute(bars: list[dict], now: datetime, source: str, mounts: list[dict]) -> dict:
    """Box from completed bars. `bars` already ends on the last close and has at least 60 rows."""
    end = len(bars) - 1
    close = bars[-1]["close"]
    prev_close = bars[-2]["close"]
    ma20 = _round(_avg(bars, end, 20), 4)
    ma20_prev = _round(_avg(bars, end - 5, 20), 4)
    ma60 = _round(_avg(bars, end, 60), 4)
    slope = _round((ma20 - ma20_prev) / ma20_prev, 6)
    highs, lows = swings(bars)
    common = {
        "代码": CODE,
        "名称": NAME,
        "截至": bars[-1]["date"],
        "采集": now.strftime("%Y-%m-%d %H:%M"),
        "根数": len(bars),
        "窗口根数": WINDOW,
        "收": close,
        "20日均线": ma20,
        "五日前列20日均线": ma20_prev,
        "60日均线": ma60,
        "斜率": slope,
        "收盘相对60日": "不低于" if close >= ma60 else "低于",
        "来源": source,
        "未挂": mounts,
        "权重": "不进W1–W8",
        "降档": "外盘档、总闸、真破位不在这一支",
        "日线": bars,
        "摆动高点": [{"日期": item["date"], "最高": item["high"]} for item in highs],
        "摆动低点": [{"日期": item["date"], "最低": item["low"]} for item in lows],
    }
    reasons = []
    if not highs:
        reasons.append("窗口内没有确认的摆动高点")
    if not lows:
        reasons.append("窗口内没有确认的摆动低点")
    if highs and lows and lows[-1]["low"] >= highs[-1]["high"]:
        reasons.append("支撑价不低于压力价")
    if reasons:
        common.update({"状态": "无效", "箱体": "无效", "原因": "，".join(reasons)})
        return common
    pressure = highs[-1]["high"]
    support = lows[-1]["low"]
    width = (pressure - support) / support
    label = decide(close, prev_close, pressure, support, slope, ma60)
    common.update(
        {
            "状态": "已核",
            "箱体": "有效",
            "压力价": pressure,
            "压力日": highs[-1]["date"],
            "支撑价": support,
            "支撑日": lows[-1]["date"],
            "箱宽": _round(width, 6),
            "宽箱": width >= 0.08,
            "标签": label,
            "标签来源": "当日",
            "基础总上限": base_cap(label, close, ma60),
        }
    )
    common["事实"] = _fact(common)
    return common


def finish(result: dict, previous: dict) -> dict:
    """Carry yesterday's label when this box is invalid. Then write the one sentence."""
    filled = dict(result)
    if filled.get("状态") == "无效":
        old = previous.get("标签") if previous else None
        if old in {"多头", "空头", "震荡"}:
            filled["标签"] = old
            filled["标签来源"] = "沿用上一交易日"
            filled["基础总上限"] = base_cap(old, filled["收"], filled["60日均线"])
        else:
            filled["标签"] = "未核"
            filled["标签来源"] = "无上一交易日"
            filled["基础总上限"] = "未核"
    filled["事实"] = _fact(filled)
    return filled


def _read(get, url: str, parser, mounts: list[dict]) -> dict | None:
    try:
        raw = get(url)
    except Exception as exc:  # noqa: BLE001 — a dead host is 未挂, not a zero
        mounts.append({"source": url, "status": "未挂", "error": type(exc).__name__})
        return None
    parsed = parser(raw)
    if parsed.get("status") == "未挂":
        mounts.append({"source": url, "status": "未挂", "error": parsed.get("error") or "空"})
        return None
    return parsed


def collect(get, now: datetime) -> dict:
    """First source with 60 completed bars wins. A later source does not cover its prices."""
    mounts: list[dict] = []
    best_count = 0
    best_source = ""
    chain = (
        (IFZQ_URL, lambda raw: parse_ifzq(raw, SH)),
        (NEWFQ_URL, lambda raw: parse_newfq(raw, SH)),
        (SINA_KLINE_URL, parse_sina_kline),
        (EM_KLINE_URL, parse_eastmoney_kline),
    )
    for url, parser in chain:
        parsed = _read(get, url, parser, mounts)
        if not parsed:
            continue
        done = completed_bars(parsed["rows"], now)
        if len(done) > best_count:
            best_count = len(done)
            best_source = parsed["source"]
        if len(done) >= NEED:
            return compute(done[-KEEP:], now, parsed["source"], mounts)
        mounts.append({"source": url, "status": "未够", "error": f"{len(done)}根"})
    blank = {
        "代码": CODE,
        "名称": NAME,
        "来源": best_source,
        "未挂": mounts,
        "根数": best_count,
        "权重": "不进W1–W8",
    }
    if best_count == 0:
        blank["状态"] = "未挂"
    else:
        blank["状态"] = "未够"
    blank["事实"] = _fact(blank)
    return blank


def _snapshot_path(root: Path) -> Path:
    return root / "hot" / "snapshots" / "箱体.json"


def _load_previous(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def store(result: dict, root: Path | None = None) -> dict:
    """Write the snapshot and the long daily line. A dead fetch keeps the previous file."""
    lake = root or LAKE
    path = _snapshot_path(lake)
    previous = _load_previous(path)
    if result.get("状态") in {"未挂", "未够"} and previous:
        return {"snapshot": "保留上一份", "bars": "保留上一份", "快照": previous}
    filled = finish(result, previous)
    bars = filled.pop("日线", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(filled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written = {"snapshot": str(path), "快照": filled}
    if bars and result.get("状态") in {"已核", "无效"}:
        written["bars"] = write_bars(lake, CODE, bars, keep=KEEP)
    else:
        written["bars"] = "未写"
    return written


def _live_get(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    if "sina" in url:
        headers["Referer"] = "https://finance.sina.com.cn"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20, context=net_context()) as resp:
        return resp.read().decode("utf-8", "replace")


def beijing_now() -> datetime:
    return datetime.now(BEIJING).replace(tzinfo=None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="上证箱体、20日和60日均线。缺日线写未核。不下单。")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写资料湖")
    args = parser.parse_args(argv)
    result = collect(_live_get, beijing_now())
    if args.dry_run:
        shown = finish(result, {})
    else:
        written = store(result)
        shown = dict(written.get("快照") or finish(result, {}))
        shown["written"] = {key: value for key, value in written.items() if key != "快照"}
    shown.pop("日线", None)
    json.dump(shown, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
