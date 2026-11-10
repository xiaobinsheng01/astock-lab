#!/usr/bin/env python3
"""Cailian Press telegraph list. Public sign, no login.

Rows are raw material. They do not enter the weight pass and do not score.
A line that cites an official body is a reprint. Comment products stay out.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from astock.info_diff import classify_link

BEIJING = timezone(timedelta(hours=8))
LIST_URL = "https://www.cls.cn/v1/roll/get_roll_list"
DETAIL = "https://www.cls.cn/detail/{}"
COMMENT_MARKS = ("盘中宝", "风口研报", "九点特供", "脱水研报", "电报解读", "VIP")
REPRINT_MARKS = (
    "据新华社",
    "据财政部",
    "据国家发展改革委",
    "据发改委",
    "据中国人民银行",
    "据央行",
    "据国务院",
    "据证监会",
    "据国家统计局",
    "据海关总署",
    "据证券时报",
    "据上海证券报",
    "据中国证券报",
    "据证券日报",
)


def sign(params: dict) -> str:
    """Public list signature: md5 of the sha1 of the sorted query."""
    raw = "&".join(f"{key}={params[key]}" for key in sorted(params))
    digest = hashlib.sha1(raw.encode()).hexdigest()
    return hashlib.md5(digest.encode()).hexdigest()


def beijing_clock(ctime) -> str:
    stamp = int(ctime)
    return datetime.fromtimestamp(stamp, BEIJING).strftime("%Y-%m-%d %H:%M")


def _title(item: dict) -> str:
    title = (item.get("title") or "").strip()
    if len(title) >= 4:
        return title
    content = (item.get("content") or "").strip()
    return content[:48]


def telegraph_rows(items: list[dict], ledger: str, cursor: str = "") -> list[dict]:
    rows = []
    seen: set[str] = set()
    for item in items:
        if item.get("is_ad"):
            continue
        item_id = item.get("id")
        if not item_id or item.get("ctime") in (None, ""):
            continue
        url = DETAIL.format(item_id)
        if url in seen:
            continue
        title = _title(item)
        content = (item.get("content") or "").strip()
        text = title + content
        clock = beijing_clock(item["ctime"])
        if any(mark in text for mark in COMMENT_MARKS):
            status = "不进W1–W5"
        else:
            status = classify_link(title, url, clock, ledger, cursor=cursor)
            if status in {"待打开", "缺口"} and any(mark in content for mark in REPRINT_MARKS):
                status = "转载"
            elif status == "待打开":
                status = "原料"
        if status is None:
            continue
        seen.add(url)
        rows.append(
            {
                "source": "财联社电报",
                "title": title[:48],
                "url": url,
                "status": status,
                "clock": clock,
                "fact": content[:160],
                "weight": False,
            }
        )
    return rows


def _fetch_page(last_time: str) -> list[dict]:
    params = {"app": "CailianpressWeb", "os": "web", "sv": "8.7.9", "rn": "20"}
    if last_time:
        params["last_time"] = last_time
    params["sign"] = sign({key: value for key, value in params.items() if key != "sign"})
    url = LIST_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cls.cn/telegraph"})
    with urllib.request.urlopen(req, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    if payload.get("errno") not in (0, "0", None):
        raise RuntimeError(str(payload.get("msg") or payload.get("errno")))
    return ((payload.get("data") or {}).get("roll_data")) or []


def fetch_telegraph(cursor: str = "", pages: int = 8) -> list[dict]:
    """Newest pages until the cursor, then stop. No cookie and no token."""
    last_time = ""
    items: list[dict] = []
    for _page in range(pages):
        batch = _fetch_page(last_time)
        if not batch:
            break
        items.extend(batch)
        oldest = min(int(item["ctime"]) for item in batch if item.get("ctime") not in (None, ""))
        if cursor and beijing_clock(oldest) <= cursor:
            break
        if len(batch) < 20:
            break
        last_time = str(oldest)
    return items
