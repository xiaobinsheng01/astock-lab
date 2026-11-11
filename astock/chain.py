#!/usr/bin/env python3
"""One fetch chain for the data window. No score, no order, no 初分."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from astock.paths import LAKE

STEPS = (
    "news",
    "close",
    "drive",
    "brief",
    "screen",
    "a50",
    "cctv",
    "cfbond",
    "cninfo",
    "cash",
)

EXCLUDED = ("初分",)

MODULES = {
    "news": "astock.info_diff",
    "close": "astock.close_inputs",
    "drive": "astock.sector_drive",
    "brief": "astock.intraday_brief",
    "screen": "astock.intraday_screen",
    "a50": "astock.a50",
    "cctv": "astock.cctv_feed",
    "cfbond": "astock.cfbond_feed",
    "cninfo": "astock.cninfo_feed",
    "cash": "astock.cash_close",
}


def _module_runner(module: str, args: list[str] | None = None):
    def run() -> tuple[int, str]:
        proc = subprocess.run(
            [sys.executable, "-m", module, *(args or [])],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout

    return run


def default_runners(*, low: float | None = None, high: float | None = None) -> dict:
    """Call each fetch module. brief waits for both band edges."""
    runners = {
        name: _module_runner(MODULES[name])
        for name in STEPS
        if name != "brief"
    }
    if low is not None and high is not None:
        runners["brief"] = _module_runner(
            MODULES["brief"],
            ["--low", str(low), "--high", str(high)],
        )
    return runners


def _record(root: Path, name: str, status: str, text: str, code: int) -> dict:
    path = root / "hot" / "steps" / f"{name}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") or not text else text + "\n", encoding="utf-8")
    return {"name": name, "status": status, "code": code, "path": str(path)}


def run_chain(
    root: Path,
    runners: dict,
    *,
    low: float | None = None,
    high: float | None = None,
) -> dict:
    """Run STEPS in order and store each printout. 初分 is never called."""
    rows = []
    for name in STEPS:
        if name in EXCLUDED:
            continue
        if name == "brief" and (low is None or high is None):
            note = json.dumps({"status": "未跑", "text": "brief 缺低点或高点"}, ensure_ascii=False) + "\n"
            rows.append(_record(root, name, "未跑", note, 0))
            continue
        runner = runners.get(name)
        if runner is None:
            note = json.dumps({"status": "未挂", "text": f"{name} 没有命令"}, ensure_ascii=False) + "\n"
            rows.append(_record(root, name, "未挂", note, 0))
            continue
        try:
            code, text = runner()
        except Exception as exc:  # noqa: BLE001 — a dead step stays 未挂
            text = json.dumps({"status": "未挂", "error": type(exc).__name__}, ensure_ascii=False) + "\n"
            rows.append(_record(root, name, "未挂", text, 1))
            continue
        status = "已写" if str(text).strip() else "未挂"
        if not str(text).strip():
            text = json.dumps({"status": "未挂", "text": f"{name} 没有印出"}, ensure_ascii=False) + "\n"
        rows.append(_record(root, name, status, str(text), int(code)))
    payload = {"chain": list(STEPS), "excluded": list(EXCLUDED), "steps": rows}
    index = root / "hot" / "chain.json"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="取数链路。只印快照，不算初分，不下单。")
    parser.add_argument("--root", default="", help="资料湖目录，默认 runtime/lake")
    parser.add_argument("--low", type=float, default=None)
    parser.add_argument("--high", type=float, default=None)
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else LAKE
    payload = run_chain(root, default_runners(low=args.low, high=args.high), low=args.low, high=args.high)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
