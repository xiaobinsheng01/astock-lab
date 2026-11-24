#!/usr/bin/env python3
"""Market-news desk. No network."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astock.news_desk import (
    SOURCE_BREAKFAST,
    SOURCE_CCTV,
    SOURCE_CLS,
    SOURCE_FLASH,
    classify_text,
    eastmoney_body,
    items_from_cctv_index,
    items_from_cls,
    items_from_em,
    render,
    select,
    write_page,
)

DAY = "2026-11-24"
TARIFF = "知情人士称美国拟对欧盟等上调关税，税率和生效日未定，官方未确认。"


def _item(source: str, text: str, clock: str, url: str, summary: str = "") -> dict:
    return {"source": source, "title": text, "summary": summary, "clock": clock, "url": url}


class ClassifyTest(unittest.TestCase):
    def test_direction_events_are_kept(self) -> None:
        margin = classify_text("融资保证金由100%调整为80%")
        self.assertEqual(margin["类别"], "监管")
        self.assertEqual(margin["映射板块"], "成长")
        self.assertEqual(margin["时效"], "当天")
        self.assertEqual(margin["改不改权重"], "不改权重")

        tariff = classify_text(TARIFF)
        self.assertEqual(tariff["类别"], "关税与出口管制")
        self.assertEqual(tariff["映射板块"], "成长、出口链")
        self.assertEqual(tariff["时效"], "隔夜")

        cobalt = classify_text("刚果（金）暂停钴出口")
        self.assertEqual(cobalt["类别"], "产业供给")
        self.assertEqual(cobalt["映射板块"], "有色")
        self.assertEqual(cobalt["时效"], "数日")

        drug = classify_text("单抗集采启动")
        self.assertEqual(drug["类别"], "监管")
        self.assertEqual(drug["映射板块"], "医药")

        hormuz = classify_text("霍尔木兹船只遇袭")
        self.assertEqual(hormuz["类别"], "地缘供给")
        self.assertEqual(hormuz["映射板块"], "油气")

        chip = classify_text("允许出售相对落后的芯片")
        self.assertEqual(chip["类别"], "关税与出口管制")
        self.assertIn("半导体", chip["映射板块"])

        buyback = classify_text("芯片公司回购12亿元")
        self.assertEqual(buyback["类别"], "并购与回购")
        self.assertEqual(buyback["映射板块"], "半导体")

        banks = classify_text("银行股回购10亿元")
        self.assertEqual(banks["映射板块"], "银行")

        seat = classify_text("即日起恢复黄仁勋的总裁、首席执行官及董事职务")
        self.assertEqual(seat["类别"], "关税与出口管制")
        self.assertIn("半导体", seat["映射板块"])

    def test_noise_is_dropped(self) -> None:
        for text in (
            "上证指数收跌1.2%",
            "某公司获得发明专利",
            "公司回购5000万元",
            "世界杯决赛开战",
            "快评：融资保证金降至80%",
            "证监会召开例行发布会",
            "将继续给予同我国建交的最不发达国家零关税待遇",
            "从法国巴黎银行获得贷款用于收购",
            "人民银行提及回购",
            "英伟达董事会放弃黄仁勋并非一时冲动",
        ):
            self.assertIsNone(classify_text(text), text)

    def test_digest_keeps_each_class_and_the_longer_sentence(self) -> None:
        rows = select(
            [
                _item(
                    SOURCE_BREAKFAST,
                    "财经早餐",
                    f"{DAY} 07:30",
                    "https://finance.eastmoney.com/a/breakfast.html",
                    summary=f"融资保证金由100%调整为80%。{TARIFF}刚果（金）暂停钴出口。",
                )
            ],
            DAY,
        )
        by_class = {row["类别"]: row for row in rows}
        self.assertEqual(set(by_class), {"监管", "关税与出口管制", "产业供给"})
        self.assertEqual(by_class["关税与出口管制"]["事实一句"], TARIFF)

    def test_same_class_keeps_distinct_sentences(self) -> None:
        rows = select(
            [
                _item(
                    SOURCE_BREAKFAST,
                    "财经早餐",
                    f"{DAY} 07:30",
                    "https://finance.eastmoney.com/a/breakfast.html",
                    summary="即日起恢复黄仁勋的职务。美国拟对欧盟等上调关税，税率未定。",
                )
            ],
            DAY,
        )
        facts = [row["事实一句"] for row in rows if row["类别"] == "关税与出口管制"]
        self.assertEqual(len(facts), 2)

    def test_follow_up_sentences_of_one_event_collapse(self) -> None:
        rows = select(
            [
                _item(
                    SOURCE_FLASH,
                    "霍尔木兹",
                    f"{DAY} 19:59",
                    "https://flash/hormuz",
                    summary="霍尔木兹海峡一艘油轮触雷。这是当日第四艘在该海峡触雷的油轮。另外两艘油轮掉头。",
                )
            ],
            DAY,
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("油轮", rows[0]["事实一句"])
        self.assertTrue(all(row["改不改权重"] == "不改权重" for row in rows))

    def test_flash_stops_at_twenty_and_breakfast_does_not(self) -> None:
        flash = [
            _item(SOURCE_FLASH, "融资保证金维持80%", f"{DAY} 10:{minute:02d}", f"https://flash/{minute}")
            for minute in range(21)
        ]
        breakfast = [
            _item(SOURCE_BREAKFAST, "两融保证金维持80%", f"{DAY} 08:{minute:02d}", f"https://breakfast/{minute}")
            for minute in range(21)
        ]
        flash_rows = select(flash, DAY)
        breakfast_rows = select(breakfast, DAY)
        self.assertEqual(len(flash_rows), 20)
        self.assertNotIn("10:00", [row["时间"] for row in flash_rows])
        self.assertEqual(len(breakfast_rows), 21)

    def test_missing_clock_and_other_days_stay_out(self) -> None:
        rows = select(
            [
                _item(SOURCE_FLASH, "融资保证金维持80%", "", "https://flash/none"),
                _item(SOURCE_FLASH, "融资保证金维持80%", "2026-11-23 21:14", "https://flash/yesterday"),
                {"source": SOURCE_FLASH, "title": "融资保证金维持80%", "summary": "", "clock": f"{DAY} 21:14", "url": ""},
            ],
            DAY,
        )
        self.assertEqual(rows, [])


class ParseTest(unittest.TestCase):
    def test_eastmoney_fields(self) -> None:
        payload = {
            "data": {
                "fastNewsList": [
                    {
                        "title": "美国拟对欧盟等上调关税",
                        "summary": TARIFF,
                        "showTime": f"{DAY} 21:14:08",
                        "code": "202611241114",
                    }
                ]
            }
        }
        row = items_from_em(payload, SOURCE_FLASH)[0]
        self.assertEqual(row["clock"], f"{DAY} 21:14")
        self.assertEqual(row["url"], "https://finance.eastmoney.com/a/202611241114.html")

    def test_cls_clock_is_beijing(self) -> None:
        payload = {
            "data": {
                "roll_data": [
                    {"id": 9, "title": "融资保证金维持80%", "content": "", "ctime": 1795526040}
                ]
            }
        }
        row = items_from_cls(payload)[0]
        self.assertEqual(row["clock"], f"{DAY} 21:14")
        self.assertEqual(row["url"], "https://www.cls.cn/detail/9")

    def test_breakfast_body_is_the_numbered_items(self) -> None:
        html = '<div id="ContentBody">融资保证金由100%调整为80%。</div>'
        self.assertIn("100%", eastmoney_body(html))

    def test_broadcast_uses_nineteen_hundred(self) -> None:
        html = """
        <a href="https://tv.cctv.com/2026/11/24/VIDE1.shtml">[视频]单抗集采启动</a>
        <a href="https://tv.cctv.com/lm/xwlb/day/20261124.shtml">新闻联播</a>
        """
        rows = items_from_cctv_index(html, DAY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["clock"], f"{DAY} 19:00")
        self.assertEqual(rows[0]["title"], "单抗集采启动")
        self.assertEqual(rows[0]["source"], SOURCE_CCTV)


class PageTest(unittest.TestCase):
    def test_page_names_the_eight_fields_and_leaves_jsonl(self) -> None:
        rows = select(
            [_item(SOURCE_FLASH, TARIFF, f"{DAY} 21:14", "https://finance.eastmoney.com/a/1.html")],
            DAY,
        )
        text = render(DAY, rows, [{"source": SOURCE_CLS, "error": "URLError"}])
        self.assertIn("不进 W1–W8。不改行为分。", text)
        self.assertIn("| 时间 | 来源 | 类别 | 事实一句 | 映射板块 | 时效 | 改不改权重 | 地址 |", text)
        self.assertIn("| 21:14 | 东方财富全球快讯 | 关税与出口管制 |", text)
        self.assertIn("| 不改权重 |", text)
        self.assertIn("未挂：财联社电报（URLError）", text)
        self.assertNotIn("本轮已用", text)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = root / "hot" / "news"
            news.mkdir(parents=True)
            jsonl = news / f"{DAY}.jsonl"
            jsonl.write_text('{"fact":"keep"}\n', encoding="utf-8")
            path = write_page(root, DAY, text)
            self.assertEqual(path.name, f"{DAY}.md")
            self.assertEqual(jsonl.read_text(encoding="utf-8"), '{"fact":"keep"}\n')
            self.assertIn("关税与出口管制", path.read_text(encoding="utf-8"))

    def test_empty_day_is_explicit(self) -> None:
        self.assertIn("这一日没有入选资讯。", render(DAY, [], []))

    def test_offline_main_writes_only_the_markdown_page(self) -> None:
        import io
        from contextlib import redirect_stdout

        from astock.news_desk import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = root / "items.json"
            items.write_text(
                json.dumps(
                    [_item(SOURCE_FLASH, "单抗集采启动", f"{DAY} 09:10", "https://flash/drug")],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                code = main(["--day", DAY, "--root", str(root), "--items", str(items)])
            self.assertEqual(code, 0)
            self.assertTrue((root / "hot" / "news" / f"{DAY}.md").exists())
            self.assertFalse((root / "hot" / "news" / f"{DAY}.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
