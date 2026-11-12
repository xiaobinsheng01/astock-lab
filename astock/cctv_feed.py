#!/usr/bin/env python3
"""CCTV-2 program list. A dead page is 未挂. No score, no order."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

PROGRAMS = ("第一时间", "正点财经", "交易时间", "天下财经", "经济信息联播")
# Each finance program's own column page. The news-broadcast page is not opened.
COLUMNS = (
    ("第一时间", "https://tv.cctv.com/lm/dysj/"),
    ("正点财经", "https://tv.cctv.com/lm/zdcj/"),
    ("交易时间", "https://tv.cctv.com/lm/jysj/"),
    ("天下财经", "https://tv.cctv.com/lm/hqcjlx/"),
    ("经济信息联播", "https://tv.cctv.com/lm/jjxxll/"),
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


def fetch_columns() -> list[dict]:
    """Open the five finance column pages. A dead column is 未挂, not skipped."""
    results = []
    for program, url in COLUMNS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", "replace")
            results.append(parse_program(html, program))
        except Exception as exc:  # noqa: BLE001 — a dead column is 未挂
            results.append(
                {
                    "program": program,
                    "status": "未挂",
                    "items": [],
                    "error": type(exc).__name__,
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
