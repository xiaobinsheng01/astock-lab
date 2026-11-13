#!/usr/bin/env python3
"""Window routing. No network."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from astock.close_inputs import CODES
from astock.route import apply_empty_stop, format_plan, plan

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
        self.assertIn("news", row["跑"])
        self.assertEqual(row["缺快照"], "未挂")
        self.assertNotIn("五行", row["跑"])

    def test_yaogu_row_has_no_score_word(self) -> None:
        text = format_plan(plan("2026-11-10 14:55", "妖股 14:55"))
        self.assertIn("轮次: 妖股", text)
        self.assertNotIn("行为分", text)
        for word in FORBIDDEN:
            self.assertNotIn(word, text)

    def test_quote_basket_includes_information_index(self) -> None:
        self.assertIn("sh000993", CODES)

    def test_broad_market_stays_in_the_analysis_window(self) -> None:
        row = plan("2026-11-11 00:01", "大盘分析")
        self.assertEqual(row["窗口"], "分析")
        self.assertEqual(row["轮次"], "大盘")
        self.assertEqual(row["跑"], "无")
        self.assertNotIn("停写", row)

    def test_empty_desk_stops_before_the_path(self) -> None:
        root = Path("/tmp/astock-empty-desk-missing")
        for ask in ("大盘分析", "预判", "盘中"):
            row = apply_empty_stop(plan("2026-11-11 00:01", ask), root)
            text = format_plan(row)
            self.assertEqual(row["停写"], "是")
            self.assertEqual(row["读"], "无")
            self.assertIn(
                "原因: info_diff、intraday_brief、intraday_screen 未跑，热层快照未挂，资料面记录未挂",
                text,
            )
            self.assertIn("操作: 停写。不补抓。不问要不要取数。", text)
            for word in FORBIDDEN:
                self.assertNotIn(word, text)

    def test_empty_stop_waits_for_both_stores_to_be_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "runtime" / "info-ledger.md"
            ledger.parent.mkdir(parents=True)
            ledger.write_text("已挂\n", encoding="utf-8")
            self.assertNotIn("停写", apply_empty_stop(plan("2026-11-11 00:01", "大盘分析"), root))
            ledger.unlink()
            quote = root / "runtime" / "lake" / "hot" / "quotes" / "2026-11-10.json"
            quote.parent.mkdir(parents=True)
            quote.write_text("{}\n", encoding="utf-8")
            self.assertNotIn("停写", apply_empty_stop(plan("2026-11-11 00:01", "大盘分析"), root))

    def test_empty_stop_skips_final_and_data_windows(self) -> None:
        root = Path("/tmp/astock-empty-desk-missing")
        self.assertNotIn("停写", apply_empty_stop(plan("2026-11-10 09:00", "终分"), root))
        self.assertNotIn("停写", apply_empty_stop(plan("2026-11-10 15:15", "跑资料面"), root))


if __name__ == "__main__":
    unittest.main()
