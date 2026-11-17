#!/usr/bin/env python3
"""华宝双创50ETF for the data layer. Prices and daily bars, or a gap.

Code 588330, on-exchange name 双创50ETF华宝. Same source order as CSI 300.
It does not enter W1–W8, the repair day, or a cushion. No order.
"""

from __future__ import annotations

import argparse
import json
import sys

from astock.csi300 import DUAL50, _live_get, collect_for, store


def collect(get) -> dict:
    return collect_for(get, DUAL50)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="双创50ETF华宝现价和日K。缺价写缺口。不下单。")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写资料湖")
    args = parser.parse_args(argv)
    result = collect(_live_get)
    if not args.dry_run:
        result["written"] = store(result)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
