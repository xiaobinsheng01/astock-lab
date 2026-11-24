#!/usr/bin/env python3
"""Window routing. No network."""

from __future__ import annotations

import unittest

from astock.close_inputs import CODES
from astock.route import format_plan, plan

FORBIDDEN = ("是否取数", "Buy", "Overweight", "Hold", "Underweight", "Sell")


class RouteTest(unittest.TestCase):
    def test_analysis_fetches_without_asking(self) -> None:
        for ask in ("终分", "初分", "盘中分析", "快评", "给这只写研报"):
            text = format_plan(plan("2026-11-10 10:00", ask))
            for word in FORBIDDEN:
                self.assertNotIn(word, text)
            self.assertIn("窗口: 分析", text)
            self.assertNotIn("补抓", text)
            self.assertNotIn("跑: 无", text)

    def test_final_runs_the_close_and_the_news_desk(self) -> None:
        row = plan("2026-11-10 09:00", "终分")
        self.assertEqual(row["窗口"], "分析")
        self.assertEqual(row["轮次"], "终分")
        self.assertEqual(row["跑"], "close、drive、news、desk")
        self.assertEqual(row["缺快照"], "先跑")

    def test_prelim_asks_for_positions_only(self) -> None:
        text = format_plan(plan("2026-11-10 21:25", "初分"))
        self.assertIn("持仓: 没提供就写待提供", text)
        self.assertNotIn("是否取数", text)

    def test_preview_and_intraday_read_the_operation_order(self) -> None:
        intraday = plan("2026-11-10 10:05", "盘中")
        preview = plan("2026-11-10 08:30", "大盘预判")
        self.assertIn("操作令", intraday["读"])
        self.assertEqual(preview["轮次"], "预判")
        self.assertIn("操作令", preview["读"])
        self.assertEqual(preview["跑"], "news、desk、brief、screen")
        self.assertEqual(intraday["跑"], "news、desk、brief、screen")

    def test_intraday_slot_follows_the_clock(self) -> None:
        self.assertEqual(plan("2026-11-10 10:05", "盘中")["轮次"], "盘中 10:00")
        self.assertEqual(plan("2026-11-10 12:50", "盘中")["轮次"], "盘中 12:50")
        self.assertEqual(plan("2026-11-10 14:10", "盘中")["轮次"], "盘中 14:00")

    def test_data_window_is_the_only_fetcher(self) -> None:
        row = plan("2026-11-10 15:15", "跑资料面")
        self.assertEqual(row["窗口"], "取数")
        self.assertIn("news", row["跑"])
        self.assertIn("desk", row["跑"])
        self.assertIn("csi300", row["跑"])
        self.assertIn("dual50", row["跑"])
        self.assertEqual(row["缺快照"], "未挂")
        self.assertNotIn("五行", row["跑"])

    def test_news_summary_is_its_own_data_window(self) -> None:
        row = plan("2026-11-24 21:30", "总结市场资讯")
        self.assertEqual(row["窗口"], "取数")
        self.assertEqual(row["轮次"], "市场资讯")
        self.assertEqual(row["跑"], "desk")
        self.assertEqual(row["读"], "runtime/lake/hot/news/2026-11-24.md")
        self.assertIn("原文", row["不打开"])
        self.assertNotIn("五行", row["跑"])

    def test_intraday_fetches_the_news_desk(self) -> None:
        row = plan("2026-11-10 10:05", "盘中资讯")
        self.assertEqual(row["窗口"], "分析")
        self.assertIn("市场资讯", row["读"])
        self.assertIn("desk", row["跑"])
        self.assertEqual(row["缺快照"], "先跑")

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
