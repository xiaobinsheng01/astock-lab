#!/usr/bin/env python3
"""Window routing. No network."""

from __future__ import annotations

import unittest

from astock.close_inputs import CODES
from astock.route import format_plan, plan

FORBIDDEN = ("是否取数", "Buy", "Overweight", "Hold", "Underweight", "Sell")


class RouteTest(unittest.TestCase):
    def test_named_rounds_fetch_and_write_together(self) -> None:
        final = plan("2026-11-10 09:00", "终分")
        prelim = plan("2026-11-10 21:25", "初分")
        intraday = plan("2026-11-10 10:00", "盘中分析")
        for row in (final, prelim, intraday):
            text = format_plan(row)
            for word in FORBIDDEN:
                self.assertNotIn(word, text)
            self.assertEqual(row["窗口"], "本轮")
            self.assertTrue(row["跑"].startswith("news"))
            self.assertEqual(row["缺快照"], "未挂")
        self.assertIn("a50", final["跑"])
        self.assertNotIn("a50", prelim["跑"])
        self.assertIn("日期-终分.json", final["写"])
        self.assertIn("日期-对照.json", prelim["写"])
        self.assertIn("日期-盘中-1000.json", intraday["写"])

    def test_review_rounds_do_not_fetch(self) -> None:
        for ask in ("快评", "给这只写研报", "如何解决"):
            text = format_plan(plan("2026-11-10 10:00", ask))
            for word in FORBIDDEN:
                self.assertNotIn(word, text)
            self.assertIn("窗口: 分析", text)
            self.assertIn("跑: 无", text)

    def test_prelim_asks_for_positions_only(self) -> None:
        text = format_plan(plan("2026-11-10 21:25", "初分"))
        self.assertIn("持仓: 没提供就写待提供", text)
        self.assertNotIn("是否取数", text)

    def test_intraday_slot_follows_the_clock(self) -> None:
        self.assertEqual(plan("2026-11-10 10:05", "盘中")["轮次"], "盘中 10:00")
        self.assertEqual(plan("2026-11-10 12:50", "盘中")["轮次"], "盘中 12:50")
        self.assertEqual(plan("2026-11-10 14:10", "盘中")["轮次"], "盘中 14:00")

    def test_info_increment_only_advances_the_cursor(self) -> None:
        row = plan("2026-11-10 15:15", "跑资料面")
        self.assertEqual(row["窗口"], "取数")
        self.assertEqual(row["跑"], "news")
        self.assertEqual(row["缺快照"], "未挂")
        self.assertNotIn("五行", row["跑"])
        self.assertIn("五行", row["不打开"])

    def test_yaogu_row_has_no_score_word(self) -> None:
        text = format_plan(plan("2026-11-10 14:55", "妖股 14:55"))
        self.assertIn("轮次: 妖股", text)
        self.assertNotIn("行为分", text)
        for word in FORBIDDEN:
            self.assertNotIn(word, text)

    def test_quote_basket_includes_information_index(self) -> None:
        self.assertIn("sh000993", CODES)


if __name__ == "__main__":
    unittest.main()
