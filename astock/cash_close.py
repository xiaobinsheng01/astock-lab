#!/usr/bin/env python3
"""9:00 cash prices. One missing price is a gap. No score, no order."""

from __future__ import annotations

import argparse
import json
import sys

NAMES = ("美股现金", "美债", "原油", "沪铜", "美元")


def assess_one(name: str, price, previous, clock: str) -> dict:
    if name not in NAMES:
        raise ValueError(f"不在 9:00 现金价名单里: {name}")
    if price in (None, "") or previous in (None, "") or not clock:
        return {"name": name, "status": "缺口", "text": f"{name} 缺收盘价"}
    return {
        "name": name,
        "status": "已核",
        "price": float(price),
        "prev": float(previous),
        "clock": clock,
    }


def assess_all(rows: list[dict]) -> dict:
    if not rows:
        return {"status": "未挂", "items": []}
    items = []
    for row in rows:
        try:
            items.append(assess_one(row.get("name", ""), row.get("price"), row.get("prev"), row.get("clock") or ""))
        except ValueError as exc:
            items.append({"name": row.get("name", ""), "status": "未挂", "text": str(exc)})
    return {"status": "已列", "items": items}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="9:00 现金价。缺价格写缺口。不下单。")
    parser.add_argument("--json", default="", help="[{name, price, prev, clock}] 文件")
    args = parser.parse_args(argv)
    if not args.json:
        result = {"status": "未挂", "items": [], "text": "未提供收盘价"}
    else:
        try:
            rows = json.loads(open(args.json, encoding="utf-8").read())
            result = assess_all(rows)
        except (OSError, json.JSONDecodeError, ValueError):
            result = {"status": "未挂", "items": []}
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
