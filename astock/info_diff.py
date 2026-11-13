#!/usr/bin/env python3
"""Diff official list pages against the ledger. Print only what this window might open.

The ledger file stays where it is. A known address is not printed again. A title
with no clock is still listed, and is not marked for opening. Titles are not
dropped for a sensitive word. This does not score and does not place an order.
Seen addresses and the cursor are written under runtime/lake so the next run
can see them.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request

from astock.overseas_feed import collect
from astock.paths import LEDGER
from astock.state import beijing_now, read_cursor, read_seen, remember_urls, write_cursor

LINK_RE = re.compile(r"""<a[^>]+href=['"]([^'"]+)['"][^>]*>([\s\S]*?)</a>""", re.I)
URL_RE = re.compile(r"https?://[^\s|）<>\"']+")
CLOCK_RE = re.compile(r"(20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}|\d{2}-\d{2}\s+\d{2}:\d{2})")
DATE_RE = re.compile(r"20\d{2}[-/]\d{2}[-/]\d{2}")
SECTOR_WORDS = ("电子", "芯片", "通信", "银行", "食品饮料", "煤炭")
COMMENT_WORDS = ("访谈", "专访", "快评", "评论", "投资机构", "基金经理")
COLLECT_START = "2026-11-03 09:00"

PAGES = (
    ("新华网财经滚动", "https://www.news.cn/fortune/gundong/index.html", "https://www.news.cn"),
    ("新华网国际", "https://www.news.cn/world/index.html", "https://www.news.cn"),
    ("中证网", "https://www.cs.com.cn/", "https://www.cs.com.cn"),
    ("发改委新闻发布", "https://www.ndrc.gov.cn/xwdt/xwfb/", "https://www.ndrc.gov.cn"),
    ("发改委通知", "https://www.ndrc.gov.cn/xxgk/zcfb/tz/", "https://www.ndrc.gov.cn"),
)


def _clean_title(raw: str) -> str:
    title = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", title).strip()


def _abs_url(href: str, base: str) -> str:
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return base.rstrip("/") + href
    return base.rstrip("/") + "/" + href.lstrip("./")


def _id_in_text(url: str, text: str) -> bool:
    found = re.findall(r"[0-9a-f]{20,}|detail_\d+|t20\d{6}_\d+", url)
    return any(item and item in text for item in found)


def _clock_text(clock: str, url: str) -> str:
    found = re.search(r"(20\d{2}-\d{2}-\d{2})[ T](\d{2}:\d{2})", clock)
    if found:
        return f"{found.group(1)} {found.group(2)}"
    found = re.search(r"(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", clock)
    if not found:
        return ""
    year = re.search(r"/(20\d{2})/", url)
    prefix = year.group(1) if year else "2026"
    return f"{prefix}-{found.group(1)}-{found.group(2)} {found.group(3)}:{found.group(4)}"


def weight_for(status: str) -> str:
    """待打开 can be cited. Commentary stays out of W1–W5. Nothing here changes the score."""
    if status == "待打开":
        return "待引用"
    return status


def classify_link(
    title: str,
    url: str,
    nearby: str,
    ledger: str,
    cursor: str = "",
    start: str = COLLECT_START,
) -> str | None:
    """Return a status, or None when the address is already recorded."""
    if not title or len(title) < 4:
        return None
    if url in ledger or _id_in_text(url, ledger):
        return None
    if any(word in title for word in COMMENT_WORDS):
        return "不进W1–W5"
    if title and title in ledger:
        return "同一事实已记"
    clock = CLOCK_RE.search(nearby)
    if clock:
        stamped = _clock_text(clock.group(1), url)
        if stamped and stamped < start:
            return None
        if stamped and cursor and stamped <= cursor:
            return "缺口"
        return "待打开"
    if DATE_RE.search(nearby) or DATE_RE.search(title):
        return "无发布时间"
    return "无发布时间"


BLOCK_END = (
    "</a>",
    "</li>",
    "</p>",
    "</dd>",
    "</tr>",
    "</div>",
    "</h1>",
    "</h2>",
    "</h3>",
    "</h4>",
    "</h5>",
)
NEXT_BLOCK = ("<a ", "<li", "<p ", "<p>", "<div", "<dd", "<tr")


def nearby_text(html: str, match, title: str) -> str:
    """Text that may carry THIS link's clock.

    Looks before and after the anchor. The before-window is cut at the last block
    boundary so a previous item's timestamp cannot be borrowed. The after-window
    stops at the next block so clocks written after the title are still found.
    """
    start, end = match.start(), match.end()
    before = html[max(0, start - 160) : start]
    cuts = [before.rfind(tag) for tag in BLOCK_END]
    cut = max(cuts)
    if cut >= 0:
        before = before[cut:]
    after = html[end : end + 160]
    stops = [after.find(tag) for tag in NEXT_BLOCK]
    stops = [item for item in stops if item >= 0]
    if stops:
        after = after[: min(stops)]
    return f"{before} {title} {after}"


def links_from_html(html: str, base: str, ledger: str, source: str, cursor: str = "") -> list[dict]:
    rows = []
    seen: set[str] = set()
    for match in LINK_RE.finditer(html):
        url = _abs_url(match.group(1), base)
        title = _clean_title(match.group(2))
        if url in seen or "weibo.com" in url or url.startswith("javascript"):
            continue
        if not any(token in url for token in ("/2026", "detail_", "t2026")):
            continue
        nearby = nearby_text(html, match, title)
        status = classify_link(title, url, nearby, ledger, cursor=cursor)
        if status is None:
            continue
        seen.add(url)
        clock = CLOCK_RE.search(nearby)
        rows.append(
            {
                "source": source,
                "title": title[:48],
                "url": url,
                "status": status,
                "weight": weight_for(status),
                "clock": clock.group(1) if clock else "",
                "sector": any(word in title for word in SECTOR_WORDS),
            }
        )
    return rows


def pack(rows: list[dict], open_limit: int | None = None) -> dict:
    """Keep every clocked new page. A limit is only for a caller that asks for one."""
    def newer(row: dict) -> str:
        return row.get("clock") or ""

    opening = sorted((row for row in rows if row["status"] == "待打开"), key=newer, reverse=True)
    gap = sorted((row for row in rows if row["status"] == "缺口"), key=newer, reverse=True)
    same = [row for row in rows if row["status"] == "同一事实已记"]
    comments = [
        {"source": row.get("source"), "title": row.get("title"), "url": row.get("url")}
        for row in rows
        if row["status"] == "不进W1–W5"
    ]
    undated = [row for row in rows if row["status"] == "无发布时间"]
    sector_undated = [row for row in undated if row.get("sector")]
    if open_limit is not None:
        opening_out, gap_out = opening[:open_limit], gap[:open_limit]
    else:
        opening_out, gap_out = opening, gap
    return {
        "open": opening_out,
        "open_left": max(0, len(opening) - len(opening_out)),
        "gap": gap_out,
        "gap_left": max(0, len(gap) - len(gap_out)),
        "same_fact": same,
        "comments": comments,
        "comment_skipped": len(comments),
        "undated": undated,
        "undated_count": len(undated),
        "undated_sector": sector_undated,
    }


MONEY_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:亿(?:元)?|万(?:元)?|元|％|%|个百分点|点)")
MOVE_RE = re.compile(
    r"(?:上涨|下跌|涨幅|降幅|高开|低开|收于|收报|升至|降至|报|涨|跌)\D{0,10}\d[\d,]*(?:\.\d+)?"
)


def article_fact(html: str) -> str:
    """One sentence from the page. The raw page stays out of the conversation.

    Prefer a body number carrying money/percent/index units so a page-header
    date (2026-11-12) is not mistaken for the close or profit.
    """
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    anchor = MONEY_RE.search(text) or MOVE_RE.search(text)
    if anchor:
        start = max(0, anchor.start() - 30)
        end = min(len(text), anchor.end() + 80)
        snippet = text[start:end].strip()
    else:
        snippet = text[:120]
    return snippet[:160]


def attach_facts(rows: list[dict]) -> None:
    for row in rows:
        try:
            html = _fetch(row["url"])
        except Exception as exc:  # noqa: BLE001 — a dead page stays a row
            row["fact"] = ""
            row["fetch"] = type(exc).__name__
            continue
        row["fact"] = article_fact(html)


def _fetch(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(400000).decode("utf-8", "replace")


def _cursor(ledger: str) -> str:
    found = re.search(r"截止:\s*(20\d{2}-\d{2}-\d{2} \d{2}:\d{2})", ledger)
    return found.group(1) if found else ""


def main() -> int:
    ledger = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""
    known = ledger + "\n" + read_seen()
    # Prefer the portable cursor; fall back to the machine-local ledger.
    cursor = read_cursor() or _cursor(known)
    rows: list[dict] = []
    mounts = []
    for source, url, base in PAGES:
        try:
            html = _fetch(url)
        except Exception as exc:  # noqa: BLE001 — a dead list is a mount note, not a story
            mounts.append({"source": source, "url": url, "error": type(exc).__name__})
            continue
        rows.extend(links_from_html(html, base, known, source, cursor=cursor))
    overseas = []
    try:
        for item in collect(8):
            url = item.get("url") or ""
            if item.get("kind") == "unmounted":
                mounts.append(item)
                continue
            title = item.get("title") or ""
            if any(word in title for word in COMMENT_WORDS):
                # Keep the title; commentary is visible but never enters weights.
                item["status"] = "不进W1–W5"
                overseas.append(item)
                continue
            if url and url not in known and not _id_in_text(url, known):
                overseas.append(item)
    except Exception as exc:  # noqa: BLE001
        mounts.append({"source": "overseas_feed", "error": type(exc).__name__})
    payload = pack(rows)
    attach_facts(payload["open"] + payload["gap"])
    listed = [row.get("url") or "" for row in payload["open"]]
    listed += [row.get("url") or "" for row in payload["comments"]]
    listed += [item.get("url") or "" for item in overseas]
    remember_urls(listed)
    if not mounts:
        write_cursor(beijing_now())
    payload["overseas_new"] = overseas
    payload["mounts"] = mounts
    payload["cursor"] = cursor
    payload["empty"] = not payload["open"] and not payload["gap"] and not overseas
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
