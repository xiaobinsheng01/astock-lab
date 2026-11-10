#!/usr/bin/env python3
"""Window routing. No network."""

from __future__ import annotations

import unittest

from astock.close_inputs import CODES
from astock.route import format_plan, plan

FORBIDDEN = ("是否取数", "Buy", "Overweight", "Hold", "Underweight", "Sell")


class RouteTest(unittest.TestCase):
    def test_analysis_does_not_ask_to_fetch(self) -> None:
        for ask in ("终分", "初分", "盘中分析", "快评", "给这只写研报"):
            text = format_plan(plan("2026-11-10 10:00", ask))
            for word in FORBIDDEN:
                self.assertNotIn(word, text)
            self.assertIn("窗口: 分析", text)
            self.assertNotIn("跑: news", text)

    def test_final_reads_snapshot_and_stops_when_missing(self) -> None:
        row = plan("2026-11-10 09:00", "终分")
        self.assertEqual(row["窗口"], "分析")
        self.assertEqual(row["轮次"], "终分")
        self.assertEqual(row["跑"], "无")
        self.assertEqual(row["缺快照"], "未跑")

    def test_prelim_asks_for_positions_only(self) -> None:
        text = format_plan(plan("2026-11-10 21:25", "初分"))
        self.assertIn("持仓: 没提供就写待提供", text)
        self.assertNotIn("是否取数", text)

    def test_intraday_slot_follows_the_clock(self) -> None:
        self.assertEqual(plan("2026-11-10 10:05", "盘中")["轮次"], "盘中 10:00")
        self.assertEqual(plan("2026-11-10 12:50", "盘中")["轮次"], "盘中 12:50")
        self.assertEqual(plan("2026-11-10 14:10", "盘中")["轮次"], "盘中 14:00")

    def test_data_window_is_the_only_fetcher(self) -> None:
        row = plan("2026-11-10 15:15", "跑资料面")
        self.assertEqual(row["窗口"], "取数")
        self.assertIn("info_diff", row["跑"])
        self.assertIn("intraday_brief", row["跑"])
        self.assertIn("intraday_screen", row["跑"])
        self.assertNotIn("news", row["跑"])
        self.assertEqual(row["缺快照"], "未挂")
        self.assertNotIn("五行", row["跑"])

    def test_fetch_ask_names_the_three_scripts(self) -> None:
        row = plan("2026-11-10 23:45", "取数")
        self.assertEqual(row["窗口"], "取数")
        self.assertEqual(
            row["跑"],
            "info_diff、intraday_brief、intraday_screen、close_inputs、sector_drive、a50、cctv、cfbond、cninfo、cash",
        )

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
