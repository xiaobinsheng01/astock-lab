#!/usr/bin/env python3
"""Close classification and the pre-market five. No network."""

from __future__ import annotations

import unittest

from astock.yaogu import SEED, classify, orders_allowed, shape_of, top5


def row(**overrides):
    base = {
        "code": "601188",
        "name": "龙江交通",
        "board": 2,
        "open": 4.09,
        "high": 4.19,
        "low": 4.00,
        "close": 4.19,
        "prev_close": 3.81,
        "volume": 41,
        "prev_volume": 100,
        "first_close": 3.81,
    }
    base.update(overrides)
    return base


class ShapeTest(unittest.TestCase):
    def test_one_word_and_turnover(self) -> None:
        self.assertEqual(shape_of(2.55, 2.55, 2.55, 2.55, 2.32), "一字")
        self.assertEqual(shape_of(4.09, 4.19, 4.00, 4.19, 3.81), "换手")
        self.assertEqual(shape_of(5.51, 5.51, 5.25, 5.51, 5.01), "T字")


class TierTest(unittest.TestCase):
    def test_nov9_sleeve(self) -> None:
        self.assertEqual(classify(row())["tier"], "隔夜")
        held = classify(row(
            code="002310", name="东方新能", open=2.55, high=2.55, low=2.55, close=2.55,
            prev_close=2.32, volume=66, prev_volume=100, first_close=2.32,
        ))
        self.assertEqual(held["tier"], "持仓")
        self.assertEqual(classify(row(volume=178, prev_volume=100))["tier"], "观察")
        self.assertEqual(classify(row(volume=220, prev_volume=100))["tier"], "否决")
        self.assertEqual(classify(row(volume=130, prev_volume=100))["tier"], "观察")

    def test_pool_edges(self) -> None:
        self.assertEqual(classify(row(board=1, first_close=9.99, volume=50))["tier"], "观察")
        self.assertEqual(classify(row(first_close=10))["tier"], "池外")
        self.assertEqual(classify(row(code="300001", name="创业板样本"))["tier"], "池外")
        self.assertEqual(classify(row(name="*ST样例"))["tier"], "池外")
        self.assertEqual(classify(row(board=4, open=4.19, high=4.19, low=4.19, close=4.19))["tier"], "观察")
        self.assertEqual(classify(row(board=3, volume=50))["tier"], "隔夜")
        blocked = classify(row(code="002081", name="金螳螂"))
        self.assertEqual(blocked["tier"], "池外")


class Top5Test(unittest.TestCase):
    def test_order_and_no_watch_fill(self) -> None:
        rows = [
            row(),
            row(code="600327", name="大东方", open=5.31, high=5.40, low=5.11, close=5.40,
                prev_close=4.91, volume=95, prev_volume=100, first_close=4.91),
            row(code="603366", name="日出东方", board=2, open=9.89, high=9.89, low=9.89, close=9.89,
                prev_close=8.99, volume=10, prev_volume=100, first_close=8.99),
            row(code="002310", name="东方新能", open=2.55, high=2.55, low=2.55, close=2.55,
                prev_close=2.32, volume=66, prev_volume=100, first_close=2.32),
            row(code="002037", name="保利联合", board=1, open=7.23, high=7.23, low=7.23, close=7.23,
                prev_close=6.57, volume=68, prev_volume=100, first_close=7.23),
            row(code="000525", name="红太阳", open=5.14, high=5.52, low=5.08, close=5.52,
                prev_close=5.02, volume=178, prev_volume=100, first_close=5.02),
        ]
        codes = [item["code"] for item in top5(rows)]
        self.assertEqual(codes, ["601188", "600327", "603366", "002310", "002037"])

    def test_seed_size(self) -> None:
        self.assertEqual(len(SEED), 23)
        self.assertEqual(len({row["code"] for row in SEED}), 23)


class WindowTest(unittest.TestCase):
    def test_orders_follow_the_window(self) -> None:
        self.assertFalse(orders_allowed("2026-11-10"))
        self.assertTrue(orders_allowed("2026-12-01"))
        self.assertTrue(orders_allowed("2027-02-05"))
        self.assertFalse(orders_allowed("2027-02-06"))


if __name__ == "__main__":
    unittest.main()
