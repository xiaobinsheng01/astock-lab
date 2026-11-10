#!/usr/bin/env python3
"""Fact-sentence checks. No network."""

from __future__ import annotations

import unittest

from astock.sentence import already_clear, seal

TAIL = "不改行为分、不改主路径、不改 9:15。不进四档、不改 14:55。"


class SentenceTest(unittest.TestCase):
    def test_clear_snippet_skips_the_model(self) -> None:
        snippet = "英特尔第三财季营收 142.5 亿美元。"
        self.assertTrue(already_clear(snippet))
        result = seal(snippet, None, "业绩")
        self.assertTrue(result["accepted"])
        self.assertFalse(result["called_model"])
        self.assertIn("142.5", result["text"])
        self.assertIn(TAIL, result["text"])

    def test_extra_number_is_dropped(self) -> None:
        result = seal("营收 142.5 亿美元", "营收 150 亿美元", "业绩")
        self.assertFalse(result["accepted"])
        self.assertTrue(result["called_model"])
        self.assertIn("页面未给业绩数字", result["text"])
        self.assertNotIn("150", result["text"])

    def test_page_without_a_number(self) -> None:
        result = seal("公司发布了新的产品计划", "营收 10 亿元", "业绩")
        self.assertIn("页面未给业绩数字", result["text"])
        self.assertNotIn("10", result["text"])

    def test_price_gap_uses_the_price_phrase(self) -> None:
        result = seal("只写了上涨", None, "价格")
        self.assertIn("页面未给价格", result["text"])
        self.assertIn(TAIL, result["text"])

    def test_matching_model_sentence_is_kept(self) -> None:
        result = seal("页面显示营收142.5亿美元，同比增加。", "营收 142.5 亿美元。", "业绩")
        self.assertTrue(result["accepted"])
        self.assertIn("142.5", result["text"])


if __name__ == "__main__":
    unittest.main()
