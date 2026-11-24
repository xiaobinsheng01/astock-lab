#!/usr/bin/env python3
"""Classifier checks for the overseas market list. No network."""

from __future__ import annotations

import unittest

from astock.overseas_feed import _round_robin, classify, items_from_html

FIXTURE = """
<a href="https://www.news.cn/world/20261104/a58541d091da468eb33bce05b5cdb32e/c.html">美民主党连获关键州席位</a>
<a href="https://www.news.cn/world/20261104/618d960658774abfaa4a0e894883310c/c.html">或重掌国会</a>
<a href="https://www.news.cn/world/20261104/5fa0c6f07cdf4c89b7c3295281a0da7f/c.html">美民主党重掌国会 特朗普执政承重压</a>
<a href="https://www.news.cn/world/20261104/c3d17ff380a745bc847677f30e015953/c.html">特朗普：若民主党掌控国会 他将行使否决权</a>
<a href="https://www.news.cn/world/20261104/vote.html">美国举行中期选举投票</a>
<a href="https://www.news.cn/world/20261104/poll.html">民调：美民主党对共和党中期选举领先优势缩小</a>
<a href="https://www.news.cn/world/20261104/spend.html">2026年美国中期选举总支出预计达119亿美元</a>
<a href="https://www.news.cn/fortune/20261104/a94ccab9783d417bab20b01576569312/c.html">纽约股市3日收盘</a>
<a href="https://www.news.cn/world/20261103/bg.html">保加利亚现任总统约托娃赢得总统选举</a>
<a href="https://www.news.cn/world/20261104/a58541d091da468eb33bce05b5cdb32e/c.html">美民主党连获关键州席位</a>
"""


class ClassifyTest(unittest.TestCase):
    def test_session_results_are_kept(self) -> None:
        self.assertEqual(classify("美民主党连获关键州席位"), "election_result")
        self.assertEqual(classify("或重掌国会"), "election_result")
        self.assertEqual(classify("美民主党重掌国会 特朗普执政承重压"), "election_result")
        self.assertEqual(classify("美国媒体预计民主党夺回参议院重掌国会"), "election_result")

    def test_title_keywords_do_not_drop_dated_links(self) -> None:
        html = """
        <a href="https://www.news.cn/world/20261104/cond.html">特朗普：若民主党掌控国会 他将行使否决权</a>
        <a href="https://www.news.cn/world/20261103/bg.html">保加利亚现任总统约托娃赢得总统选举</a>
        <a href="https://www.news.cn/world/20261123/huang.html">黄仁勋复职</a>
        <a href="https://www.news.cn/fortune/20261104/gold.html">前三季度我国黄金产量同比下降</a>
        <a href="https://www.news.cn/world/vote.html">美国举行中期选举投票</a>
        """
        titles = [row["title"] for row in items_from_html(html, "world")]
        self.assertEqual(
            titles,
            [
                "特朗普：若民主党掌控国会 他将行使否决权",
                "保加利亚现任总统约托娃赢得总统选举",
                "黄仁勋复职",
                "前三季度我国黄金产量同比下降",
            ],
        )

    def test_fixture_keeps_dated_links_and_dedupes_the_address(self) -> None:
        rows = items_from_html(FIXTURE, "world")
        titles = [row["title"] for row in rows]
        self.assertIn("特朗普：若民主党掌控国会 他将行使否决权", titles)
        self.assertIn("保加利亚现任总统约托娃赢得总统选举", titles)
        self.assertIn("纽约股市3日收盘", titles)
        self.assertIn("美国举行中期选举投票", titles)
        self.assertIn("民调：美民主党对共和党中期选举领先优势缩小", titles)
        urls = [row["url"] for row in rows]
        self.assertEqual(len(urls), len(set(urls)))

    def test_same_title_with_two_addresses_both_stay(self) -> None:
        world = [{"title": "国际金价反弹", "url": "https://www.news.cn/world/a"}]
        fortune = [
            {"title": "国际金价反弹", "url": "https://www.news.cn/fortune/b"},
            {"title": "黄仁勋复职", "url": "https://www.news.cn/world/c"},
        ]
        rows = _round_robin(world, fortune, None)
        self.assertEqual(
            [row["url"] for row in rows],
            [
                "https://www.news.cn/world/a",
                "https://www.news.cn/fortune/b",
                "https://www.news.cn/world/c",
            ],
        )


if __name__ == "__main__":
    unittest.main()
