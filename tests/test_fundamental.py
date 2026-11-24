#!/usr/bin/env python3
"""Fundamental portrait. No network."""

from __future__ import annotations

import unittest

from astock.fundamental import (
    board_limit,
    deducted_turn,
    format_portrait,
    next_unlock,
    portrait,
    self_check,
)
from astock.route import plan


class FundamentalTest(unittest.TestCase):
    def test_self_check(self) -> None:
        self.assertEqual(self_check(), 0)

    def test_missing_cells_stay_unchecked(self) -> None:
        sheet = portrait({"code": "002081", "name": "金螳螂"}, "2026-11-25")
        self.assertEqual(sheet["机构"]["业绩"], "未核")
        self.assertEqual(sheet["机构"]["扣非拐点"], "未核")
        self.assertEqual(sheet["主力"]["实际控制人"], "未核")
        self.assertEqual(sheet["游资"]["板块"], "主板")
        self.assertEqual(sheet["游资"]["涨跌幅上限"], 10)
        self.assertNotIn("收盘", format_portrait(sheet))

    def test_deducted_turn_needs_both_periods(self) -> None:
        self.assertEqual(deducted_turn(1, -1), "由负转正")
        self.assertEqual(deducted_turn(-1, 1), "由正转负")
        self.assertEqual(deducted_turn(1, None), "未核")

    def test_past_unlock_is_none(self) -> None:
        block = next_unlock(
            [{"LIFT_DATE": "2020-01-01", "LIFT_NUM": 1, "LIFT_TYPE": "旧", "TOTAL_SHARES_RATIO": 1}],
            "2026-11-25",
            100,
        )
        self.assertEqual(block["状态"], "无")

    def test_limit_regime(self) -> None:
        self.assertEqual(board_limit("688111", "金山办公")["涨跌幅上限"], 20)
        self.assertEqual(board_limit("830001", "北证示例")["板块"], "北交所")
        self.assertEqual(board_limit("600127", "ST金健")["涨跌幅上限"], 5)

    def test_route_opens_the_portrait(self) -> None:
        row = plan("2026-11-25 01:07", "构建个股画像")
        self.assertEqual(row["窗口"], "取数")
        self.assertEqual(row["轮次"], "个股画像")
        self.assertEqual(row["跑"], "portrait")
        self.assertIn("行为分", row["不打开"])
        self.assertNotIn("技术面", row["不打开"])
        preview = plan("2026-11-25 08:30", "大盘预判")
        self.assertEqual(preview["轮次"], "预判")


if __name__ == "__main__":
    unittest.main()
