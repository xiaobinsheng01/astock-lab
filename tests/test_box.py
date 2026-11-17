#!/usr/bin/env python3
"""Shanghai box. No network."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from astock.box import (
    EM_KLINE_URL,
    IFZQ_URL,
    NEED,
    base_cap,
    collect,
    completed_bars,
    compute,
    decide,
    store,
)


def _rows(n: int = 70, close: float = 100.0, high: float = 101.0, low: float = 99.0) -> list[dict]:
    start = datetime(2026, 1, 5)
    rows = []
    for offset in range(n):
        day = (start + timedelta(days=offset)).date().isoformat()
        rows.append({"date": day, "open": close, "close": close, "high": high, "low": low})
    return rows


def _stamp(index: int) -> str:
    return (datetime(2026, 1, 5) + timedelta(days=index)).date().isoformat()


def _bull() -> list[dict]:
    rows = _rows()
    for index in range(50, 70):
        rows[index]["close"] = 112.0
        rows[index]["high"] = 112.5
        rows[index]["low"] = 111.0
    rows[40]["high"] = 108.0
    rows[60]["low"] = 90.0
    return rows


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 17, hour, minute)


class DecideTest(unittest.TestCase):
    def test_exact_slope_and_the_average_gate(self) -> None:
        self.assertEqual(decide(120, 120, 110, 90, 0.003, 100), "震荡")
        self.assertEqual(decide(120, 120, 110, 90, 0.0031, 100), "多头")
        self.assertEqual(decide(100, 100, 90, 80, 0.01, 100), "多头")
        self.assertEqual(decide(100, 100, 90, 80, 0.01, 110), "震荡")
        self.assertEqual(decide(120, 100, 110, 90, 0.01, 100), "震荡")
        self.assertEqual(decide(80, 80, 110, 90, -0.003, 100), "震荡")
        self.assertEqual(decide(80, 80, 110, 90, -0.0031, 100), "空头")
        self.assertEqual(base_cap("多头", 120, 100), "80%")
        self.assertEqual(base_cap("震荡", 100, 100), "60%")
        self.assertEqual(base_cap("震荡", 90, 100), "30%")
        self.assertEqual(base_cap("空头", 120, 100), "30%")


class ComputeTest(unittest.TestCase):
    def test_bull_uses_the_latest_swing_inside_the_window(self) -> None:
        rows = _bull()
        rows[10]["high"] = 500.0
        rows[68]["high"] = 999.0
        packet = compute(rows, _at(9, 23), "fixture", [])
        self.assertEqual(packet["状态"], "已核")
        self.assertEqual(packet["箱体"], "有效")
        self.assertEqual(packet["压力价"], 108.0)
        self.assertEqual(packet["压力日"], _stamp(40))
        self.assertEqual(packet["支撑价"], 90.0)
        self.assertEqual(packet["支撑日"], _stamp(60))
        self.assertTrue(packet["宽箱"])
        self.assertEqual(packet["20日均线"], 112.0)
        self.assertEqual(packet["五日前列20日均线"], 109.0)
        self.assertEqual(packet["60日均线"], 104.0)
        self.assertGreater(packet["斜率"], 0.003)
        self.assertEqual(packet["标签"], "多头")
        self.assertEqual(packet["标签来源"], "当日")
        self.assertEqual(packet["基础总上限"], "80%")
        self.assertEqual(packet["收盘相对60日"], "不低于")
        self.assertIn("不进权重", packet["事实"])
        self.assertIn("不下单", packet["事实"])
        self.assertNotIn(_stamp(10), [item["日期"] for item in packet["摆动高点"]])
        self.assertNotIn(_stamp(68), [item["日期"] for item in packet["摆动高点"]])

    def test_bear_and_flat_and_exact_width(self) -> None:
        bear = _rows()
        for index in range(50, 70):
            bear[index]["close"] = 80.0
            bear[index]["high"] = 101.0
            bear[index]["low"] = 90.0
        bear[40]["high"] = 110.0
        bear[60]["low"] = 85.0
        packet = compute(bear, _at(9, 23), "fixture", [])
        self.assertEqual(packet["标签"], "空头")
        self.assertEqual(packet["基础总上限"], "30%")
        self.assertEqual(packet["收盘相对60日"], "低于")
        self.assertEqual(packet["60日均线"], 93.3333)

        flat = _rows(close=101.0, high=102.0, low=101.0)
        flat[40]["high"] = 108.0
        flat[60]["low"] = 100.0
        exact = compute(flat, _at(9, 23), "fixture", [])
        self.assertEqual(exact["标签"], "震荡")
        self.assertEqual(exact["基础总上限"], "60%")
        self.assertEqual(exact["箱宽"], 0.08)
        self.assertTrue(exact["宽箱"])
        flat[40]["high"] = 107.99
        narrow = compute(flat, _at(9, 23), "fixture", [])
        self.assertFalse(narrow["宽箱"])

    def test_no_swing_is_invalid_and_today_waits_for_the_close(self) -> None:
        flat = compute(_rows(), _at(9, 23), "fixture", [])
        self.assertEqual(flat["状态"], "无效")
        self.assertIn("摆动高点", flat["原因"])
        self.assertIn("摆动低点", flat["原因"])

        rows = _bull()
        today = dict(rows[-1])
        today["date"] = "2026-11-17"
        today["high"] = 999.0
        morning = completed_bars(rows + [today], _at(9, 23))
        self.assertEqual(morning[-1]["date"], rows[-1]["date"])
        self.assertEqual(len(morning), 70)
        closed = completed_bars(rows + [today], _at(15, 0))
        self.assertEqual(closed[-1]["date"], "2026-11-17")
        self.assertEqual(len(closed), 71)


class StoreTest(unittest.TestCase):
    def test_invalid_box_keeps_the_previous_label_and_a_short_fetch_does_not(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = compute(_bull(), _at(9, 23), "fixture", [])
            store(good, root)
            saved = json.loads((root / "hot" / "snapshots" / "箱体.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["标签"], "多头")
            self.assertNotIn("日线", saved)
            bars = json.loads((root / "bars" / "000001.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(bars), NEED)
            self.assertIn("high", bars[-1])
            self.assertIn("low", bars[-1])

            invalid = compute(_rows(), _at(9, 23), "fixture", [])
            store(invalid, root)
            carried = json.loads((root / "hot" / "snapshots" / "箱体.json").read_text(encoding="utf-8"))
            self.assertEqual(carried["状态"], "无效")
            self.assertEqual(carried["标签"], "多头")
            self.assertEqual(carried["标签来源"], "沿用上一交易日")
            self.assertEqual(carried["基础总上限"], "80%")

            short = {"状态": "未够", "根数": 12, "代码": "000001", "名称": "上证指数", "权重": "不进W1–W8"}
            kept = store(short, root)
            self.assertEqual(kept["snapshot"], "保留上一份")
            still = json.loads((root / "hot" / "snapshots" / "箱体.json").read_text(encoding="utf-8"))
            self.assertEqual(still["标签"], "多头")
            self.assertEqual(len(json.loads((root / "bars" / "000001.json").read_text(encoding="utf-8"))), 70)


def _ifzq(rows: list[dict]) -> str:
    payload = {"data": {"sh000001": {"day": [[row["date"], "1", str(row["close"]), str(row["high"]), str(row["low"])] for row in rows]}}}
    return json.dumps(payload)


def _em(rows: list[dict]) -> str:
    lines = [f"{row['date']},1,{row['close']},{row['high']},{row['low']},1" for row in rows]
    return json.dumps({"data": {"klines": lines}})


class FetchTest(unittest.TestCase):
    def test_a_long_tencent_series_is_not_replaced(self) -> None:
        rows = _bull()
        called = []

        def get(url: str) -> str:
            called.append(url)
            if url == IFZQ_URL:
                return _ifzq(rows)
            if url == EM_KLINE_URL:
                raise AssertionError(url)
            raise OSError(url)

        packet = collect(get, _at(9, 23))
        self.assertEqual(packet["状态"], "已核")
        self.assertEqual(packet["收"], 112.0)
        self.assertEqual(packet["来源"], "web.ifzq.gtimg.cn")
        self.assertNotIn(EM_KLINE_URL, called)

    def test_a_short_tencent_series_gives_way_to_the_next_long_one(self) -> None:
        def get(url: str) -> str:
            if url == IFZQ_URL:
                return _ifzq(_bull()[:12])
            if url == EM_KLINE_URL:
                shifted = _bull()
                shifted[-1]["close"] = 112.0
                return _em(shifted)
            raise OSError(url)

        packet = collect(get, _at(9, 23))
        self.assertEqual(packet["状态"], "已核")
        self.assertEqual(packet["来源"], "push2his.eastmoney.com")
        self.assertEqual(packet["根数"], 70)

    def test_every_host_down_is_a_gap(self) -> None:
        def get(url: str) -> str:
            raise OSError(url)

        packet = collect(get, _at(9, 23))
        self.assertEqual(packet["状态"], "未挂")
        self.assertIn("未挂", packet["事实"])


if __name__ == "__main__":
    unittest.main()
