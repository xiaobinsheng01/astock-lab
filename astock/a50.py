#!/usr/bin/env python3
"""FTSE China A50 night session. Two prices or a gap. No score, no order."""

from __future__ import annotations

import argparse
import json
import sys


def assess(latest, previous, clock: str) -> dict:
    """`latest` and `previous` are the night price and the prior settle."""
    if latest in (None, "") or previous in (None, "") or not clock:
        return {"status": "缺口", "text": "A50 缺最新价或前结"}
    latest_f = float(latest)
    previous_f = float(previous)
    if previous_f == 0:
        return {"status": "缺口", "text": "A50 缺最新价或前结"}
    change = (latest_f - previous_f) / previous_f * 100
    if abs(change) < 0.20:
        word = "平开"
    elif change > 0:
        word = "高开"
    else:
        word = "低开"
    return {
        "status": "已核",
        "word": word,
        "pct": round(change, 2),
        "clock": clock,
        "text": f"A50 {word} {change:.2f}% 报价{clock}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A50 两个价。缺一个就写缺口。不下单。")
    parser.add_argument("--latest", default="")
    parser.add_argument("--prev", default="")
    parser.add_argument("--clock", default="", help="报价的北京时间")
    args = parser.parse_args(argv)
    latest = args.latest or None
    previous = args.prev or None
    try:
        result = assess(latest, previous, args.clock)
    except ValueError:
        result = {"status": "未挂", "text": "A50 报价打不开"}
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
