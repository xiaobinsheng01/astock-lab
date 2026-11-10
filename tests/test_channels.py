#!/usr/bin/env python3
"""Public-channel parsers. No network."""

from __future__ import annotations

import unittest

from astock.a50 import assess
from astock.cash_close import assess_all
from astock.cctv_feed import parse_cctv
from astock.cfbond_feed import parse_cfbond
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

    def test_pdf_header(self) -> None:
        self.assertEqual(pdf_status(b"%PDF-1.7"), "数字来自巨潮 PDF")
        self.assertEqual(pdf_status(b"<html>"), "交易所 PDF 未挂")


class CashTest(unittest.TestCase):
    def test_missing_price_is_a_gap_and_empty_input_is_unmounted(self) -> None:
        self.assertEqual(assess_all([])["status"], "未挂")
        item = assess_all([{"name": "原油", "price": None, "prev": 70, "clock": "09:00"}])["items"][0]
        self.assertEqual(item["status"], "缺口")


if __name__ == "__main__":
    unittest.main()
