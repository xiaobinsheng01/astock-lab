#!/usr/bin/env python3
"""A股交易员角色：把一整套数据收成结构化的 claim 草稿，再校验能不能落进记分板。

交易员不是聊天角色，是一个有固定输出格式的岗位。它只做三件事：

  1. 读同一轮已经算好的数（行情、行业表、量价四态、行为分、板块分类）。
  2. 按固定格子写 claim：主路径、板块强弱、量价、风险。一格一句话，每句必须
     带核对条件。
  3. 交给 `astock.forecast` 收进记分板。收不进去的句子不许写进结论。

这个模块做的是 1 和 2 之间的翻译：`draft` 把数读成候选 claim，`check` 校验
一份 claim 草稿是否写得出核对条件。它不假装自己是模型，也不写自然语言结论——
结论由角色正文（`rules/09-trader.md`）规定的模型来写，这里只保证「写下来的每句
都能收盘核对」。

三条纪律，和 `forecast` 一致：

  - 数没取到就写未核，不猜方向。
  - 格子空着就空着，不为了凑满而编一条。
  - 波浪只写文字，不做成 check，不进验证。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from astock.forecast import KINDS, validate

# 交易员的固定格子。每格一个 claim，格子里可以放 1–3 条 check。
SLOTS = (
    "index_path",    # 上证主路径：收在哪一段
    "index_dir",     # 上证方向
    "sector_strong", # 哪些行业会强于上证
    "sector_state",  # 板块分类
    "volume",        # 量价四态
    "risk",          # 风险触发
)

SLOT_READS = {
    "index_path": "上证收在四条路径的哪一段。用上一交易日的低点和高点，不自己造边界。",
    "index_dir": "上证收涨还是收跌。这一格最容易写，也最容易被说糊。",
    "sector_strong": "哪些申万一级行业会强于上证，写清强几个百分点算中。",
    "sector_state": "行业的两栏分类明天会是什么。分类是历史统计，不改成分那次不算。",
    "volume": "量价四态落在哪一格。行业用行业自己的容差，个股用个股的。",
    "risk": "哪一条风险会触发。触发条件要写成一个能收盘判定的事实。",
}


def slot_prompt(as_of: str = "") -> dict:
    """给模型看的格子清单。模型按这个填，不按自己的习惯填。"""
    return {
        "as_of": as_of,
        "slots": [
            {"slot": name, "read": SLOT_READS[name]} for name in SLOTS
        ],
        "kinds": list(KINDS),
        "rules": [
            "一格至少一条 check，没有核对条件的句子不写。",
            "数没取到写未核，不猜方向。",
            "波浪只写文字，放进 wave，不做成 check。",
            "最多 6 条 check，超过就说明这句不像一句能核的话。",
        ],
    }


def draft(
    *,
    as_of: str,
    name: str,
    quotes: dict | None = None,
    sectors: dict | None = None,
    breadth: float | None = None,
) -> dict:
    """把当轮已经算好的数翻成一份 claim 草稿。

    这里只做「有数才有 claim」：缺数的格子空着，不给默认方向。返回的每个格子
    都已经带好 `check`，模型只需要确认或改写，不需要重造核对条件。
    """
    quotes = quotes or {}
    sectors = sectors or {}
    checks: dict[str, list[dict]] = {}

    sh = quotes.get("000001") or {}
    if sh.get("pct") is not None:
        direction = "up" if sh["pct"] > 0 else ("down" if sh["pct"] < 0 else "flat")
        checks["index_dir"] = [{"kind": "index_pct", "code": "000001", "want": direction}]

    # 主路径这一格要上一交易日的高低点。没有就不给，不拿当日高低点顶替。
    if sh.get("prev_high") is not None and sh.get("prev_low") is not None:
        midpoint = (sh["prev_high"] + sh["prev_low"]) / 2.0
        px = sh.get("px")
        if px is not None:
            if px > sh["prev_high"]:
                zone = "above_hard"
            elif px > midpoint:
                zone = "hard_upper"
            elif px >= sh["prev_low"]:
                zone = "narrow_lower"
            else:
                zone = "below_hard"
            checks["index_path"] = [{"kind": "index_zone", "want": zone}]

    # 行业强弱：只对当天强于上证达到 1 个百分点的行业出候选，差不到不写。
    sh_pct = sh.get("pct")
    if sh_pct is not None:
        strong = []
        for sector, row in sectors.items():
            pct = (row or {}).get("pct")
            if pct is None:
                continue
            if pct - sh_pct >= 1.0:
                strong.append((sector, pct))
        strong.sort(key=lambda item: -item[1])
        if strong:
            sector, pct = strong[0]
            checks["sector_strong"] = [
                {"kind": "sector_vs_index", "sector": sector, "margin_pp": 1.0, "want": True}
            ]

    # 板块分类：只取脚本已经判出来的，不自己判。
    picks = [
        {"kind": "industry_pick", "sector": sector, "want": row["pick"]}
        for sector, row in sectors.items()
        if (row or {}).get("pick") in ("主线", "仅进攻", "仅防御", "无")
    ]
    if picks:
        checks["sector_state"] = picks[:2]

    if breadth is not None:
        checks["risk"] = [{"kind": "breadth", "want": 0.5}]

    claims = {}
    for slot in SLOTS:
        if slot in checks:
            claims[slot] = {
                "slot": slot,
                "read": SLOT_READS[slot],
                "checks": checks[slot],
            }
    return {
        "as_of": as_of,
        "name": name,
        "claims": [claims[slot] for slot in SLOTS if slot in claims],
        "missing": [slot for slot in SLOTS if slot not in claims],
    }


def check(draft_payload: dict) -> dict:
    """校验一份 claim 草稿能不能收进记分板。

    每个 claim 走和 `astock.forecast` 完全相同的 `validate`，所以这里通过的，
    `predict` 一定收得下；这里不通过的，`predict` 一定拒收。两套规则不能分叉。
    """
    problems = []
    accepted = []
    claims = draft_payload.get("claims")
    if not isinstance(claims, list) or not claims:
        problems.append("没有 claim：这一轮不写结论")
        return {"ok": False, "problems": problems, "accepted": []}
    for index, claim in enumerate(claims):
        slot = claim.get("slot")
        where = f"claims[{index}]"
        if slot not in SLOTS:
            problems.append(f"{where}.slot 不认识：{slot!r}，只能是 {', '.join(SLOTS)}")
            continue
        record = {
            "date": draft_payload.get("as_of"),
            "name": f"{draft_payload.get('name') or '上证'}.{slot}",
            "checks": claim.get("checks") or [],
        }
        found = validate(record)
        if found:
            problems.extend(f"{where}({slot})：{item}" for item in found)
        else:
            accepted.append({"slot": slot, "record": record})
    return {"ok": not problems, "problems": problems, "accepted": accepted}


def format_draft(payload: dict) -> str:
    lines = [f"{payload.get('as_of')}  {payload.get('name')}"]
    for claim in payload.get("claims") or []:
        wanted = "；".join(str(item.get("want")) for item in claim.get("checks") or [])
        lines.append(f"  {claim['slot']}: {wanted}")
    missing = payload.get("missing") or []
    if missing:
        lines.append(f"  未写（缺数或不写）：{', '.join(missing)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="A股交易员 claim 草稿与校验。不改权重，不下单。",
        epilog="草稿只是候选，收不收得下由 astock.forecast 决定。",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    prompt = sub.add_parser("slots", help="印出交易员的固定格子和允许的 check 类型")
    prompt.add_argument("--as-of", default="")

    make = sub.add_parser("draft", help="从当轮取数包生成 claim 草稿")
    make.add_argument("--file", required=True, help="取数包 JSON")
    make.add_argument("--name", default="上证")
    make.add_argument("--json", action="store_true", help="只印 JSON，方便管道")

    verify = sub.add_parser("check", help="校验一份草稿，从 stdin 或 --file 读")
    verify.add_argument("--file", default="")

    args = parser.parse_args(argv)
    if args.cmd == "slots":
        print(json.dumps(slot_prompt(args.as_of), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "draft":
        try:
            packet = json.loads(Path(args.file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"取数包读不出来：{exc}", file=sys.stderr)
            return 2
        payload = draft(
            as_of=str(packet.get("date") or ""),
            name=args.name,
            quotes=packet.get("quotes") or {},
            sectors=packet.get("sectors") or {},
            breadth=packet.get("breadth"),
        )
        if args.json:
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            return 0
        print(format_draft(payload))
        print()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"不是合法 JSON：{exc}", file=sys.stderr)
        return 2
    result = check(payload)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
