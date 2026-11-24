#!/usr/bin/env python3
"""List overseas-market items from Xinhua world and finance pages.

Stdlib only. Does not score W1–W8, does not write the ledger, and does not
emit an order. The agent still opens each page and copies one sentence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

WORLD_URL = "https://www.news.cn/world/index.html"
FORTUNE_URL = "https://www.news.cn/fortune/gundong/index.html"

PARTY = ("民主党", "共和党", "众议院", "参议院", "国会")
OUTCOME = ("席位", "控制权", "重掌", "夺回", "赢得", "胜选", "掌控")
BLOCK = ("若", "如果", "民调", "投票", "计票", "支出", "议题")
MARKET = (
    "道指",
    "标普",
    "纳指",
    "美股",
    "欧股",
    "富时",
    "DAX",
    "CAC",
    "日经",
    "恒生",
    "美元指数",
    "美债",
    "油价",
    "金价",
    "沪铜",
    "铜价",
    "美联储",
)
MARKET_PLACE = ("美国", "纽约", "欧洲", "伦敦", "东京", "香港", "日本")
EARNINGS = ("营收", "净利润", "财报", "并购")
EARNINGS_WHERE = ("美国", "美股", "纽约", "欧洲", "日本", "香港")
# Named companies and people. A title that only says the name still belongs
# on this list; "黄仁勋复职" does not contain 美股 or 公司.
NAMES = ("黄仁勋", "英伟达", "台积电", "阿斯麦", "美光", "博通")
# Overseas corporate / policy events that must not vanish from the desk.
EVENT = ("人事", "管制", "制裁", "停产", "指引", "复职", "出任", "任命")

LINK_RE = re.compile(
    r"""<a[^>]+href=['"]([^'"]+)['"][^>]*>([\s\S]*?)</a>""",
    re.IGNORECASE,
)
# A dated article path. Navigation and section hubs stay off the list.
ARTICLE_URL = re.compile(r"/20\d{2}|detail_|t20\d{6}")


def classify(title: str) -> str | None:
    """Return election_result, market_print, earnings, event, or None."""
    blocked = any(word in title for word in BLOCK)
    election = (
        not blocked
        and any(word in title for word in PARTY)
        and any(word in title for word in OUTCOME)
    )
    if election:
        return "election_result"
    if any(word in title for word in MARKET) or (
        "股市" in title and any(word in title for word in MARKET_PLACE)
    ):
        return "market_print"
    if "半导体" in title and any(word in title for word in ("指数", "费城")):
        return "market_print"
    if any(word in title for word in NAMES):
        if blocked:
            return None
        return "event"
    if any(word in title for word in EARNINGS) and any(
        word in title for word in EARNINGS_WHERE
    ):
        return "earnings"
    if any(word in title for word in EVENT) and (
        any(word in title for word in EARNINGS_WHERE)
        or any(word in title for word in ("公司", "企业", "集团"))
    ):
        return "event"
    return None


def items_from_html(html: str, source: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for match in LINK_RE.finditer(html):
        url = match.group(1).strip()
        title = re.sub(r"<[^>]+>", "", match.group(2))
        title = re.sub(r"\s+", " ", title).strip()
        if not title or not url or url.startswith("#") or url in seen:
            continue
        if url.startswith("/"):
            url = "https://www.news.cn" + url
        if len(title) < 4 or not ARTICLE_URL.search(url):
            continue
        seen.add(url)
        out.append(
            {
                "source": source,
                "kind": classify(title) or "article",
                "title": title,
                "url": url,
            }
        )
    return out


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _round_robin(world: list[dict], fortune: list[dict], limit: int | None = None) -> list[dict]:
    """Alternate the two lists. The same address is kept once.

    `limit` None keeps every article. Titles are not a filter.
    """
    out: list[dict] = []
    seen: set[str] = set()
    pointers = [0, 0]
    lists = [world, fortune]
    while (limit is None or len(out) < limit) and any(
        pointers[i] < len(lists[i]) for i in (0, 1)
    ):
        progressed = False
        for index, rows in enumerate(lists):
            if limit is not None and len(out) >= limit:
                break
            while pointers[index] < len(rows):
                row = rows[pointers[index]]
                pointers[index] += 1
                url = row.get("url") or ""
                if url and url in seen:
                    continue
                if url:
                    seen.add(url)
                out.append(row)
                progressed = True
                break
        if not progressed:
            break
    return out


def collect(limit: int | None = None) -> list[dict]:
    by_source: dict[str, list[dict]] = {}
    notes = []
    for source, url in (("world", WORLD_URL), ("fortune", FORTUNE_URL)):
        try:
            html = fetch(url)
        except Exception as exc:  # noqa: BLE001 — record the list as unavailable
            notes.append({"source": source, "kind": "unmounted", "title": "", "url": url, "error": type(exc).__name__})
            by_source[source] = []
            continue
        by_source[source] = items_from_html(html, source)
    kept = _round_robin(by_source.get("world", []), by_source.get("fortune", []), limit)
    return kept + notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List overseas market items")
    parser.add_argument("--html", help="Parse this file instead of fetching")
    parser.add_argument("--source", default="world", help="Source name for --html")
    parser.add_argument("--limit", type=int, default=0, help="0 表示不截断")
    args = parser.parse_args(argv)
    limit = None if args.limit <= 0 else args.limit
    if args.html:
        html = open(args.html, encoding="utf-8", errors="replace").read()
        rows = items_from_html(html, args.source)
        if limit is not None:
            rows = rows[:limit]
    else:
        rows = collect(limit)
    json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
