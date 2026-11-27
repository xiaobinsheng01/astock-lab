#!/usr/bin/env python3
"""Hot and archive storage for one desk. No score, no order.

Quotes in the hot layer are the previous session and the current calendar day.
Weekends and holidays still get a quote file, so the hot layer is not missing
that day. News from the previous trading day through the current moment stays
hot. The next trading day's finished 终分 moves older hot files out.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from astock.paths import LAKE


def _load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_weekend(day: str) -> bool:
    return date.fromisoformat(day).weekday() >= 5


def hot_quote_dates(
    sessions: list[str],
    *,
    today: str,
    today_has_open: bool,
    final_dates: list[str],
) -> list[str]:
    """Sessions still in the hot layer.

    A finished 终分 on `trade_date` archives sessions strictly before that date.
    A weekend or holiday stays once its quote has been written.
    """
    ordered = sorted(set(sessions))
    if today_has_open and today not in ordered:
        ordered.append(today)
    if not ordered:
        return []
    if today_has_open:
        current = today
    else:
        current = ordered[-1]
    prior = [item for item in ordered if item < current]
    chosen = [prior[-1], current] if prior else [current]
    latest_final = max(final_dates) if final_dates else ""
    hot = []
    for item in chosen:
        if latest_final and item < latest_final:
            continue
        if item not in hot:
            hot.append(item)
    return hot


def _sessions(root: Path) -> list[str]:
    return list(_load(root / "sessions.json", []))


def _finals(root: Path) -> list[str]:
    return list(_load(root / "finals.json", []))


def write_quote(root: Path, session_date: str, payload: dict, *, today_has_open: bool) -> dict:
    """Store one session's quote snapshot, including weekends and holidays."""
    path = root / "hot" / "quotes" / f"{session_date}.json"
    _dump(path, payload)
    sessions = _sessions(root)
    if session_date not in sessions:
        sessions.append(session_date)
        _dump(root / "sessions.json", sorted(sessions))
    closed = (not today_has_open) or is_weekend(session_date)
    return {"status": "已写", "path": str(path), "closed": closed}


def write_news(root: Path, publish_date: str, fact: dict) -> dict:
    """Append one fact. News is kept through weekends."""
    path = root / "hot" / "news" / f"{publish_date}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(fact, ensure_ascii=False) + "\n")
    return {"status": "已写", "path": str(path)}


def write_bars(root: Path, code: str, rows: list[dict]) -> dict:
    """Merge one session's bars into the stored series. Never truncates history.

    A ten-bar window cannot compute a 20-day or 250-day line, so keeping only the
    last ten made every long-window test impossible. New rows are merged by date,
    an existing date takes the newer row, and the series grows without bound.
    """
    path = root / "bars" / f"{code}.json"
    existing = _load(path, [])
    by_date: dict[str, dict] = {}
    for item in existing:
        day = str(item.get("date") or "")
        if day:
            by_date[day] = item
    for item in rows:
        day = str(item.get("date") or "")
        if day:
            by_date[day] = item
    kept = [by_date[day] for day in sorted(by_date)]
    _dump(path, kept)
    return {"status": "已写", "kept": len(kept), "added": len(rows), "path": str(path)}


def read_bars(root: Path, code: str) -> list[dict]:
    """Stored bars for one code, oldest first. A missing file is an empty list."""
    return list(_load(root / "bars" / f"{code}.json", []))


def archive_snapshots(root: Path, trade_date: str) -> list[str]:
    """Copy dated judgment snapshots into the archive before they get overwritten.

    `终分.json` and `初分.json` are single files: today's write destroys
    yesterday's judgment, so nothing could ever be scored against what was
    actually predicted. A snapshot named `<stem>.<clock>.json` is copied to
    `archive/snapshots/<trade_date>/<name>`. The hot copy stays in place because
    the desk keeps reading it. A record already archived for this date is not
    copied twice.
    """
    hot_dir = root / "hot" / "snapshots"
    if not hot_dir.exists():
        return []
    target_dir = root / "archive" / "snapshots" / trade_date
    copied: list[str] = []
    for path in sorted(hot_dir.glob("*.json")):
        if path.stem == "手写持仓":
            # The book is state, not a judgment for this session.
            continue
        if target_dir.joinpath(path.name).exists():
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(target_dir / path.name))
        copied.append(str(target_dir / path.name))
    return copied


def finish_final(root: Path, trade_date: str, *, trading_day: bool) -> dict:
    """Archive hot files dated before `trade_date` after that day's 终分.

    A weekend or a day passed as not a trading day does not move files. Judgment
    snapshots are copied out of the hot layer first, because the next session
    overwrites them in place.
    """
    if not trading_day or is_weekend(trade_date):
        return {"status": "非交易日", "moved": []}
    finals = _finals(root)
    if trade_date not in finals:
        finals.append(trade_date)
        _dump(root / "finals.json", sorted(finals))
    moved = archive_snapshots(root, trade_date)
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
            if kind == "news" and target.exists():
                target.write_text(target.read_text(encoding="utf-8") + path.read_text(encoding="utf-8"), encoding="utf-8")
                path.unlink()
            else:
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
    bars.add_argument("--rows", required=True, help="[{date, close}] JSON")

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
        result = write_quote(root, args.date, json.loads(args.payload), today_has_open=args.open)
    elif args.cmd == "news":
        result = write_news(root, args.date, json.loads(args.fact))
    elif args.cmd == "bars":
        result = write_bars(root, args.code, json.loads(args.rows))
    elif args.cmd == "final":
        trading = args.trading_day and not args.closed
        result = finish_final(root, args.date, trading_day=trading)
    else:
        result = {
            "hot": hot_quote_dates(
                _sessions(root),
                today=args.today,
                today_has_open=args.open,
                final_dates=_finals(root),
            )
        }
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
