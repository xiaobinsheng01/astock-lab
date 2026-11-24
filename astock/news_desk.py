#!/usr/bin/env python3
"""Market-news desk. Five event classes, one page per day. No score, no order.

The script lists and classifies. It does not write ``runtime/info-ledger.md``
and does not enter W1–W8. A live run rewrites ``hot/news/YYYY-MM-DD.md`` only.
The jsonl fact file for that day stays untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from astock.net import open_url
from astock.paths import LAKE

BEIJING = timezone(timedelta(hours=8))
CLOCK_RE = re.compile(r"^20\d{2}-\d{2}-\d{2} \d{2}:\d{2}$")
LINK_RE = re.compile(r"""<a[^>]+href=['"]([^'"]+)['"][^>]*>([\s\S]*?)</a>""", re.I)
YI_RE = re.compile(r"(\d+(?:\.\d+)?)\s*亿元")
EXPORT_HALT_RE = re.compile(r"(?:暂停|停止|禁止).{0,8}出口")

BREAKFAST_URL = (
    "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
    "?client=web&biz=web_news_col&column=1207&order=1&needInteractData=0"
    "&page_index=1&page_size=200&req_trace=1710314682980"
    "&fields=code,showTime,title,mediaName,summary,image,url,uniqueUrl,Np_dst"
)
FLASH_URL = (
    "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
    "?client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize=200&req_trace=1710315450384"
)
CLS_URL = "https://www.cls.cn/v1/roll/get_roll_list"
CCTV_DAY = "https://tv.cctv.com/lm/xwlb/day/{compact}.shtml"
CCTV_FETCH_CAP = 30

SOURCE_BREAKFAST = "东方财富财经早餐"
SOURCE_FLASH = "东方财富全球快讯"
SOURCE_CLS = "财联社电报"
SOURCE_CCTV = "新闻联播"
CAPS = {
    SOURCE_BREAKFAST: None,
    SOURCE_CCTV: None,
    SOURCE_CLS: 20,
    SOURCE_FLASH: 20,
}
WEIGHT = "不改权重"

VETO = (
    "专利",
    "世界杯",
    "欧冠",
    "英超",
    "NBA",
    "奥运会",
    "金牌",
    "足球",
    "篮球",
    "男篮",
    "女足",
    "快评",
    "专访",
    "访谈",
    "投资策略",
    "怎么看",
    "投资建议",
)
SECTOR_RULES = (
    (("芯片", "半导体", "光刻", "英伟达", "黄仁勋", "先进制程", "光模块"), "半导体"),
    (("钴", "锂", "稀土", "铜", "有色", "铝", "黄金"), "有色"),
    (("原油", "石油", "天然气", "霍尔木兹", "炼厂", "油轮"), "油气"),
    (("集采", "创新药", "单抗", "医药", "药品"), "医药"),
    (("服务器", "算力", "人工智能"), "算力"),
    (("融资保证金", "保证金", "两融", "融资融券", "印花税", "降费", "逆周期"), "成长"),
    (("关税", "出口管制", "出口限制", "实体清单"), "出口链"),
    (("银行股", "银行业", "银行板块", "准备金"), "银行"),
    (("煤炭",), "煤炭"),
    (("光伏",), "电新"),
    (("做市", "券商"), "券商"),
)
BROADCAST_PREFIXES = (
    "央视网消息（新闻联播）：",
    "央视网消息(新闻联播)：",
    "（新闻联播）：",
    "(新闻联播)：",
)


def normalize_day(day: str) -> str:
    digits = re.sub(r"\D", "", day.strip())
    if len(digits) != 8:
        raise ValueError("日期写成 YYYY-MM-DD")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def _clean(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    text = _clean(text)
    parts = re.split(r"(?<=[。！？；;])", text)
    return [part.strip() for part in parts if len(part.strip()) >= 4]


def _one_fact(text: str) -> str:
    text = _clean(text).replace("|", "｜")
    if len(text) <= 120:
        return text
    clipped = text[:120]
    for mark in ("。", "；", "，", " "):
        pos = clipped.rfind(mark)
        if pos >= 40:
            end = pos if mark == " " else pos + 1
            return clipped[:end].strip()
    return clipped


def _category(text: str) -> str | None:
    chip_export = "芯片" in text and any(word in text for word in ("出口", "出售", "管制", "禁运", "许可"))
    chip_seat = any(word in text for word in ("黄仁勋", "英伟达")) and any(
        word in text for word in ("复职", "恢复")
    )
    if chip_seat or chip_export or any(word in text for word in ("关税", "出口管制", "出口限制", "实体清单", "先进制程", "禁运")):
        return "关税与出口管制"
    if any(word in text for word in ("霍尔木兹", "油轮", "炼厂")) or (
        "遇袭" in text and any(word in text for word in ("海峡", "油", "船"))
    ):
        return "地缘供给"
    if EXPORT_HALT_RE.search(text) or any(
        word in text for word in ("停产", "缺料", "停工", "减产", "短缺", "涨价", "禁令")
    ):
        return "产业供给"
    if any(word in text for word in ("保证金", "融资融券", "两融", "印花税", "降费", "做市", "集采", "逆周期", "准备金")):
        return "监管"
    if any(word in text for word in ("并购", "收购", "回购")):
        return "并购与回购"
    return None


def _sectors(text: str, category: str) -> list[str]:
    found: list[str] = []
    for words, name in SECTOR_RULES:
        if any(word in text for word in words) and name not in found:
            found.append(name)
    if category == "关税与出口管制":
        if "成长" not in found:
            found.insert(0, "成长")
        if "出口链" not in found:
            found.append("出口链")
    return found


def _horizon(text: str) -> str:
    if any(word in text for word in ("拟", "尚未", "未定", "未确认", "知情人士", "或将")):
        return "隔夜"
    if any(word in text for word in ("季度", "三个月", "年内", "十五五")):
        return "一季"
    if any(word in text for word in ("停产", "禁令", "暂停", "停止出口", "禁止出口", "缺料", "减产")):
        return "数日"
    return "当天"


def _trigger(text: str, category: str) -> str:
    if category == "关税与出口管制":
        if any(word in text for word in ("复职", "恢复")) and any(word in text for word in ("黄仁勋", "英伟达")):
            return "芯片职务"
        if "芯片" in text:
            return "芯片出口"
        return "关税"
    if category == "监管":
        if any(word in text for word in ("集采", "药")):
            return "医药监管"
        if "做市" in text:
            return "做市"
        if "印花税" in text:
            return "印花税"
        return "交易监管"
    return category


def _rank(text: str) -> int:
    if re.search(r"\d+(?:\.\d+)?\s*(?:亿元|%|％|个百分点)", text):
        return 2
    if re.search(r"\d", text):
        return 1
    return 0


def _better(new: dict, old: dict) -> bool:
    new_rank = _rank(new["事实一句"])
    old_rank = _rank(old["事实一句"])
    if new_rank != old_rank:
        return new_rank > old_rank
    return len(new["事实一句"]) > len(old["事实一句"])


def _small_buyback(text: str, category: str) -> bool:
    if category != "并购与回购" or "回购" not in text:
        return False
    if "收购" in text or "并购" in text:
        return False
    return not any(float(amount) >= 1 for amount in YI_RE.findall(text))


def classify_text(text: str) -> dict | None:
    """One sentence in, or None when it is noise or has no tradable sector."""
    cleaned = _clean(text)
    if not cleaned or any(word in cleaned for word in VETO):
        return None
    if "最不发达" in cleaned:
        return None
    category = _category(cleaned)
    if category is None or _small_buyback(cleaned, category):
        return None
    sectors = _sectors(cleaned, category)
    if not sectors:
        return None
    return {
        "类别": category,
        "触发": _trigger(cleaned, category),
        "事实一句": _one_fact(cleaned),
        "映射板块": "、".join(sectors),
        "时效": _horizon(cleaned),
        "改不改权重": WEIGHT,
    }


def explode(item: dict) -> list[dict]:
    """One list row can carry several events. Keep the longer sentence per class."""
    if not item.get("url"):
        return []
    title = _clean(item.get("title") or "")
    summary = _clean(item.get("summary") or "")
    parts = split_sentences(summary) if summary else []
    if title and title not in summary:
        parts = [title, *parts]
    if not parts and title:
        parts = [title]
    best: dict[str, dict] = {}
    for part in parts:
        chosen = classify_text(part)
        if chosen is None:
            continue
        previous = best.get(chosen["触发"])
        if previous is None or _better(chosen, previous):
            best[chosen["触发"]] = chosen
    kept = list(best.values())
    clock = item.get("clock") or ""
    rows = []
    for chosen in kept:
        row = dict(chosen)
        row["来源"] = item.get("source") or ""
        row["时间"] = clock[11:16]
        row["clock"] = clock
        row["地址"] = item["url"]
        rows.append(row)
    return rows


def _cap(rows: list[dict], limit: int | None) -> list[dict]:
    indexed = list(enumerate(rows))
    indexed.sort(key=lambda pair: (pair[1]["clock"], -pair[0]), reverse=True)
    kept = indexed if limit is None else indexed[:limit]
    kept.sort(key=lambda pair: (pair[1]["clock"], pair[0]))
    return [row for _, row in kept]


def select(items: list[dict], day: str) -> list[dict]:
    """Keep that day's classified rows. Flash and telegraph stop at 20 each."""
    grouped: dict[str, list[dict]] = {name: [] for name in CAPS}
    for item in items:
        source = item.get("source") or ""
        clock = item.get("clock") or ""
        if source not in CAPS or not CLOCK_RE.match(clock) or clock[:10] != day:
            continue
        grouped[source].extend(explode(item))
    chosen: list[dict] = []
    for source, rows in grouped.items():
        chosen.extend(_cap(rows, CAPS[source]))
    chosen.sort(key=lambda row: (row["clock"], row["来源"], row["类别"]))
    deduped = []
    seen: set[tuple[str, str, str]] = set()
    for row in chosen:
        key = (row["地址"], row["类别"], row["事实一句"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def render(day: str, rows: list[dict], mounts: list[dict] | None = None) -> str:
    lines = [f"# 市场资讯 {day}", "", "不进 W1–W8。不改行为分。", ""]
    for item in mounts or []:
        lines.append(f"未挂：{item.get('source', '')}（{item.get('error', '')}）")
    if mounts:
        lines.append("")
    if not rows:
        lines.append("这一日没有入选资讯。")
        return "\n".join(lines) + "\n"
    lines.append("| 时间 | 来源 | 类别 | 事实一句 | 映射板块 | 时效 | 改不改权重 | 地址 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        lines.append(
            "| {时间} | {来源} | {类别} | {事实一句} | {映射板块} | {时效} | 不改权重 | {地址} |".format(**row)
        )
    return "\n".join(lines) + "\n"


def write_page(root: Path, day: str, text: str) -> Path:
    """Rewrite the day page. Do not append to or replace the jsonl facts."""
    path = root / "hot" / "news" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def items_from_em(payload: dict, source: str) -> list[dict]:
    data = payload.get("data") or {}
    raw_rows = data.get("list") or data.get("fastNewsList") or []
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        url = str(item.get("uniqueUrl") or "")
        code = str(item.get("code") or "")
        if not url and code:
            url = f"https://finance.eastmoney.com/a/{code}.html"
        rows.append(
            {
                "source": source,
                "title": str(item.get("title") or ""),
                "summary": str(item.get("summary") or ""),
                "clock": str(item.get("showTime") or "")[:16],
                "url": url,
            }
        )
    return rows


def items_from_cls(payload: dict) -> list[dict]:
    raw_rows = (payload.get("data") or {}).get("roll_data") or []
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        ctime = item.get("ctime")
        if ctime in (None, ""):
            clock = ""
        else:
            clock = datetime.fromtimestamp(int(ctime), tz=BEIJING).strftime("%Y-%m-%d %H:%M")
        url = str(item.get("shareurl") or "")
        if not url and item.get("id"):
            url = f"https://www.cls.cn/detail/{item['id']}"
        rows.append(
            {
                "source": SOURCE_CLS,
                "title": str(item.get("title") or ""),
                "summary": str(item.get("content") or ""),
                "clock": clock,
                "url": url,
            }
        )
    return rows


def items_from_cctv_index(html: str, day: str) -> list[dict]:
    compact = day.replace("-", "")
    slash = f"{day[:4]}/{day[5:7]}/{day[8:10]}"
    seen: set[str] = set()
    rows = []
    for href, raw in LINK_RE.findall(html):
        if "xwlb/day" in href or (compact not in href and slash not in href):
            continue
        title = _clean(raw).removeprefix("[视频]").strip()
        if len(title) < 4 or href in seen:
            continue
        seen.add(href)
        url = href if href.startswith("http") else "https://tv.cctv.com" + href
        rows.append(
            {
                "source": SOURCE_CCTV,
                "title": title,
                "summary": "",
                "clock": f"{day} 19:00",
                "url": url,
            }
        )
    return rows


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def eastmoney_body(html: str) -> str:
    mark = html.find('id="ContentBody"')
    if mark < 0:
        return ""
    start = html.find(">", mark)
    if start < 0:
        return ""
    return html_to_text(html[start + 1 : start + 1 + 12000])


def article_text(html: str) -> str:
    for klass in ("cnt_bd", "content_area"):
        start = html.find(f'class="{klass}"')
        if start < 0:
            continue
        return html_to_text(html[start : start + 8000])
    return ""


def clean_broadcast(text: str) -> str:
    cleaned = text.strip()
    for prefix in BROADCAST_PREFIXES:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :].strip()
    return cleaned


def _fetch_bytes(url: str, timeout: int = 15) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0"}
    if "cls.cn" in url:
        headers["Referer"] = "https://www.cls.cn/telegraph"
    with open_url(url, headers=headers, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url: str) -> dict:
    raw = _fetch_bytes(url)
    return json.loads(raw.decode("utf-8", "replace"))


def fetch_cls(now: int | None = None) -> list[dict]:
    stamp = int(time.time()) if now is None else now
    pairs = [
        ("app", "CailianpressWeb"),
        ("category", ""),
        ("last_time", str(stamp)),
        ("os", "web"),
        ("refresh_type", "1"),
        ("rn", "20"),
        ("sv", "8.4.6"),
    ]
    query = urlencode(pairs)
    sign = hashlib.md5(hashlib.sha1(query.encode("utf-8")).hexdigest().encode("utf-8")).hexdigest()
    return items_from_cls(fetch_json(f"{CLS_URL}?{query}&sign={sign}"))


def fill_breakfast(items: list[dict], day: str) -> list[dict]:
    """The breakfast list is a teaser. The article body holds the numbered items."""
    filled = []
    opened = 0
    for item in items:
        clock = str(item.get("clock") or "")
        if item.get("source") != SOURCE_BREAKFAST or not clock.startswith(day) or opened >= 3:
            filled.append(item)
            continue
        try:
            html = _fetch_bytes(item["url"]).decode("utf-8", "replace")
            body = eastmoney_body(html)
            opened += 1
        except Exception:  # noqa: BLE001 — the teaser still classifies
            filled.append(item)
            continue
        copied = dict(item)
        if body:
            copied["summary"] = body
        filled.append(copied)
    return filled


def fill_cctv(items: list[dict]) -> list[dict]:
    """Open broadcast pages so the fact sentence can come from the body."""
    filled = []
    fetched = 0
    for item in items:
        if fetched >= CCTV_FETCH_CAP:
            filled.append(item)
            continue
        try:
            body = clean_broadcast(article_text(_fetch_bytes(item["url"]).decode("utf-8", "replace")))
            fetched += 1
        except Exception:  # noqa: BLE001 — one dead page stays a title
            filled.append(item)
            continue
        copied = dict(item)
        if body:
            copied["summary"] = body
        filled.append(copied)
    return filled


def fetch_cctv(day: str) -> list[dict]:
    compact = day.replace("-", "")
    html = _fetch_bytes(CCTV_DAY.format(compact=compact)).decode("utf-8", "replace")
    return fill_cctv(items_from_cctv_index(html, day))


def collect(day: str) -> tuple[list[dict], list[dict]]:
    items: list[dict] = []
    mounts: list[dict] = []
    jobs = (
        (SOURCE_BREAKFAST, lambda: fill_breakfast(items_from_em(fetch_json(BREAKFAST_URL), SOURCE_BREAKFAST), day)),
        (SOURCE_FLASH, lambda: items_from_em(fetch_json(FLASH_URL), SOURCE_FLASH)),
        (SOURCE_CLS, lambda: fetch_cls()),
        (SOURCE_CCTV, lambda: fetch_cctv(day)),
    )
    for source, fetch in jobs:
        try:
            items.extend(fetch())
        except Exception as exc:  # noqa: BLE001 — a dead list is 未挂
            mounts.append({"source": source, "error": type(exc).__name__})
    return items, mounts


def _public_row(row: dict) -> dict:
    return {key: row[key] for key in ("时间", "来源", "类别", "事实一句", "映射板块", "时效", "改不改权重", "地址")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="市场资讯五类。不改权重，不写台账，不下单。")
    parser.add_argument("--day", required=True, help="北京时间日期，YYYY-MM-DD")
    parser.add_argument("--root", default="", help="资料湖目录，默认 runtime/lake")
    parser.add_argument("--items", default="", help="规范化条目 JSON。给出则不访问网络")
    parser.add_argument("--no-write", action="store_true", help="只印出，不写当日页")
    args = parser.parse_args(argv)
    try:
        day = normalize_day(args.day)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.items:
        items = json.loads(Path(args.items).read_text(encoding="utf-8"))
        mounts: list[dict] = []
    else:
        items, mounts = collect(day)
    rows = select(items, day)
    text = render(day, rows, mounts)
    path = ""
    if not args.no_write:
        root = Path(args.root) if args.root else LAKE
        path = str(write_page(root, day, text))
    payload = {
        "day": day,
        "path": path,
        "count": len(rows),
        "rows": [_public_row(row) for row in rows],
        "mounts": mounts,
        "weights": "不改",
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
