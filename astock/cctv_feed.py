#!/usr/bin/env python3
"""CCTV-2 program list. A dead page is 未挂. No score, no order."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

PROGRAMS = ("第一时间", "正点财经", "交易时间", "天下财经", "经济信息联播")
LIST_URL = "https://tv.cctv.com/lm/xwlb/index.shtml"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="央视财经栏目。打不开写未挂。不下单。")
    parser.add_argument("--html", default="", help="解析这个文件，不访问网络")
    args = parser.parse_args(argv)
    if args.html:
        html = open(args.html, encoding="utf-8").read()
        result = parse_cctv(html)
    else:
        try:
            req = urllib.request.Request(LIST_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", "replace")
            result = parse_cctv(html)
        except Exception as exc:  # noqa: BLE001 — a dead list is 未挂
            result = {"status": "未挂", "items": [], "error": type(exc).__name__}
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
