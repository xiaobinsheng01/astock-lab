#!/usr/bin/env python3
"""Fundamental portrait. No network."""

from __future__ import annotations

import unittest

from astock.fundamental import (
    NOT_APPLICABLE,
    _balance_view,
    _finance_report,
    board_limit,
    deducted_turn,
    format_portrait,
    next_unlock,
    portrait,
    fetch_queries,
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

    def test_indicator_page_series_is_used(self) -> None:
        rows = [
            {"REPORT_DATE_NAME": "2026三季报", "TOTALOPERATEREVE": 3e10,
             "TOTALOPERATEREVETZ": 5.0, "PARENTNETPROFIT": 2e9, "XSMLL": 30.0},
            {"REPORT_DATE_NAME": "2026中报", "TOTALOPERATEREVE": 2e10,
             "TOTALOPERATEREVETZ": 4.0, "PARENTNETPROFIT": 1e9, "XSMLL": 29.0},
            {"REPORT_DATE_NAME": "2026一季报", "TOTALOPERATEREVE": None},
        ]
        sheet = portrait({"code": "600000", "indicators": rows}, "2026-11-25")
        series = sheet["机构"]["报表序列"]
        self.assertEqual([row["报告期"] for row in series], ["2026三季报", "2026中报"])
        self.assertEqual(series[0]["营业总收入亿元"], 300.0)
        self.assertTrue(any("报告期 2026三季报" in line for line in format_portrait(sheet).splitlines()))

    def test_quarterly_deducted_roe_is_not_a_fetch_failure(self) -> None:
        quarter = portrait(
            {"code": "600000", "indicators": [{"REPORT_DATE_NAME": "2026三季报"}]}, "2026-11-25"
        )
        self.assertEqual(quarter["机构"]["扣非加权ROE"], "本期不披露")
        annual = portrait(
            {"code": "600000", "indicators": [{"REPORT_DATE_NAME": "2025年报", "ROEKCJQ": 9.9}]},
            "2026-11-25",
        )
        self.assertEqual(annual["机构"]["扣非加权ROE"], 9.9)

    def test_balance_sheet_items_are_wired(self) -> None:
        sheet = portrait(
            {"code": "600000", "balance": [{
                "REPORT_DATE": "2026-09-30 00:00:00",
                "MONETARYFUNDS": 5e9, "ACCOUNTS_RECE": 1e9, "INVENTORY": 2e9,
                "GOODWILL": None, "SHORT_LOAN": 1e9, "LONG_LOAN": None,
                "BOND_PAYABLE": None, "NONCURRENT_LIAB_1YEAR": None,
            }]},
            "2026-11-25",
        )
        block = sheet["机构"]["资产负债分项"]
        self.assertEqual(block["状态"], "已核")
        self.assertEqual(block["货币资金亿元"], 50.0)
        self.assertEqual(block["商誉亿元"], "未核")
        self.assertEqual(block["有息负债亿元"], 10.0)

    def test_dead_page_differs_from_an_empty_statement(self) -> None:
        dead = portrait({"code": "600000", "balance": None}, "2026-11-25")["机构"]["资产负债分项"]
        self.assertEqual(dead["状态"], "未核")
        blank = portrait({"code": "600000", "balance": []}, "2026-11-25")["机构"]["资产负债分项"]
        self.assertEqual(blank["状态"], "无")

    def test_dividend_plan_text_survives_a_missing_figure(self) -> None:
        sheet = portrait(
            {"code": "600000", "dividends": [{
                "REPORT_DATE": "2026-06-30 00:00:00",
                "ASSIGN_PROGRESS": "预披露",
                "PRETAX_BONUS_RMB": None,
                "IMPL_PLAN_PROFILE": "每10股派发现金红利应不少于3.8元(含税)",
            }]},
            "2026-11-25",
        )
        plan = sheet["机构"]["分红"]["明细"][0]
        self.assertEqual(plan["每10股派元"], "未核")
        self.assertIn("不少于3.8元", plan["方案原文"])
        self.assertIn("方案原文", format_portrait(sheet))

    def test_dividend_is_per_ten_shares_not_per_share(self) -> None:
        # 茅台 2025-12-31 是 10派280.2423元。按每股再乘 10 会得出 2802.42。
        sheet = portrait(
            {"code": "600519", "dividends": [{
                "REPORT_DATE": "2025-12-31 00:00:00",
                "ASSIGN_PROGRESS": "实施分配",
                "PRETAX_BONUS_RMB": 280.2423,
                "IMPL_PLAN_PROFILE": "10派280.2423元(含税)",
            }]},
            "2026-11-25",
        )
        plan = sheet["机构"]["分红"]["明细"][0]
        self.assertEqual(plan["每10股派元"], 280.2423)
        self.assertNotEqual(plan["每10股派元"], 2802.423)

    def test_finance_sectors_use_their_own_statements(self) -> None:
        # 三类金融股各用一张报表，用错表名拿到的是空表，看着像页面挂了。
        self.assertEqual(_finance_report("银行"), "RPT_F10_FINANCE_BBALANCE")
        self.assertEqual(_finance_report("保险"), "RPT_F10_FINANCE_IBALANCE")
        self.assertEqual(_finance_report("券商信托"), "RPT_F10_FINANCE_SBALANCE")
        self.assertIsNone(_finance_report("有色金属"))

    def test_bank_cash_is_the_central_bank_deposit(self) -> None:
        # CURRENCY 是记账币种（CNY），当成货币资金会印出「货币资金0亿」。
        block = _balance_view(
            [{
                "REPORT_DATE": "2026-09-30 00:00:00",
                "CASH_DEPOSIT_PBC": 5e11, "GOODWILL": 1e10,
                "LOAN_ADVANCE": 7e12, "ACCEPT_DEPOSIT": 1e13, "BOND_PAYABLE": 1e11,
                "CURRENCY": "CNY",
            }],
            industry="银行",
        )
        self.assertEqual(block["货币资金亿元"], 5000.0)
        self.assertEqual(block["货币资金口径"], "存放中央银行款项")
        self.assertEqual(block["有息负债亿元"], NOT_APPLICABLE)
        self.assertEqual(block["应收账款亿元"], NOT_APPLICABLE)
        self.assertNotEqual(block["货币资金亿元"], 0)

    def test_broker_receivables_use_their_own_column(self) -> None:
        block = _balance_view(
            [{
                "REPORT_DATE": "2026-09-30 00:00:00",
                "MONETARYFUNDS": 1e11, "RECEIVABLES": 2e10, "GOODWILL": 1e9,
                "LONG_LOAN": 0, "BOND_PAYABLE": 3e11,
            }],
            industry="券商信托",
        )
        self.assertEqual(block["应收账款亿元"], 200.0)
        self.assertEqual(block["存货亿元"], NOT_APPLICABLE)

    def test_finance_debt_includes_bonds(self) -> None:
        # 中信用长借 0、债券 2114 亿，只算长借款会印出「有息负债0.07亿」。
        block = _balance_view(
            [{
                "REPORT_DATE": "2026-09-30 00:00:00",
                "MONETARYFUNDS": 1e11, "RECEIVABLES": 1e10, "GOODWILL": 1e9,
                "LONG_LOAN": 7e6, "BOND_PAYABLE": 2.114e11,
            }],
            industry="券商信托",
        )
        self.assertEqual(block["有息负债亿元"], 2114.07)

    def test_industrial_statement_is_unaffected(self) -> None:
        block = _balance_view(
            [{"REPORT_DATE": "2026-09-30 00:00:00", "MONETARYFUNDS": 1e10,
              "ACCOUNTS_RECE": 1e9, "INVENTORY": 2e9, "GOODWILL": None,
              "SHORT_LOAN": 1e9}],
            industry="有色金属",
        )
        self.assertEqual(block["存货亿元"], 20.0)
        self.assertEqual(block["商誉亿元"], "未核")
        self.assertEqual(block["有息负债亿元"], 10.0)

    def test_a_company_without_a_controller_says_so(self) -> None:
        # 招行、平安、中信的 sjkzr 页返回行但名称为空，这是股权分散，不是缺数。
        sheet = portrait(
            {"code": "600036", "controller": [{"HOLDER_NAME": None, "HOLD_RATIO": None}]},
            "2026-11-25",
        )
        self.assertEqual(sheet["主力"]["实际控制人"], "无实际控制人")
        # 无实控人不能变成一个「查控制权与股东公告」的查询词。
        self.assertFalse(any("无实际控制人" in str(row["查询"]) for row in fetch_queries(sheet)))
        missing = portrait({"code": "600036"}, "2026-11-25")
        self.assertEqual(missing["主力"]["实际控制人"], "未核")

    def test_financial_statement_has_no_gross_margin(self) -> None:
        sheet = portrait(
            {"code": "600036", "survey": {"jbzl": {"sshy": "银行"}},
             "indicators": [{"REPORT_DATE_NAME": "2026三季报", "TOTALOPERATEREVE": 1e10}]},
            "2026-11-25",
        )
        self.assertEqual(sheet["机构"]["毛利率"], NOT_APPLICABLE)
        self.assertEqual(sheet["机构"]["流动比率"], NOT_APPLICABLE)
        self.assertEqual(sheet["机构"]["报表序列"][0]["毛利率"], NOT_APPLICABLE)

    def test_restricted_shares_are_not_guessed(self) -> None:
        resolved = portrait(
            {"code": "601899", "capital": [{"TOTAL_SHARES": 1000, "LISTED_A_SHARES": 700,
                                            "H_FREE_SHARE": 300}]},
            "2026-11-25",
        )
        self.assertEqual(resolved["游资"]["限售股"], 0)
        unknown = portrait(
            {"code": "601899", "capital": [{"TOTAL_SHARES": 1000, "LISTED_A_SHARES": 800}]},
            "2026-11-25",
        )
        self.assertEqual(unknown["游资"]["限售股"], "未核")

    def test_free_float_cap_carries_its_quote_moment(self) -> None:
        sheet = portrait(
            {"code": "601899", "quote": {
                "收盘": 24.11, "行情日期": "2026-11-27", "行情时刻": "2026-11-27 11:00",
                "是否收盘": "否（盘中）", "流通市值亿": 4967.09, "总市值亿": 6411.04,
                "换手率": 0.65, "量比": 0.87,
            }},
            "2026-11-25",
        )
        text = format_portrait(sheet)
        self.assertIn("4967.09亿", text)
        self.assertIn("2026-11-27 11:00", text)
        self.assertIn("盘中", text)

    def test_a_failed_quote_leaves_the_cap_unchecked(self) -> None:
        sheet = portrait({"code": "601899", "quote": {}}, "2026-11-25")
        self.assertEqual(sheet["游资"]["行情"]["状态"], "未核")
        self.assertIn("自由流通市值: 未核", format_portrait(sheet))


if __name__ == "__main__":
    unittest.main()
