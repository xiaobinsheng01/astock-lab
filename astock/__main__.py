"""One desk entry. ``python -m astock <command>`` forwards to a calculator.

The modules stay runnable on their own (``python -m astock.close_inputs``).
This wrapper only names the session commands.
"""

from __future__ import annotations

import importlib
import sys

COMMANDS = {
    "close": "astock.close_inputs",
    "news": "astock.info_diff",
    "brief": "astock.intraday_brief",
    "screen": "astock.intraday_screen",
    "drive": "astock.sector_drive",
    "overseas": "astock.overseas_feed",
    "us": "astock.us_sectors",
    "direction": "astock.direction",
}


def _usage() -> str:
    lines = [
        "用法: python -m astock <命令> [参数]",
        "",
        "命令只出数，不改规则，不下单。",
        "  close     收盘输入、W6、修复、对冲托住   python -m astock.close_inputs",
        "  news      资料面本窗与缺口               python -m astock.info_diff",
        "  brief     上证落在四条路径的哪一段       python -m astock.intraday_brief",
        "  screen    站上 5 日和 10 日的主板名字    python -m astock.intraday_screen",
        "  drive     发力板块和发力个股             python -m astock.sector_drive",
        "  overseas  外围市场资讯候选               python -m astock.overseas_feed",
        "  us        美股行业 ETF 冷热              python -m astock.us_sectors",
        "  direction  资料面方向句                   python -m astock.direction",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(_usage())
        return 0
    name = argv[0]
    module_name = COMMANDS.get(name)
    if module_name is None:
        print(_usage(), file=sys.stderr)
        return 2
    module = importlib.import_module(module_name)
    sys.argv = [module_name, *argv[1:]]
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
