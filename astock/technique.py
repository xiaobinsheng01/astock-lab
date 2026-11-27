#!/usr/bin/env python3
"""技术面：量价四态、均线窗口、炒作周期的题材轮动。不打分，不下单。

三件事，各自独立：

1. 量价四态。用今天和昨天的成交量、收盘价，把一天分成量增价涨、量缩价涨、
   量增价跌、量缩价跌四格。这是「量能的大与小」落到当天的那一格。
2. 均线窗口。5/10/20/60 日收盘均值，以及收盘相对每条均线的距离。窗口不够
   就写「未核」，不拿短样本冒充。
3. 炒作周期。看概念板块里「仅进攻」占多少，判断资金在做接力还是做一日游。

波浪不在这里。`rules/02-rules.md` 写明波浪只写文字，不进脚本，不进验证。
本模块不生成、不统计、不打分任何浪级。
"""

from __future__ import annotations

import sys
from statistics import median

# 量能比较的容差，量和价分开。量平、价平各留 3%，与
# `rules/08-portrait.md` 的量价四态一节一致。个股用这一组容差。
VOL_FLAT = 0.03
PRICE_FLAT = 0.03

# 行业等权指数是几十只票的平均，单日振幅天然被抹平：实测 31 个行业的中位单日
# 涨跌约 0.9%，最大也只到 2.5%，用个股的 3% 会让整张表 30 个行业一起写「量价
# 持平」，四态就失去了区分力。行业按它自己的尺度留 1%。
INDUSTRY_PRICE_FLAT = 0.01

# 均线窗口，按规则取这几个。
WINDOWS = (5, 10, 20, 60)

# 炒作周期分类的分档。概念板块里「仅进攻」的占比越高，轮动越短促。
CYCLE_BANDS = (
    (0.65, "一日游居多"),
    (0.45, "短促轮动"),
    (0.25, "接力中"),
    (0.0, "主线为主"),
)


def volume_state(volume, prev_volume, close, prev_close, *, vol_flat: float = VOL_FLAT, price_flat: float = PRICE_FLAT) -> dict:
    """今天落在量价四态的哪一格。

    `volume` 和 `prev_volume` 是同一口径的成交量（手或股，不混用）。缺任一边
    都返回「未核」，不猜。价平、量平各留一条容差，避免把噪声当信号。
    """
    if not volume or not prev_volume or volume <= 0 or prev_volume <= 0:
        return {"state": "未核", "why": "缺成交量"}
    if close is None or prev_close is None or close <= 0 or prev_close <= 0:
        return {"state": "未核", "why": "缺收盘价"}
    vol_ratio = volume / prev_volume
    pct = close / prev_close - 1.0
    heavy = vol_ratio > 1.0 + vol_flat
    light = vol_ratio < 1.0 - vol_flat
    if heavy and pct > price_flat:
        state = "量增价涨"
    elif light and pct > price_flat:
        state = "量缩价涨"
    elif heavy and pct < -price_flat:
        state = "量增价跌"
    elif light and pct < -price_flat:
        state = "量缩价跌"
    else:
        state = "量价持平"
    return {"state": state, "vol_ratio": vol_ratio, "pct": pct * 100.0}


VOLUME_READS = {
    "量增价涨": "有资金主动买，趋势可延续；但要看位置，高位放量要防兑现。",
    "量缩价涨": "买盘不积极，涨得轻。没有新的量，持续性存疑。",
    "量增价跌": "有人在出，且出了量。高位是派发，低位是恐慌。",
    "量缩价跌": "卖压不大，跌得轻。多是无人接而非有人砸。",
    "量价持平": "量价都没走出容差，这一天不构成信号。",
}


def volume_read(state: str) -> str:
    """一格一句话。只描述，不变成买卖指令。"""
    return VOLUME_READS.get(state, "未核，不读。")


def averages(bars: list[dict], windows: tuple[int, ...] = WINDOWS) -> dict:
    """收盘均线和距离。窗口不够的写 `None`，不拿短样本凑。"""
    closes = [bar.get("close") for bar in bars]
    closes = [float(px) for px in closes if px is not None]
    out: dict[str, dict] = {}
    for window in windows:
        if len(closes) < window:
            out[f"ma{window}"] = {"ma": None, "dist": None, "state": "未核"}
            continue
        ma = sum(closes[-window:]) / float(window)
        dist = closes[-1] / ma - 1.0 if ma > 0 else None
        out[f"ma{window}"] = {"ma": ma, "dist": dist, "state": "已核"}
    return out


def above_all(bars: list[dict], windows: tuple[int, ...] = WINDOWS) -> dict:
    """收盘站上几条均线。缺窗口的那条不计入，也不当成站上。"""
    table = averages(bars, windows)
    checked = [key for key, row in table.items() if row["state"] == "已核"]
    above = [key for key in checked if (table[key]["dist"] or 0) > 0]
    return {
        "checked": len(checked),
        "above": len(above),
        "names": above,
        "state": "未核" if not checked else ("站上全部" if len(above) == len(checked) else f"站上 {len(above)}/{len(checked)}"),
    }


def cycle(concept_rows: list[dict]) -> dict:
    """从概念板块的两栏分类读炒作周期。只数「仅进攻」和「主线」。"""
    counted = {
        "主线": 0,
        "仅进攻": 0,
        "仅防御": 0,
        "无": 0,
        "样本不足": 0,
        "未核": 0,
    }
    for row in concept_rows:
        pick = row.get("pick") or "未核"
        counted[pick] = counted.get(pick, 0) + 1
    usable = counted["主线"] + counted["仅进攻"] + counted["仅防御"] + counted["无"]
    if usable == 0:
        return {"state": "未核", "counts": counted, "share": None, "read": "概念板块没有可用的样本。"}
    share = counted["仅进攻"] / float(usable)
    label = CYCLE_BANDS[-1][1]
    for line, name in CYCLE_BANDS:
        if share >= line:
            label = name
            break
    return {
        "state": label,
        "counts": counted,
        "share": share,
        "read": _cycle_read(label, counted),
    }


def _cycle_read(label: str, counted: dict) -> str:
    if label == "一日游居多":
        return "概念里「仅进攻」占大多数，资金不留隔夜，接力靠不住。追高就是接最后一棒。"
    if label == "短促轮动":
        return "进攻型概念偏多，故事换得快。只有当天第一个起来的那个能看。"
    if label == "接力中":
        return "有主线也有进攻，资金在做接力。看主线能不能连着两天被选中。"
    if counted["主线"] > 0:
        return "主线型概念占多数，故事被反复接力。这是能持续一段的题材环境。"
    return "概念板块既没有主线也没有进攻，题材没有方向。"


def hot_concepts(concept_rows: list[dict], top: int = 5) -> list[dict]:
    """进攻最强的前几个概念。按上涨日中位排，不按今天涨幅排。"""
    rows = [row for row in concept_rows if row.get("up", {}).get("median") is not None]
    rows.sort(key=lambda row: row["up"]["median"], reverse=True)
    return rows[:top]


def thematic(bars: list[dict], *, window: int = 60) -> dict:
    """题材的技术位置：相对 `window` 日高点的位置，以及是否创窗口新高。"""
    closes = [float(bar["close"]) for bar in bars if bar.get("close") is not None]
    if len(closes) < 5:
        return {"state": "未核", "why": "日线不足 5 根"}
    sample = closes[-window:]
    high = max(sample)
    last = sample[-1]
    return {
        "state": "已核",
        "from_high": last / high - 1.0 if high > 0 else None,
        "new_high": last >= high,
        "median_gain": median([b / a - 1.0 for a, b in zip(sample, sample[1:])]) if len(sample) > 1 else None,
        "bars": len(sample),
    }


def frame(code: str, bars: list[dict], *, price_flat: float = PRICE_FLAT, vol_flat: float = VOL_FLAT) -> dict:
    """一只票的技术面四格：量价四态、均线、站上几条、窗口位置。

    `bars` 按日期升序，最后一根是当日。缺前一日就写未核，不拿当日跟自己比。
    行业等权指数传 `INDUSTRY_PRICE_FLAT`：几十只票平均之后单日振幅被抹平，
    个股的 3% 容差会把整张行业表压成清一色「量价持平」。
    """
    if not bars:
        return {"code": code, "state": "未核", "why": "没有日线"}
    today_bar = bars[-1]
    prev_bar = bars[-2] if len(bars) > 1 else {}
    volume = volume_state(
        today_bar.get("volume"),
        prev_bar.get("volume"),
        today_bar.get("close"),
        prev_bar.get("close"),
        vol_flat=vol_flat,
        price_flat=price_flat,
    )
    return {
        "code": code,
        "state": "已核",
        "date": today_bar.get("date"),
        "volume": volume,
        "read": volume_read(volume["state"]),
        "averages": averages(bars),
        "above": above_all(bars),
        "thematic": thematic(bars),
    }


def format_frame(frames: list[dict]) -> str:
    """一张票一行。四态和站上几条并排，未核写未核，不写 0。"""
    lines = ["代码\t日期\t量价\t量比\t涨跌\t站上均线\t离窗口高点"]
    for item in frames:
        if item.get("state") != "已核":
            lines.append(f"{item['code']}\t未核\t未核\t未核\t未核\t未核\t{item.get('why', '')}")
            continue
        volume = item["volume"]
        ratio = "未核" if volume.get("vol_ratio") is None else f"{volume['vol_ratio']:.2f}"
        pct = "未核" if volume.get("pct") is None else f"{volume['pct']:+.2f}%"
        high = item["thematic"].get("from_high")
        gap = "未核" if high is None else f"{high * 100:+.1f}%"
        lines.append(
            f"{item['code']}\t{item['date']}\t{volume['state']}\t{ratio}\t{pct}\t"
            f"{item['above']['state']}\t{gap}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json as _json

    from astock.lake import read_bars
    from astock.paths import LAKE

    parser = argparse.ArgumentParser(
        description="量价四态与均线窗口。不打分，不下单。",
        epilog="本地没有成交量的旧日线会被标未核；行业走 --industry，成分股等权现算。",
    )
    parser.add_argument("codes", nargs="*", help="股票或指数代码，读本地日线")
    parser.add_argument("--industry", action="append", default=[], help="申万一级行业名，可重复")
    parser.add_argument("--members", type=int, default=20, help="行业等权取多少只成分股")
    parser.add_argument("--days", type=int, default=120, help="取多少根日线")
    parser.add_argument("--json", action="store_true", help="印 JSON")
    args = parser.parse_args(argv)

    frames = [frame(code, read_bars(LAKE, code)) for code in args.codes]
    if args.industry:
        from astock.industry import industry_frame

        for name in args.industry:
            bars = industry_frame(name, count=args.days, limit=args.members)
            frames.append(frame(name, bars, price_flat=INDUSTRY_PRICE_FLAT))

    if args.json:
        _json.dump(frames, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    elif frames:
        print(format_frame(frames))
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
