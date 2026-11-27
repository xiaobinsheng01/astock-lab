#!/usr/bin/env python3
"""结构化预测、结算和记分板。写死核对条件，收盘由脚本逐条判对错。

规则里说过：目标是下一次收盘能逐条核对，写不出核对条件的句子不算预测。所以
这里的一句话不是自然语言，而是一条带 `check` 的记录——`check` 说清用什么数据、
哪个方向算中。写不出 `check` 的句子在这里记不下来。

三层结构：

  预测（predict）：盘前写下的 claim，一条一个 `check`，落进 `runtime/lake/state/forecasts.jsonl`。
  结算（resolve）：收盘拿当天的行情、日线、行业表去逐条判 `hit` / `miss` / `unchecked`。
  记分板（scoreboard）：按名字汇总命中率，落进 `runtime/lake/state/scoreboard.json`。

三条硬规则：

  1. 结算只认数据，不认说法。判不出来写 `unchecked`，不写 miss。没数据不等于错。
  2. 结算过的不重算。`resolve` 只处理还没有 `resolution` 的记录，预测写下的那一刻
     不会被后来的行情改写。要改，先删掉那条记录。
  3. 记分板不改权重、不改硬门、不下单。规则原文：权重和硬门不因对错而改。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astock.paths import STATE_DIR

BEIJING = timezone(timedelta(hours=8))

FORECAST_FILE = STATE_DIR / "forecasts.jsonl"
SCOREBOARD_FILE = STATE_DIR / "scoreboard.json"

# 判出来的三种结果。`unchecked` 不算进命中率的分母。
HIT = "hit"
MISS = "miss"
UNCHECKED = "unchecked"
RESULTS = (HIT, MISS, UNCHECKED)

# 一条预测最多带几个检查项。多了就不像一句能核的话了。
MAX_CHECKS = 6

# 方向词。检查项只认这三个，别的写法在写下来的那一刻就报错。
UP = "up"
DOWN = "down"
FLAT = "flat"
DIRECTIONS = (UP, DOWN, FLAT)

# 支持的检查类型。写一条 check 必须落进这里的一种，否则 `predict` 直接拒收：
# 收下来却永远核不了的预测，比没写更糟。
KINDS = (
    "index_pct",       # 指数涨跌幅落在哪一侧
    "index_zone",      # 指数收盘落在四条路径的哪一段
    "sector_pct",      # 申万一级行业的等权涨跌幅落在哪一侧
    "sector_vs_index", # 行业涨跌幅是否强于上证至少多少个百分点
    "industry_pick",   # 行业两栏分类等于什么
    "quote_above",     # 某只票或指数收盘是否高于某个价位
    "breadth",         # 上涨家数占比是否达到阈值
)

ZONES = ("narrow_lower", "hard_upper", "above_hard", "below_hard")
PICKS = ("主线", "仅进攻", "仅防御", "无", "样本不足")


def beijing_now() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M")


def today() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------- 写入


def validate(record: dict) -> list[str]:
    """一条预测哪里不合法。返回空表才算写得出核对条件。

    这里故意严：宁可拒收，也不收下一条永远核不了的话。规则说「写不出核对条件
    的句子不算预测」，这一段就是那句话的执行。
    """
    problems = []
    if not str(record.get("name") or "").strip():
        problems.append("缺 name：这条预测算在谁头上")
    date = str(record.get("date") or "")
    if len(date) != 10 or not date[:4].isdigit():
        problems.append("date 必须是 YYYY-MM-DD")
    checks = record.get("checks")
    if not isinstance(checks, list) or not checks:
        problems.append("缺 checks：至少一条核对条件")
        return problems
    if len(checks) > MAX_CHECKS:
        problems.append(f"checks 最多 {MAX_CHECKS} 条")
    for index, check in enumerate(checks):
        where = f"checks[{index}]"
        kind = check.get("kind")
        if kind not in KINDS:
            problems.append(f"{where}.kind 不认识：{kind!r}，只能是 {', '.join(KINDS)}")
            continue
        if "want" not in check:
            problems.append(f"{where} 缺 want：不写想要什么，收不了盘")
            continue
        problem = _validate_check(kind, check, where)
        if problem:
            problems.append(problem)
    return problems


def _validate_check(kind: str, check: dict, where: str):
    want = check.get("want")
    if kind in ("index_pct", "sector_pct"):
        if want not in DIRECTIONS:
            return f"{where}.want 只能是 up/down/flat"
        if kind == "index_pct" and not check.get("code"):
            return f"{where} 缺 code"
        if kind == "sector_pct" and not check.get("sector"):
            return f"{where} 缺 sector"
        return None
    if kind == "index_zone":
        if want not in ZONES:
            return f"{where}.want 只能是 {', '.join(ZONES)}"
        return None
    if kind == "sector_vs_index":
        if want not in (True, False):
            return f"{where}.want 只能是 true/false"
        margin = check.get("margin_pp")
        if not isinstance(margin, (int, float)) or isinstance(margin, bool):
            return f"{where} 缺 margin_pp：强于上证几个百分点算中"
        if not check.get("sector"):
            return f"{where} 缺 sector"
        return None
    if kind == "industry_pick":
        if want not in PICKS:
            return f"{where}.want 只能是 {', '.join(PICKS)}"
        if not check.get("sector"):
            return f"{where} 缺 sector"
        return None
    if kind == "quote_above":
        if not isinstance(want, (int, float)) or isinstance(want, bool):
            return f"{where}.want 必须是价位数字"
        if not check.get("code"):
            return f"{where} 缺 code"
        return None
    if kind == "breadth":
        if not isinstance(want, (int, float)) or isinstance(want, bool):
            return f"{where}.want 必须是 0 到 1 的上涨家数占比"
        if not 0 <= want <= 1:
            return f"{where}.want 必须落在 0 到 1"
        return None
    return f"{where}.kind 不认识"


def write_forecast(record: dict, *, path: Path = FORECAST_FILE) -> dict:
    """收下一条预测。不合法直接抛 `ValueError`，不半截落盘。"""
    problems = validate(record)
    if problems:
        raise ValueError("；".join(problems))
    stored = {
        "date": record["date"],
        "name": str(record["name"]).strip(),
        "written_at": record.get("written_at") or beijing_now(),
        "checks": record["checks"],
        "note": str(record.get("note") or ""),
    }
    if "wave" in record:
        # 波浪只写文字，不进验证。存下来只为了复盘时能读到当时那句话，
        # 结算和记分板都不看这个字段。
        stored["wave"] = str(record["wave"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stored, ensure_ascii=False) + "\n")
    return stored


def read_forecasts(path: Path = FORECAST_FILE) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------- 结算


def judge_pct(pct, want: str) -> str:
    """涨跌幅落在哪一侧。缺数就是 `unchecked`，不当成 miss。"""
    if pct is None:
        return UNCHECKED
    if pct > 0:
        got = UP
    elif pct < 0:
        got = DOWN
    else:
        got = FLAT
    return HIT if got == want else MISS


def judge_zone(close, day_low, day_high, want: str) -> str:
    """收盘落在四条路径的哪一段，用 `session_path` 的同一套边界。"""
    if close is None or day_low is None or day_high is None:
        return UNCHECKED
    midpoint = (day_low + day_high) / 2.0
    if close < day_low:
        zone = "below_hard"
    elif close <= midpoint:
        zone = "narrow_lower"
    elif close <= day_high:
        zone = "hard_upper"
    else:
        zone = "above_hard"
    return HIT if zone == want else MISS


def judge_quote_above(close, level) -> str:
    if close is None or level is None:
        return UNCHECKED
    return HIT if close > level else MISS


def judge_sector_vs_index(sector_pct, index_pct, margin_pp, want: bool) -> str:
    """行业是否强于上证至少 `margin_pp` 个百分点。"""
    if sector_pct is None or index_pct is None:
        return UNCHECKED
    strong = (sector_pct - index_pct) >= float(margin_pp)
    return HIT if strong is want else MISS


def judge_pick(pick, want: str) -> str:
    if not pick:
        return UNCHECKED
    return HIT if pick == want else MISS


def judge_breadth(share, want) -> str:
    """上涨家数占比至少达到 `want` 算中。"""
    if share is None:
        return UNCHECKED
    return HIT if share >= float(want) else MISS


def resolve_record(record: dict, day: dict) -> dict:
    """把一条预测的每条 check 判一遍。

    `day` 是当天收盘的取数包，形如：

        {
          "date": "2026-11-26",
          "quotes": {"000001": {"px": .., "pct": .., "high": .., "low": ..}, ...},
          "prev":   {"000001": {"high": .., "low": ..}, ...},   # 上一交易日
          "sectors": {"有色金属": {"pct": 1.87, "pick": "仅进攻"}},
          "breadth": 0.42,   # 上涨家数占比
        }

    缺哪块就判 `unchecked`，不猜。返回新记录，不改原来的。
    """
    quotes = day.get("quotes") or {}
    prev = day.get("prev") or {}
    sectors = day.get("sectors") or {}
    results = []
    for check in record.get("checks") or []:
        kind = check.get("kind")
        want = check.get("want")
        if kind == "index_pct":
            row = quotes.get(check.get("code")) or {}
            outcome = judge_pct(row.get("pct"), want)
        elif kind == "index_zone":
            code = check.get("code") or "000001"
            row = quotes.get(code) or {}
            before = prev.get(code) or {}
            outcome = judge_zone(row.get("px"), before.get("low"), before.get("high"), want)
        elif kind == "sector_pct":
            row = sectors.get(check.get("sector")) or {}
            outcome = judge_pct(row.get("pct"), want)
        elif kind == "sector_vs_index":
            row = sectors.get(check.get("sector")) or {}
            index_pct = (quotes.get(check.get("index") or "000001") or {}).get("pct")
            outcome = judge_sector_vs_index(
                row.get("pct"), index_pct, check.get("margin_pp"), want
            )
        elif kind == "industry_pick":
            row = sectors.get(check.get("sector")) or {}
            outcome = judge_pick(row.get("pick"), want)
        elif kind == "quote_above":
            row = quotes.get(check.get("code")) or {}
            outcome = judge_quote_above(row.get("px"), want)
        elif kind == "breadth":
            outcome = judge_breadth(day.get("breadth"), want)
        else:
            outcome = UNCHECKED
        results.append({**check, "result": outcome})
    return {
        **record,
        "resolution": {
            "resolved_at": beijing_now(),
            "date": day.get("date") or record.get("date"),
            "results": results,
            "summary": summarize(results),
        },
    }


def summarize(results: list[dict]) -> dict:
    """一条预测的总结果。

    有一条 miss 就不是全中；全是 hit 才算中；其余全是 unchecked 就是未核。
    `partial` 单列：有些中、有些没中，复盘要看得见是哪条翻了。
    """
    hits = sum(1 for item in results if item.get("result") == HIT)
    misses = sum(1 for item in results if item.get("result") == MISS)
    unknown = sum(1 for item in results if item.get("result") == UNCHECKED)
    if misses == 0 and hits and unknown == 0:
        state = HIT
    elif misses and not hits:
        state = MISS
    elif not hits and unknown:
        state = UNCHECKED
    else:
        state = "partial"
    return {"hit": hits, "miss": misses, "unchecked": unknown, "state": state}


def resolve_all(day: dict, *, path: Path = FORECAST_FILE) -> dict:
    """结算所有还没结算、日期不晚于 `day['date']` 的记录。

    已经带 `resolution` 的原样留着：预测写下那一刻的话不能被后来的行情改写。
    一条记录连一条能判的都没有时留着不结算，等有数据再判，免得把「没取到数」
    写成终局。
    """
    target = str(day.get("date") or "")
    records = read_forecasts(path)
    updated = []
    resolved = 0
    for record in records:
        if record.get("resolution"):
            updated.append(record)
            continue
        if target and str(record.get("date") or "") > target:
            updated.append(record)
            continue
        done = resolve_record(record, day)
        if done["resolution"]["summary"]["state"] == UNCHECKED:
            updated.append(record)
            continue
        updated.append(done)
        resolved += 1
    _write_lines(path, updated)
    return {"resolved": resolved, "total": len(updated)}


def _write_lines(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in records)
    path.write_text(body + ("\n" if body else ""), encoding="utf-8")


# ---------------------------------------------------------------- 记分板


def scoreboard(records: list[dict]) -> dict:
    """按 `name` 汇总命中率。只算已结算的，`unchecked` 不进分母。

    这里只统计，不改权重、不改硬门、不下单。规则原文：权重和硬门不因对错而改。
    """
    per_name: dict[str, dict] = {}
    for record in records:
        resolution = record.get("resolution")
        if not resolution:
            continue
        results = resolution.get("results") or []
        name = record.get("name") or "未命名"
        row = per_name.setdefault(
            name, {"name": name, "hit": 0, "miss": 0, "unchecked": 0, "days": 0}
        )
        row["days"] += 1
        for item in results:
            outcome = item.get("result")
            if outcome in RESULTS:
                row[outcome] += 1
    for row in per_name.values():
        judged = row["hit"] + row["miss"]
        row["judged"] = judged
        row["rate"] = (row["hit"] / judged) if judged else None
    rows = sorted(
        per_name.values(),
        key=lambda item: (
            -(item["rate"] if item["rate"] is not None else -1),
            -item["judged"],
        ),
    )
    judged = sum(row["judged"] for row in rows)
    hits = sum(row["hit"] for row in rows)
    return {
        "updated_at": beijing_now(),
        "rows": rows,
        "total": {
            "judged": judged,
            "hit": hits,
            "rate": (hits / judged) if judged else None,
        },
    }


def write_scoreboard(records: list[dict], *, path: Path = SCOREBOARD_FILE) -> dict:
    board = scoreboard(records)
    _dump(path, board)
    return board


def format_scoreboard(board: dict) -> str:
    lines = ["名字\t已结算\t中\t未中\t未核\t命中率"]
    for row in board.get("rows") or []:
        rate = "未核" if row.get("rate") is None else f"{row['rate'] * 100:.0f}%"
        lines.append(
            f"{row['name']}\t{row['days']}\t{row['hit']}\t{row['miss']}\t"
            f"{row['unchecked']}\t{rate}"
        )
    total = board.get("total") or {}
    rate = "未核" if total.get("rate") is None else f"{total['rate'] * 100:.0f}%"
    lines.append(f"合计\t{total.get('judged', 0)}\t{total.get('hit', 0)}\t-\t-\t{rate}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="结构化预测、结算与记分板。不改权重，不下单。",
        epilog="核对条件写不出来的句子不收：`predict` 会当场拒收。",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("predict", help="收下一条预测，从 stdin 读 JSON")
    add.add_argument("--file", default="", help="从文件读，不给就读 stdin")

    run = sub.add_parser("resolve", help="结算还没结算的预测，从 stdin 读当天取数包")
    run.add_argument("--file", default="", help="从文件读，不给就读 stdin")

    sub.add_parser("scoreboard", help="按名字汇总命中率")

    args = parser.parse_args(argv)
    if args.cmd == "predict":
        raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"不是合法 JSON：{exc}", file=sys.stderr)
            return 2
        try:
            stored = write_forecast(record)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        json.dump(stored, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    if args.cmd == "resolve":
        raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
        try:
            day = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"不是合法 JSON：{exc}", file=sys.stderr)
            return 2
        print(json.dumps(resolve_all(day), ensure_ascii=False))
        return 0
    board = write_scoreboard(read_forecasts())
    print(format_scoreboard(board))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
