#!/usr/bin/env python3
"""Public-channel parsers. No network."""

from __future__ import annotations

import unittest

from datetime import datetime
from zoneinfo import ZoneInfo

from astock.a50 import assess, parse_a50
from astock.cash_close import assess_all, clock_from_parts, parse_shanghai_copper
from astock.cctv_feed import clock_from_focus, parse_cctv, programs_from_payload
from astock.cfbond_feed import parse_cfbond
from astock.close_inputs import breadth_close_status
from astock.cninfo_feed import pdf_status, read_announcements


class A50Test(unittest.TestCase):
    def test_missing_price_is_a_gap(self) -> None:
        self.assertEqual(assess(None, 100, "2026-11-10 08:00")["status"], "缺口")
        self.assertEqual(assess(100, "", "2026-11-10 08:00")["text"], "A50 缺最新价或前结")

    def test_threshold(self) -> None:
        self.assertEqual(assess(100.1, 100, "2026-11-10 08:00")["word"], "平开")
        self.assertEqual(assess(100.2, 100, "2026-11-10 08:00")["word"], "高开")
        self.assertEqual(assess(99.8, 100, "2026-11-10 08:00")["word"], "低开")


class CctvTest(unittest.TestCase):
    def test_named_programs_are_kept(self) -> None:
        html = "<div>2026-11-10 20:00 经济信息联播</div><div>正点财经 12:00</div>"
        result = parse_cctv(html)
        names = [item["program"] for item in result["items"]]
        self.assertEqual(names, ["正点财经", "经济信息联播"])

    def test_empty_page_is_unmounted(self) -> None:
        self.assertEqual(parse_cctv("   ")["status"], "未挂")
        self.assertEqual(parse_cctv("<p>其他栏目</p>")["status"], "栏目未挂")


class CfbondTest(unittest.TestCase):
    def test_source_line_marks_reprint(self) -> None:
        html = """
        <li data-time="2026-11-10 21:00" data-source="中国财富网">官方数字 12 亿</li>
        <li data-time="2026-11-10 21:05" data-source="上海证券报">转载稿</li>
        """
        items = parse_cfbond(html)["items"]
        self.assertEqual(items[0]["status"], "原文")
        self.assertEqual(items[1]["status"], "转载")


class CninfoTest(unittest.TestCase):
    def test_code_only_zero_is_not_no_announcement(self) -> None:
        result = read_announcements([], with_org=False)
        self.assertIn("不写成没发公告", result["status"])

    def test_another_company_is_not_this_announcement(self) -> None:
        rows = [{"announcementTitle": "别的公司", "secCode": "600000"}]
        result = read_announcements(rows, with_org=True, code="000001")
        self.assertIn("不是这只股票", result["status"])
        self.assertEqual(result["items"], [])

    def test_a_row_without_a_code_is_not_this_announcement(self) -> None:
        rows = [{"announcementTitle": "没有证券代码"}]
        result = read_announcements(rows, with_org=True, code="000001")
        self.assertIn("不是这只股票", result["status"])

    def test_pdf_header(self) -> None:
        self.assertEqual(pdf_status(b"%PDF-1.7"), "数字来自巨潮 PDF")
        self.assertEqual(pdf_status(b"<html>"), "交易所 PDF 未挂")


class CashTest(unittest.TestCase):
    def test_missing_price_is_a_gap_and_empty_input_is_unmounted(self) -> None:
        self.assertEqual(assess_all([])["status"], "未挂")
        item = assess_all([{"name": "原油", "price": None, "prev": 70, "clock": "09:00"}])["items"][0]
        self.assertEqual(item["status"], "缺口")
        self.assertIn("缺收盘价", item["text"])

    def test_a_price_without_a_settle_names_the_settle(self) -> None:
        item = assess_all([{"name": "美元", "price": 102.908, "prev": None, "clock": "09:00"}])["items"][0]
        self.assertEqual(item["status"], "缺口")
        self.assertIn("缺前结", item["text"])
        self.assertEqual(item["price"], 102.908)

    def test_us_clock_is_read_from_one_field(self) -> None:
        self.assertEqual(clock_from_parts(["2026-11-13 11:51:21"]), "2026-11-13 11:51")

    def test_shanghai_copper_uses_the_settle_field(self) -> None:
        body = (
            "铜连续,004947,105150.000,105440.000,104260.000,0.000,104400.000,"
            "104410.000,104410.000,0.000,105040.000,5,1,183883.000,38521,沪,铜,2026-11-14,1"
        )
        parsed = parse_shanghai_copper(body)
        self.assertEqual(parsed["price"], "104410.000")
        self.assertEqual(parsed["prev"], "105040.000")
        self.assertEqual(parsed["clock"], "2026-11-14 00:49")


class A50ParseTest(unittest.TestCase):
    def test_prior_settle_is_not_the_bid(self) -> None:
        body = "12816.300,,12817.000,12818.000,12871.000,12810.000,00:51:33,12830.000,12829.000,0,0,0,2026-11-14,富时中国A50"
        parsed = parse_a50(body)
        self.assertEqual(parsed["latest"], "12816.300")
        self.assertEqual(parsed["previous"], "12830.000")


class BreadthClockTest(unittest.TestCase):
    def test_counts_before_the_close_are_not_scored(self) -> None:
        morning = datetime(2026, 11, 13, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        afternoon = datetime(2026, 11, 13, 15, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertFalse(breadth_close_status("20261113", morning)["verified"])
        self.assertTrue(breadth_close_status("20261113", afternoon)["verified"])


class CctvApiTest(unittest.TestCase):
    def test_column_payload_keeps_the_air_time(self) -> None:
        self.assertEqual(clock_from_focus(1794533170635), "2026-11-13 09:26")
        result = programs_from_payload(
            "第一时间",
            {"data": {"list": [{"title": "第一时间 20261113", "focus_date": 1794533170635, "url": "https://tv.cctv.com/a"}]}},
        )
        self.assertEqual(result["status"], "已列")
        self.assertEqual(result["items"][0]["clock"], "2026-11-13 09:26")


if __name__ == "__main__":
    unittest.main()
