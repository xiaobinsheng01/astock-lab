#!/usr/bin/env python3
"""Map one fact sentence onto sleeves the desk already has.

The script classifies. It does not score W1–W8, does not write the ledger,
and does not place an order. A card that only says the number misses the
scale is unfinished until these lines are written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

UP = ("上涨", "上升", "扩大", "增加", "回升")
DOWN = ("下降", "下跌", "回落", "减少", "下行")
ELECTRONICS = ("计算机通信", "电子设备", "通信和其他电子")
ELECTRICAL = ("电气机械", "电力设备")
FOOD = ("食品价格", "鲜菜", "鲜果")
OIL = ("原油", "油价", "布伦特", "轻质原油")
OMO = ("逆回购", "公开市场")
BROAD = ("制造业贷款",)
COMPANY = ("控制权", "实际控制人", "增持", "减持", "立案告知", "协议转让", "股权结构")
SERVICE = ("服务价格",)

FOUR = (
    ("通信", "399389"),
    ("电子", "399811"),
    ("信息", "000993"),
    ("科创芯片", "000685"),
)


def _side(window: str) -> str:
    up = any(word in window for word in UP)
    down = any(word in window for word in DOWN)
    if up and down:
        return "分化"
    if up:
        return "偏多"
    if down:
        return "偏空"
    return "无方向"


def _check(published: str, settlement_required: bool) -> str:
    if settlement_required:
        return "待结算"
    found = re.search(r"(\d{2}):(\d{2})", published or "")
    if not found:
        return "核对日未写"
    hour, minute = int(found.group(1)), int(found.group(2))
    if (hour, minute) >= (15, 0):
        return "下一交易日收盘"
    return "当日收盘"


def _line(
    side: str,
    sleeves: list[tuple[str, str]],
    note: str,
    check: str,
    chip_separate: bool = False,
) -> dict:
    return {
        "side": side,
        "sleeves": [{"name": name, "code": code} for name, code in sleeves],
        "chip_separate": chip_separate,
        "note": note,
        "check": check,
        "changes_score": False,
        "used_this_round": False,
    }


def _clause_lines(clause: str, published: str) -> list[dict]:
    lines: list[dict] = []
    side = _side(clause)
    if any(word in clause for word in ELECTRONICS):
        chip_separate = "芯片" in clause and "电子设备" not in clause
        lines.append(
            _line(
                side,
                list(FOUR),
                "芯片单独确认" if chip_separate else "芯片不单独确认",
                _check(published, False),
                chip_separate,
            )
        )
    elif "芯片" in clause:
        lines.append(
            _line(
                side,
                [("科创芯片", "000685")],
                "只核科创芯片",
                _check(published, False),
                True,
            )
        )
    if any(word in clause for word in ELECTRICAL):
        lines.append(
            _line(
                side,
                [],
                "电气机械不新开列，不进四个发力指数",
                _check(published, False),
            )
        )
    if any(word in clause for word in FOOD):
        lines.append(
            _line(
                side,
                [("食品饮料", "000807")],
                "不改第二托",
                _check(published, False),
            )
        )
    if any(word in clause for word in OIL):
        needs_settlement = "结算" not in clause and "收盘" not in clause
        lines.append(
            _line(
                side,
                [("煤炭", "399998")],
                "不进托住",
                _check(published, needs_settlement),
            )
        )
    if any(word in clause for word in OMO):
        lines.append(_line("无方向", [], "不写进银行或电子", "不核板块"))
    if any(word in clause for word in BROAD):
        lines.append(_line("无方向", [], "制造业贷款不点名板块", "不核板块"))
    if any(word in clause for word in SERVICE) and not lines:
        lines.append(
            _line(
                _side(clause),
                [],
                "没有对应指数，不点名板块",
                _check(published, False),
            )
        )
    return lines


def direction_lines(text: str, published: str = "") -> list[dict]:
    """One line per sleeve the sentence actually names. Empty text returns none."""
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return []
    if any(word in compact for word in COMPANY):
        return [
            _line("个股", [], "只留在该公司，不外推行业", "不核板块"),
        ]
    clauses = [piece for piece in re.split(r"[。；;]", compact) if piece]
    lines: list[dict] = []
    for clause in clauses or [compact]:
        lines.extend(_clause_lines(clause, published))
    if lines:
        return lines
    side = _side(compact)
    if side == "无方向":
        return []
    return [
        _line(side, [], "对不上已有分组，不点名板块", _check(published, False)),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify one fact onto existing sleeves")
    parser.add_argument("--text", default="", help="The one-sentence fact")
    parser.add_argument("--at", default="", help="Beijing publish time, HH:MM decides the check day")
    args = parser.parse_args(argv)
    json.dump(direction_lines(args.text, args.at), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
