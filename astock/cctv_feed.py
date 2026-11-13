#!/usr/bin/env python3
"""CCTV-2 program list. A dead page is 未挂. No score, no order."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

PROGRAMS = ("第一时间", "正点财经", "交易时间", "天下财经", "经济信息联播")
# Column video API. The static column pages do not carry the current air time,
# and the news-broadcast page is not opened. 交易时间 has no public column id.
COLUMN_API = (
    ("第一时间", "TOPC1451530259915198"),
    ("正点财经", "TOPC1453100395512779"),
    ("天下财经", "TOPC1451531385787654"),
    ("经济信息联播", "TOPC1451533782742171"),
)


def parse_cctv(html: str) -> dict:
    if not html or not html.strip():
        return {"status": "未挂", "items": []}
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    items = []
    seen = set()
    for name in PROGRAMS:
        for match in re.finditer(re.escape(name), text):
            window = text[max(0, match.start() - 24): match.end() + 8]
            clock = re.search(r"20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}|\d{2}:\d{2}", window)
            stamp = clock.group(0) if clock else ""
            key = (name, stamp)
            if key in seen:
                continue
            seen.add(key)
            items.append({"program": name, "clock": stamp})
    if not items:
        return {"status": "栏目未挂", "items": []}
    return {"status": "已列", "items": items}


def parse_program(html: str, program: str) -> dict:
    """Items for one program on its own column page."""
    if not html or not html.strip():
        return {"program": program, "status": "栏目未挂", "items": []}
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    items = []
    seen = set()
    for match in re.finditer(re.escape(program), text):
        window = text[max(0, match.start() - 24): match.end() + 8]
        clock = re.search(r"20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}|\d{2}:\d{2}", window)
        stamp = clock.group(0) if clock else ""
        if stamp in seen:
            continue
        seen.add(stamp)
        items.append({"program": program, "clock": stamp})
    status = "已列" if items else "栏目未挂"
    return {"program": program, "status": status, "items": items}


def clock_from_focus(value) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 13:
        return ""
    moment = datetime.fromtimestamp(int(digits[:13]) / 1000, timezone(timedelta(hours=8)))
    return moment.strftime("%Y-%m-%d %H:%M")


def programs_from_payload(program: str, payload: dict) -> dict:
    items = ((payload or {}).get("data") or {}).get("list") or []
    programs = []
    for item in items[:5]:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        programs.append(
            {
                "program": program,
                "title": title,
                "clock": clock_from_focus(item.get("focus_date")),
                "url": item.get("url") or "",
            }
        )
    if not programs:
        return {"program": program, "status": "栏目未挂", "items": []}
    return {"program": program, "status": "已列", "items": programs}


def fetch_columns() -> list[dict]:
    """Open the finance column feeds. A dead column is 未挂, not skipped."""
    results = []
    for program, column_id in COLUMN_API:
        url = (
            "https://api.cntv.cn/NewVideo/getVideoListByColumn"
            f"?id={column_id}&n=5&sort=desc&mode=0&serviceId=tvcctv"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
            results.append(programs_from_payload(program, payload))
        except Exception as exc:  # noqa: BLE001 — a dead column is 未挂
            results.append(
                {
                    "program": program,
                    "status": "未挂",
                    "items": [],
                    "error": type(exc).__name__,
                }
            )
    results.append(
        {
            "program": "交易时间",
            "status": "栏目未挂",
            "items": [],
            "text": "栏目页没有节目编号",
        }
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="央视财经栏目。打不开写未挂。不下单。")
    parser.add_argument("--html", default="", help="解析这个文件，不访问网络")
    args = parser.parse_args(argv)
    if args.html:
        result = parse_cctv(open(args.html, encoding="utf-8").read())
    else:
        columns = fetch_columns()
        items = [entry for col in columns for entry in col["items"]]
        result = {
            "status": "已列" if items else "栏目未挂",
            "items": items,
            "columns": columns,
        }
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
