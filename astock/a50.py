#!/usr/bin/env python3
"""FTSE China A50 night session. Two prices or a gap. No score, no order."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

SINA_URL = "https://hq.sinajs.cn/list=hf_CHA50CFD"


def parse_a50(body: str) -> dict:
    """Sina hf line. Field 0 is the last price and field 7 is the prior settle.

    Field 2 is the bid. Using it as the settle makes the night change look flat.
    """
    fields = body.split(",")
    if len(fields) < 13 or not fields[0]:
        return {"error": "NoPrice"}
    clock = f"{fields[12]} {fields[6]}"
    previous = fields[7]
    if previous in ("", "0"):
        return {"latest": fields[0], "previous": "", "clock": clock}
    return {"latest": fields[0], "previous": previous, "clock": clock}


def fetch_live() -> dict:
    """Fetch the night price and prior settle from the public Sina host.

    Returns latest/previous/clock. A dead host is reported, never silently 0.
    """
    req = urllib.request.Request(
        SINA_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("gbk", "replace")
    except Exception as exc:  # noqa: BLE001 — caller writes 未挂 with the cause
        return {"error": type(exc).__name__}
    payload = raw.split('"', 1)
    if len(payload) < 2:
        return {"error": "EmptyPayload"}
    return parse_a50(payload[1].split('"', 1)[0])


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
    parser.add_argument("--live", action="store_true", help="自己取价（默认无参数时也自取）")
    args = parser.parse_args(argv)
    if args.live or (not args.latest and not args.clock):
        live = fetch_live()
        if "error" in live:
            result = {"status": "未挂", "text": "A50 报价未挂", "error": live["error"]}
        else:
            result = assess(live["latest"], live["previous"], live["clock"])
    else:
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
