#!/usr/bin/env python3
"""China Wealth news list. Other media on the source line are reprints."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

LIST_URL = "https://www.cfbond.com/zgcfw/ejy/yw/list.shtml"
_ITEM = re.compile(
    r'data-time="([^"]*)"[^>]*data-source="([^"]*)"[^>]*>(.*?)</li>',
    re.IGNORECASE | re.DOTALL,
)


def parse_cfbond(html: str) -> dict:
    if not html or not html.strip():
        return {"status": "未挂", "items": []}
    items = []
    for match in _ITEM.finditer(html):
        source = re.sub(r"\s+", "", match.group(2))
        title = re.sub(r"<[^>]+>", "", match.group(3))
        title = re.sub(r"\s+", " ", title).strip()
        status = "原文" if source == "中国财富网" else "转载"
        items.append(
            {
                "time": match.group(1).strip(),
                "source": source,
                "title": title,
                "status": status,
            }
        )
    if not items:
        return {"status": "未挂", "items": []}
    return {"status": "已列", "items": items}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="中国财富网要闻。打不开写未挂。不下单。")
    parser.add_argument("--html", default="", help="解析这个文件，不访问网络")
    args = parser.parse_args(argv)
    if args.html:
        result = parse_cfbond(open(args.html, encoding="utf-8").read())
    else:
        try:
            req = urllib.request.Request(LIST_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", "replace")
            result = parse_cfbond(html)
        except Exception as exc:  # noqa: BLE001 — a dead list is 未挂
            result = {"status": "未挂", "items": [], "error": type(exc).__name__}
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
