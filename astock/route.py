#!/usr/bin/env python3
"""Print which window this turn uses. No fetch, no score, no order.

The analysis window reads snapshots that the data window already stored.
It does not ask whether to fetch, and it does not open the article text.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime


def _clock(at: str) -> datetime:
    text = at.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法识别的北京时间: {at}")


def _slot(at: datetime, ask: str) -> str:
    for label in ("14:00", "12:50", "10:00"):
        if label in ask:
            return label
    minutes = at.hour * 60 + at.minute
    if minutes >= 14 * 60:
        return "14:00"
    if minutes >= 12 * 60 + 50:
        return "12:50"
    return "10:00"


def plan(at: str, ask: str) -> dict:
    """Return the route row for one utterance. `at` is Beijing time."""
    clock = _clock(at)
    text = ask.strip()
    stamp = clock.strftime("%Y-%m-%d %H:%M")
    row = {
        "窗口": "分析",
        "轮次": "",
        "北京时间": stamp,
        "读": "",
        "跑": "无",
        "缺快照": "未跑",
        "不打开": "原文、总结模型、补抓",
        "持仓": "",
    }
    if any(word in text for word in ("研报", "多空", "值不值得")):
        row["轮次"] = "研报"
        row["读"] = "收盘命令已经印出的行"
        row["缺快照"] = "无"
        row["不打开"] = "原文、总结模型、补抓、新采集"
        return row
    if any(word in text for word in ("妖股", "盘前五只", "封板", "14:55")):
        row["轮次"] = "妖股"
        row["读"] = "当日开高低收和量"
        row["缺快照"] = "未跑"
        row["不打开"] = "原文、总结模型、补抓、资料面、主仓重算"
        return row
    if "快评" in text or "现在几点" in text:
        row["轮次"] = "快评"
        row["读"] = "最近一份终分或初分"
        row["跑"] = "无"
        row["缺快照"] = "未跑"
        row["不打开"] = "原文、总结模型、补抓、三支全扫"
        return row
    if "终分" in text:
        row["轮次"] = "终分"
        row["读"] = "硬门、终分、预测、发力、缠论、热层快照"
        return row
    if "初分" in text:
        row["轮次"] = "初分"
        row["读"] = "硬门、初分、预测、今日关注、缠论、热层快照"
        row["持仓"] = "没提供就写待提供"
        return row
    if "盘中" in text:
        row["轮次"] = f"盘中 {_slot(clock, text)}"
        row["读"] = "硬门、盘中分析、持仓、路径、热层快照"
        return row
    if any(word in text for word in ("取数", "资料面", "取行情", "补缺口")):
        row["窗口"] = "取数"
        row["轮次"] = "资料面"
        row["读"] = "热层写入位置"
        row["跑"] = "news、close、drive、brief、screen、a50、cctv、cfbond、cninfo、cash"
        row["缺快照"] = "未挂"
        row["不打开"] = "五行、主仓重算、妖股分档"
        row["持仓"] = ""
        return row
    row["轮次"] = "未识别"
    row["读"] = "无"
    row["缺快照"] = "未跑"
    return row


def format_plan(row: dict) -> str:
    lines = [
        f"窗口: {row['窗口']}",
        f"轮次: {row['轮次']}",
        f"北京时间: {row['北京时间']}",
        f"读: {row['读']}",
        f"跑: {row['跑']}",
        f"缺快照: {row['缺快照']}",
        f"不打开: {row['不打开']}",
    ]
    if row["持仓"]:
        lines.append(f"持仓: {row['持仓']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打印这一轮的窗口。不取数，不下单。")
    parser.add_argument("--at", required=True, help="北京时间，例如 2026-11-10 10:00")
    parser.add_argument("--ask", required=True, help="用户原话")
    args = parser.parse_args(argv)
    try:
        row = plan(args.at, args.ask)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(format_plan(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
