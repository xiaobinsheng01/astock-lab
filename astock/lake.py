#!/usr/bin/env python3
"""Hot and archive storage for one desk. No score, no order.

Quotes in the hot layer stay until the next trading day's 终分 has been
written and read. Weekends and holidays still get a quote file. News is
replaced by url instead of appended twice. A 终分 result file is written
once. Archive runs only after that file exists, and only moves dated files
from before that session.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from astock.paths import LAKE

PRICE_KEYS = ("open", "high", "low", "close", "px", "last", "price", "prev_close")
BAR_FIELDS = ("open", "high", "low", "close")
FACT_KEYS = ("url", "地址", "link")
RESULT_KINDS = ("终分", "对照", "盘中-1000", "盘中-1250", "盘中-1400")


def _load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_weekend(day: str) -> bool:
    return date.fromisoformat(day).weekday() >= 5


def _has_price(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    for key, value in payload.items():
        if key in PRICE_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if isinstance(value, dict) and _has_price(value):
            return True
    return False


def _fact_key(fact: dict) -> str:
    for key in FACT_KEYS:
        value = fact.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def _merge_facts(rows: list[dict]) -> list[dict]:
    merged: list[dict] = []
    index: dict[str, int] = {}
    for row in rows:
        key = _fact_key(row)
        if key and key in index:
            merged[index[key]] = row
            continue
        if key:
            index[key] = len(merged)
        merged.append(row)
    return merged


def hot_quote_dates(
    sessions: list[str],
    *,
    today: str,
    today_has_open: bool,
    final_dates: list[str],
) -> list[str]:
    """Sessions still in the hot layer.

    A finished 终分 on `trade_date` archives every hot file strictly before
    that date. Until then, weekend and holiday files stay in the list with
    the trading sessions. The list is not cut down to two dates.
    """
    ordered = sorted(set(sessions))
    if today_has_open and today not in ordered:
        ordered.append(today)
        ordered.sort()
    if not ordered:
        return []
    latest_final = max(final_dates) if final_dates else ""
    return [item for item in ordered if not latest_final or item >= latest_final]


def _sessions(root: Path) -> list[str]:
    return list(_load(root / "sessions.json", []))


def _finals(root: Path) -> list[str]:
    return list(_load(root / "finals.json", []))


def _remember_session(root: Path, session_date: str) -> None:
    sessions = _sessions(root)
    if session_date not in sessions:
        sessions.append(session_date)
        _dump(root / "sessions.json", sorted(sessions))


def write_quote(root: Path, session_date: str, payload: dict, *, today_has_open: bool) -> dict:
    """Store one session's quote snapshot, including weekends and holidays.

    An empty payload does not replace a file that already has prices, and a
    second 休市 write does not replace the first. A failed fetch with no
    prior file is stored as 未挂 and still occupies that date.
    """
    path = root / "hot" / "quotes" / f"{session_date}.json"
    closed = (not today_has_open) or is_weekend(session_date)
    existing = _load(path, None) if path.exists() else None
    if not _has_price(payload):
        if existing is not None and (_has_price(existing) or existing.get("状态") == "休市"):
            return {"status": "已有", "path": str(path), "closed": closed}
        stored = dict(payload)
        if stored.get("状态") != "休市":
            stored["状态"] = "未挂"
        if existing is not None and existing.get("状态") == "未挂" and stored.get("状态") == "未挂":
            return {"status": "未挂", "path": str(path), "closed": closed}
        _dump(path, stored)
        _remember_session(root, session_date)
        status = "已写" if stored.get("状态") == "休市" else "未挂"
        return {"status": status, "path": str(path), "closed": closed}
    _dump(path, payload)
    _remember_session(root, session_date)
    return {"status": "已写", "path": str(path), "closed": closed}


def write_news(root: Path, publish_date: str, fact: dict) -> dict:
    """Store one fact. The same url, 地址, or link replaces the earlier line."""
    path = root / "hot" / "news" / f"{publish_date}.jsonl"
    rows = _read_jsonl(path)
    key = _fact_key(fact)
    status = "已写"
    if key:
        for index, row in enumerate(rows):
            if _fact_key(row) == key:
                rows[index] = fact
                status = "已替换"
                break
        else:
            rows.append(fact)
    else:
        rows.append(fact)
    _write_jsonl(path, rows)
    return {"status": status, "path": str(path)}


def write_bars(root: Path, code: str, rows: list[dict]) -> dict:
    """Keep the latest ten sessions. A missing open, high, or low does not erase one already stored."""
    path = root / "bars" / f"{code}.json"
    existing = {item["date"]: item for item in _load(path, []) if isinstance(item, dict) and item.get("date")}
    for row in rows:
        if not isinstance(row, dict) or not row.get("date"):
            continue
        prior = existing.get(row["date"], {"date": row["date"]})
        merged = {"date": row["date"]}
        for field in BAR_FIELDS:
            new_value = row.get(field)
            old_value = prior.get(field)
            if new_value is None:
                if old_value is not None:
                    merged[field] = old_value
            else:
                merged[field] = new_value
        existing[row["date"]] = merged
    ordered = [existing[day] for day in sorted(existing)]
    kept = ordered[-10:]
    _dump(path, kept)
    return {"status": "已写", "kept": len(kept), "path": str(path)}


def write_result(root: Path, trade_date: str, kind: str, payload: dict) -> dict:
    """Write one round's result. The 终分 file is not overwritten."""
    if kind not in RESULT_KINDS:
        return {"status": "未挂", "reason": "未知稿"}
    path = root / "results" / f"{trade_date}-{kind}.json"
    if kind == "终分" and path.exists():
        return {"status": "已冻住", "path": str(path)}
    _dump(path, payload)
    return {"status": "已写", "path": str(path)}


def _result_day(name: str) -> str:
    if len(name) < 10:
        return ""
    day = name[:10]
    try:
        date.fromisoformat(day)
    except ValueError:
        return ""
    return day


def finish_final(root: Path, trade_date: str, *, trading_day: bool) -> dict:
    """Archive hot files dated before `trade_date` after that day's 终分 file exists.

    A weekend, a day passed as not a trading day, or a missing 终分 file does
    not move files and does not record the date.
    """
    if not trading_day or is_weekend(trade_date):
        return {"status": "非交易日", "moved": []}
    final_path = root / "results" / f"{trade_date}-终分.json"
    if not final_path.exists():
        return {"status": "未写终分", "moved": []}
    finals = _finals(root)
    if trade_date not in finals:
        finals.append(trade_date)
        _dump(root / "finals.json", sorted(finals))
    moved = []
    for kind in ("quotes", "news"):
        hot_dir = root / "hot" / kind
        if not hot_dir.exists():
            continue
        archive_dir = root / "archive" / kind
        archive_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(hot_dir.iterdir()):
            if path.stem >= trade_date:
                continue
            target = archive_dir / path.name
            if kind == "news":
                combined = _merge_facts(_read_jsonl(target) + _read_jsonl(path))
                _write_jsonl(target, combined)
                path.unlink()
            else:
                shutil.move(str(path), str(target))
            moved.append(str(target))
    results = root / "results"
    if results.exists():
        archive_dir = root / "archive" / "results"
        archive_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(results.iterdir()):
            day = _result_day(path.name)
            if not day or day >= trade_date:
                continue
            target = archive_dir / path.name
            shutil.move(str(path), str(target))
            moved.append(str(target))
    return {"status": "已归档", "moved": moved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="热层和归档。不改权重，不下单。")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default="", help="资料湖目录，默认 runtime/lake")
    sub = parser.add_subparsers(dest="cmd", required=True)

    quote = sub.add_parser("quote", parents=[common])
    quote.add_argument("--date", required=True)
    quote.add_argument("--open", action="store_true", help="这一天有开盘价")
    quote.add_argument("--payload", default="{}", help="行情 JSON")

    news = sub.add_parser("news", parents=[common])
    news.add_argument("--date", required=True)
    news.add_argument("--fact", required=True, help="一句事实的 JSON")

    bars = sub.add_parser("bars", parents=[common])
    bars.add_argument("--code", required=True)
    bars.add_argument("--rows", required=True, help="[{date, open, high, low, close}] JSON")

    result = sub.add_parser("result", parents=[common])
    result.add_argument("--date", required=True)
    result.add_argument("--kind", required=True, choices=RESULT_KINDS)
    result.add_argument("--payload", default="{}", help="这一轮结果 JSON")

    final = sub.add_parser("final", parents=[common])
    final.add_argument("--date", required=True)
    final.add_argument("--trading-day", action="store_true")
    final.add_argument("--closed", action="store_true", help="周末或放假，不搬归档")

    show = sub.add_parser("hot", parents=[common])
    show.add_argument("--today", required=True)
    show.add_argument("--open", action="store_true")

    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else LAKE
    if args.cmd == "quote":
        output = write_quote(root, args.date, json.loads(args.payload), today_has_open=args.open)
    elif args.cmd == "news":
        output = write_news(root, args.date, json.loads(args.fact))
    elif args.cmd == "bars":
        output = write_bars(root, args.code, json.loads(args.rows))
    elif args.cmd == "result":
        output = write_result(root, args.date, args.kind, json.loads(args.payload))
    elif args.cmd == "final":
        trading = args.trading_day and not args.closed
        output = finish_final(root, args.date, trading_day=trading)
    else:
        output = {
            "hot": hot_quote_dates(
                _sessions(root),
                today=args.today,
                today_has_open=args.open,
                final_dates=_finals(root),
            )
        }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
