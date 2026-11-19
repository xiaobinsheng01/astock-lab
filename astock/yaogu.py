#!/usr/bin/env python3
"""Cross-year limit-up sleeve. Classifies a close and ranks the pre-market five.

The sleeve is separate from the desk behavior score. This module does not
change a weight, does not read the ledger, and does not place an order.
Live overnight queues start on 2026-12-01 and stop before 2027-02-06.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from astock.close_inputs import round_fen

WINDOW_OPEN = "2026-12-01"
WINDOW_SHUT = "2027-02-06"
MAIN_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")
# Desk hard gates. These names never enter the overnight queue.
BLOCKED = {
    "002081": "金螳螂",
    "601061": "中信金属",
    "000559": "万向钱潮",
    "601868": "中国能建",
}
VR_OVERNIGHT = 1.3
VR_VETO = 2.2
# 2027-02-06 is the first day of the goat year. The character counts only in a limit-up name.
ZODIAC = "羊"
BROKEN_DOWN = 0.25
# Corporate fillers. A shared pair of characters has to be outside this list to be a name cluster.
NAME_STOP = frozenset({
    "股份", "集团", "控股", "科技", "发展", "实业", "国际", "有限", "公司",
    "投资", "产业", "中国", "电子", "能源", "信息", "网络", "智能", "生物",
    "医药", "化工", "建设", "环保", "环境", "数据", "数字", "光电", "光学",
})
# Place names. A region counts only when two names share one and their industries differ.
PLACES = (
    "哈尔滨", "内蒙古", "石家庄",
    "海南", "西藏", "新疆", "北京", "上海", "深圳", "广州", "成都", "重庆",
    "天津", "宁波", "厦门", "青岛", "大连", "南京", "杭州", "武汉", "长沙",
    "郑州", "西安", "沈阳", "长春", "昆明", "贵阳", "南宁", "兰州", "合肥",
    "福州", "济南", "太原", "南昌", "珠海", "佛山", "苏州", "无锡", "西部",
    "北方", "南方", "东北", "广西", "宁夏", "青海",
)

# 2026-11-09 close. A settlement cohort, not the daily monitor.
SEED: tuple[dict[str, Any], ...] = (
    {"code": "002310", "name": "东方新能", "board": 2, "close": 2.55, "vr": 0.66, "seed_tier": "持仓"},
    {"code": "603366", "name": "日出东方", "board": 2, "close": 9.89, "vr": 0.10, "seed_tier": "持仓"},
    {"code": "002037", "name": "保利联合", "board": 1, "close": 7.23, "vr": 0.68, "seed_tier": "持仓"},
    {"code": "601188", "name": "龙江交通", "board": 2, "close": 4.19, "vr": 0.41, "seed_tier": "隔夜"},
    {"code": "600327", "name": "大东方", "board": 2, "close": 5.40, "vr": 0.95, "seed_tier": "隔夜"},
    {"code": "002578", "name": "闽发铝业", "board": 6, "close": 5.51, "vr": 1.19, "seed_tier": "观察"},
    {"code": "000525", "name": "红太阳", "board": 2, "close": 5.52, "vr": 1.78, "seed_tier": "观察"},
    {"code": "600278", "name": "东方创业", "board": 2, "close": 7.83, "vr": 1.50, "seed_tier": "观察"},
    {"code": "002124", "name": "天邦食品", "board": 1, "close": 2.20, "vr": 1.17, "seed_tier": "观察"},
    {"code": "600715", "name": "文投控股", "board": 1, "close": 2.59, "vr": 0.82, "seed_tier": "观察"},
    {"code": "600408", "name": "安泰集团", "board": 1, "close": 3.32, "vr": 1.24, "seed_tier": "观察"},
    {"code": "600609", "name": "金杯汽车", "board": 1, "close": 3.48, "vr": 3.67, "seed_tier": "观察"},
    {"code": "002596", "name": "海南瑞泽", "board": 1, "close": 3.48, "vr": 1.25, "seed_tier": "观察"},
    {"code": "600853", "name": "龙建股份", "board": 1, "close": 3.85, "vr": 1.76, "seed_tier": "观察"},
    {"code": "600792", "name": "云煤能源", "board": 1, "close": 4.20, "vr": 4.79, "seed_tier": "观察"},
    {"code": "002638", "name": "勤上股份", "board": 1, "close": 4.33, "vr": 1.63, "seed_tier": "观察"},
    {"code": "600121", "name": "郑州煤电", "board": 1, "close": 4.73, "vr": 1.81, "seed_tier": "观察"},
    {"code": "600892", "name": "大晟文化", "board": 1, "close": 5.09, "vr": 1.41, "seed_tier": "观察"},
    {"code": "002172", "name": "澳洋健康", "board": 1, "close": 6.18, "vr": 0.91, "seed_tier": "观察"},
    {"code": "002347", "name": "泰尔股份", "board": 1, "close": 7.00, "vr": 0.73, "seed_tier": "观察"},
    {"code": "002488", "name": "金固股份", "board": 1, "close": 7.48, "vr": 0.99, "seed_tier": "观察"},
    {"code": "603660", "name": "苏州科达", "board": 1, "close": 9.26, "vr": 0.39, "seed_tier": "观察"},
    {"code": "000530", "name": "冰山冷热", "board": 1, "close": 9.57, "vr": 0.49, "seed_tier": "观察"},
)


def orders_allowed(day: str) -> bool:
    """True only inside the 2026-12-01 window, before the 2027 festival halt."""
    return WINDOW_OPEN <= day < WINDOW_SHUT


def limit_up_price(prev_close: float) -> float:
    return round_fen(prev_close * 1.1)


def shape_of(open_: float, high: float, low: float, close: float, prev_close: float) -> str:
    """一字, T字, or 换手. 一字 is a range of at most 1 fen or 0.15% of the close."""
    span = high - low
    if span <= 0.01 or span <= close * 0.0015:
        return "一字"
    if open_ >= limit_up_price(prev_close) - 0.001:
        return "T字"
    return "换手"


def _first_close(row: dict[str, Any]) -> float | None:
    if row.get("first_close") is not None:
        return float(row["first_close"])
    board = int(row["board"])
    if board == 1:
        return float(row["close"])
    return None


def _mainboard(code: str) -> bool:
    return code.startswith(MAIN_PREFIXES)


def _blocked_name(name: str) -> bool:
    text = name.upper()
    return "ST" in text or "退" in name


def classify(row: dict[str, Any]) -> dict[str, Any]:
    """One limit-up close. Missing first-board price above board 1 stays out of the pool."""
    code = str(row["code"])
    name = str(row["name"])
    board = int(row["board"])
    close = float(row["close"])
    prev_close = float(row["prev_close"])
    open_ = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    volume = float(row["volume"])
    prev_volume = row.get("prev_volume")
    vr = None if not prev_volume else volume / float(prev_volume)
    shape = shape_of(open_, high, low, close, prev_close)
    first = _first_close(row)
    out = {
        "code": code,
        "name": name,
        "board": board,
        "close": close,
        "shape": shape,
        "vr": None if vr is None else round(vr, 4),
        "first_close": first,
        "tier": "池外",
        "hy": _industry(row),
        "broken": bool(row.get("broken")),
        "sector_pct": row.get("sector_pct"),
    }
    if code in BLOCKED or not _mainboard(code) or _blocked_name(name):
        return out
    if first is None or first >= 10:
        return out
    if shape == "一字" and board in (1, 2, 3):
        out["tier"] = "持仓"
    elif board == 2 and shape == "换手" and vr is not None and vr >= VR_VETO:
        out["tier"] = "否决"
    elif board in (2, 3) and shape == "换手" and vr is not None and vr < VR_OVERNIGHT:
        out["tier"] = "隔夜"
    elif board in (2, 3) and shape == "T字" and vr is not None and vr < VR_OVERNIGHT:
        out["tier"] = "只看"
    else:
        out["tier"] = "观察"
    return out


def tail_queue(row: dict[str, Any]) -> dict[str, Any]:
    """14:55 queue. Yesterday's last five minutes are added before the 1.3 check.

    A fill is not revoked when the full-day ratio is known at 15:10.
    Missing last-five volume cannot queue.
    """
    prev = row.get("prev_volume")
    last5 = row.get("last5_volume")
    so_far = row.get("volume_1455")
    result: dict[str, Any] = {
        "code": str(row.get("code", "")),
        "name": str(row.get("name", "")),
        "queue": False,
        "buffered_vr": None,
        "fill_stands": False,
    }
    if last5 is None or not prev or so_far is None:
        return result
    probed = dict(row)
    probed["volume"] = so_far
    item = classify(probed)
    buffered = (float(so_far) + float(last5)) / float(prev)
    result["buffered_vr"] = round(buffered, 4)
    result["code"] = item["code"]
    result["name"] = item["name"]
    qualifies = item["tier"] != "池外" and item["board"] in (2, 3) and item["shape"] == "换手" and buffered < VR_OVERNIGHT
    result["queue"] = qualifies
    result["fill_stands"] = qualifies
    return result


def _grams(name: str) -> set[str]:
    chars = [char for char in name if "\u4e00" <= char <= "\u9fff"]
    found = set()
    for index in range(len(chars) - 1):
        gram = "".join(chars[index : index + 2])
        if gram not in NAME_STOP and gram not in PLACES and gram != ZODIAC:
            found.add(gram)
    return found


def _industry(row: dict[str, Any]) -> str:
    return str(row.get("hy") or row.get("industry") or "")


def _place_of(name: str) -> str:
    found = [place for place in PLACES if place in name]
    if not found:
        return ""
    return max(found, key=len)


def _place_groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        place = _place_of(str(row.get("name") or ""))
        if place:
            groups.setdefault(place, []).append(row)
    return groups


def _industries_differ(group: list[dict[str, Any]]) -> bool:
    names = [_industry(row) for row in group]
    if any(not name for name in names):
        return False
    return len(set(names)) >= 2


def element_view(
    rows: list[dict[str, Any]],
    prior: list[dict[str, Any]] | None = None,
    official: list[dict[str, Any]] | None = None,
    mood: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tag name, zodiac, region, official text, and tape context.

    Tags do not change a tier and do not change a queue decision.
    """
    clusters: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for gram in _grams(str(row.get("name") or "")):
            clusters.setdefault(gram, []).append(row)
    cluster_lines = []
    for gram in sorted(clusters):
        uniq = {row.get("code"): row for row in clusters[gram]}
        if len(uniq) < 2:
            continue
        cluster_lines.append("名称簇\t" + gram + "\t" + " ".join(str(row.get("name")) for row in uniq.values()))
    if not cluster_lines:
        cluster_lines.append("名称簇\t无")

    zodiac_rows = [row for row in rows if ZODIAC in str(row.get("name") or "")]
    zodiac_lines = ["生肖\t" + (" ".join(str(row.get("name")) for row in zodiac_rows) if zodiac_rows else "无")]
    pointed = any(item.get("clock") and ZODIAC in str(item.get("text") or "") for item in official or [])
    if pointed and not zodiac_rows:
        zodiac_lines.append("生肖稿\t已点\t池中无票")

    today = _place_groups(rows)
    earlier = _place_groups(prior or [])
    region_lines = []
    for place in sorted(today):
        group = today[place]
        if len(group) < 2 or not _industries_differ(group):
            continue
        prior_group = earlier.get(place) or []
        formed = len(prior_group) >= 2 and _industries_differ(prior_group)
        state = "成簇" if formed else "当日"
        region_lines.append(f"地域\t{place}\t{state}\t" + " ".join(str(row.get("name")) for row in group))
    if not region_lines:
        region_lines.append("地域\t无")

    official_lines = []
    for kind in ("文件", "会议", "数字"):
        matched: list[str] = []
        for item in official or []:
            if item.get("kind") != kind or not item.get("clock"):
                continue
            codes = set(item.get("codes") or [])
            industries = set(item.get("industries") or [])
            words = [word for word in (item.get("words") or []) if word]
            for row in rows:
                industry = _industry(row)
                name = str(row.get("name") or "")
                if row.get("code") in codes or industry in industries or any(word in name for word in words):
                    matched.append(name)
        official_lines.append(kind + "\t" + (" ".join(dict.fromkeys(matched)) if matched else "无"))

    if not mood:
        mood_lines = ["情绪\t未核", "市场\t未核", "降档\t无"]
    else:
        mood_lines = ["情绪\t已核", "市场\t已核"]
        sector = mood.get("sector_pct") or {}
        ratio = mood.get("broken_ratio")
        downs = []
        for row in rows:
            reasons = []
            if row.get("broken") and ratio is not None and float(ratio) >= BROKEN_DOWN:
                reasons.append("炸板")
            industry = _industry(row)
            pct = sector.get(industry) if industry else None
            if pct is None and row.get("sector_pct") is not None:
                pct = row.get("sector_pct")
            if pct is not None and float(pct) < 0:
                reasons.append("行业指数跌")
            if reasons:
                downs.append(f"降档\t{row.get('code')}\t{row.get('name')}\t{'+'.join(reasons)}")
        mood_lines.extend(downs or ["降档\t无"])
    return {
        "lines": cluster_lines + zodiac_lines + region_lines + official_lines + mood_lines,
    }


def _attention_key(item: dict[str, Any]) -> tuple[int, float, str] | None:
    tier = item["tier"]
    board = item["board"]
    if tier == "隔夜":
        rank = 0
    elif tier == "持仓" and board in (2, 3):
        rank = 1
    elif tier == "持仓" and board == 1:
        rank = 2
    else:
        return None
    vr = item["vr"]
    return (rank, 999.0 if vr is None else float(vr), item["code"])


def top5(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Up to five names to check, not to buy. 隔夜, then board 2–3 一字, then board 1 一字."""
    ranked = []
    for row in rows:
        item = row if "tier" in row and "shape" in row else classify(row)
        key = _attention_key(item)
        if key is not None:
            ranked.append((key, item))
    ranked.sort(key=lambda pair: pair[0])
    return [item for _, item in ranked[:5]]


def format_monitor() -> str:
    lines = [f"结算样本 {len(SEED)} 只，种子日 2026-11-09。不是每日监控池"]
    for row in SEED:
        lines.append(
            f"{row['seed_tier']}\t{row['code']}\t{row['name']}\t{row['board']}板\t{row['close']:.2f}\t量比{row['vr']:.2f}"
        )
    return "\n".join(lines)


def _vr_text(item: dict[str, Any]) -> str:
    return "缺" if item["vr"] is None else f"{item['vr']:.2f}"


def format_report(
    day: str,
    rows: list[dict[str, Any]],
    prior: list[dict[str, Any]] | None = None,
    official: list[dict[str, Any]] | None = None,
    mood: dict[str, Any] | None = None,
) -> str:
    picked = top5(rows)
    watch = [row for row in rows if row.get("tier") == "只看"]
    watch.sort(key=lambda item: (999.0 if item["vr"] is None else float(item["vr"]), item["code"]))
    gate = "可排队" if orders_allowed(day) else "窗口未开，不排队"
    lines = [f"{day} 盘前核对 {gate}"]
    if not picked:
        lines.append("核对：无")
    for index, item in enumerate(picked, start=1):
        lines.append(
            f"{index}\t{item['tier']}\t{item['code']}\t{item['name']}\t{item['board']}板\t{item['shape']}\t收盘{item['close']:.2f}\t量比{_vr_text(item)}"
        )
    lines.append("只看不排")
    if not watch:
        lines.append("无")
    for item in watch:
        lines.append(
            f"{item['code']}\t{item['name']}\t{item['board']}板\t{item['shape']}\t收盘{item['close']:.2f}\t量比{_vr_text(item)}"
        )
    lines.append("元素")
    lines.extend(element_view(rows, prior, official, mood)["lines"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="妖股收盘分类和盘前五只。不下单。")
    parser.add_argument("--monitor", action="store_true", help="打印 2026-11-09 初始监控")
    parser.add_argument("--day", default="", help="交易日 YYYY-MM-DD")
    parser.add_argument("--rows", default="", help="涨停收盘 JSON 列表")
    parser.add_argument("--prior", default="", help="上一日涨停名单 JSON，用来核地域是否成簇")
    parser.add_argument("--official", default="", help="带发布时间的文件、会议、数字 JSON")
    parser.add_argument("--mood", default="", help="炸板率和行业指数涨跌 JSON")
    args = parser.parse_args(argv)
    if args.monitor:
        print(format_monitor())
        return 0
    if not args.day or not args.rows:
        parser.error("分类需要 --day 和 --rows")
    payload = json.loads(sys.stdin.read() if args.rows == "-" else open(args.rows, encoding="utf-8").read())
    def load(path: str):
        if not path:
            return None
        return json.loads(open(path, encoding="utf-8").read())

    classified = [classify(row) for row in payload]
    print(format_report(args.day, classified, load(args.prior), load(args.official), load(args.mood)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
