#!/usr/bin/env python3
"""Direction lines stay on sleeves the desk already has. No network."""

from __future__ import annotations

import unittest

from astock.direction import direction_lines

CPI = (
    "10月份，鲜菜、鲜果供应充足，带动食品价格同比下降。"
    "服务价格同比有所上涨。"
    "PPI同比上涨5.7%，涨幅比上月扩大0.7个百分点。"
    "计算机通信和其他电子设备制造业、电气机械和器材制造业价格同比均有所上涨。"
)


class DirectionTest(unittest.TestCase):
    def test_cpi_ppi_splits_food_electronics_and_electrical(self) -> None:
        lines = direction_lines(CPI, "2026-11-09 19:20")
        food = next(row for row in lines if row["sleeves"] and row["sleeves"][0]["name"] == "食品饮料")
        self.assertEqual(food["side"], "偏空")
        self.assertEqual(food["note"], "不改第二托")
        self.assertEqual(food["check"], "下一交易日收盘")
        self.assertFalse(food["changes_score"])
        self.assertFalse(food["used_this_round"])

        growth = next(row for row in lines if any(item["name"] == "通信" for item in row["sleeves"]))
        self.assertEqual(growth["side"], "偏多")
        self.assertEqual([item["code"] for item in growth["sleeves"]], ["399389", "399811", "000993", "000685"])
        self.assertFalse(growth["chip_separate"])
        self.assertEqual(growth["note"], "芯片不单独确认")

        electrical = next(row for row in lines if "不新开列" in row["note"])
        self.assertEqual(electrical["side"], "偏多")
        self.assertEqual(electrical["sleeves"], [])

        service = next(row for row in lines if "没有对应指数" in row["note"])
        self.assertEqual(service["side"], "偏多")
        self.assertTrue(all("PPI" not in row["note"] for row in lines))

    def test_clock_decides_the_check_day(self) -> None:
        before = direction_lines("鲜菜带动食品价格同比下降。", "2026-11-09 14:59")
        after = direction_lines("鲜菜带动食品价格同比下降。", "2026-11-09 15:00")
        self.assertEqual(before[0]["check"], "当日收盘")
        self.assertEqual(after[0]["check"], "下一交易日收盘")

    def test_repo_loan_oil_and_company_do_not_invent_a_sleeve(self) -> None:
        repo = direction_lines("开展1820亿元隔夜逆回购，利率1.25%。", "2026-11-09 09:20")
        self.assertEqual(repo[0]["note"], "不写进银行或电子")
        self.assertEqual(repo[0]["sleeves"], [])
        self.assertFalse(repo[0]["used_this_round"])

        loan = direction_lines("前十个月国开行发放制造业贷款超4800亿元。", "2026-11-09 19:28")
        self.assertEqual(loan[0]["note"], "制造业贷款不点名板块")

        oil = direction_lines("国际油价盘中下跌，布伦特原油至93.32美元。", "2026-11-09 22:56")
        self.assertEqual(oil[0]["side"], "偏空")
        self.assertEqual(oil[0]["sleeves"][0]["code"], "399998")
        self.assertEqual(oil[0]["check"], "待结算")

        settled = direction_lines("原油结算价下跌。", "2026-11-09 16:00")
        self.assertEqual(settled[0]["check"], "下一交易日收盘")

        company = direction_lines("控股股东拟协议转让，实际控制人可能变更。", "2026-11-09 22:54")
        self.assertEqual(company[0]["side"], "个股")
        self.assertEqual(company[0]["sleeves"], [])
        self.assertEqual(company[0]["check"], "不核板块")

    def test_named_chip_is_separate_and_empty_text_is_empty(self) -> None:
        chip = direction_lines("芯片价格同比上涨。", "2026-11-09 10:00")
        self.assertEqual(chip[0]["sleeves"][0]["code"], "000685")
        self.assertEqual(chip[0]["note"], "只核科创芯片")
        self.assertTrue(chip[0]["chip_separate"])
        named = direction_lines("计算机通信设备价格上涨，芯片价格同比上涨。", "2026-11-09 10:00")
        growth = next(row for row in named if row["sleeves"])
        self.assertTrue(growth["chip_separate"])
        self.assertEqual(direction_lines("   "), [])


if __name__ == "__main__":
    unittest.main()
