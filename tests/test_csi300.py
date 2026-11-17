#!/usr/bin/env python3
"""CSI 300 data-layer packet. No network."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from astock.csi300 import (
    EM_KLINE_URL,
    EM_QUOTE_URL,
    IFZQ_URL,
    NEWFQ_URL,
    QUOTE_URL,
    SINA_KLINE_URL,
    SINA_QUOTE_URL,
    assemble,
    collect,
    parse_tencent_quote,
    session_word,
    store,
)

TENCENT = (
    'v_sh000300="1~沪深300~000300~3979.80~4016.29~3984.77~185439196~'
    "0~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~~"
    "20261116161409~-36.49~-0.91~3997.40~3959.93~3979.80/185439196/430554181505~"
    "185439196~43055418~0.55~13.45~~3997.40~3959.93~0.93~480992.93~507426.60~0.00~"
    '-1~-1~1.12~0~3978.91~~~~~~43055418.1505~0.0000~0~ ~ZS~";'
)

IFZQ = json.dumps(
    {
        "data": {
            "sh000300": {
                "day": [
                    ["2026-11-13", "4047.77", "4016.29", "4052.06", "4004.50", "999"],
                    ["2026-11-16", "3984.77", "3979.80", "3997.40", "3959.93", "185439196"],
                ]
            }
        }
    }
)

NEWFQ = json.dumps(
    {
        "data": {
            "sh000300": {
                "day": [
                    ["2026-11-13", "1", "1", "1", "1", "1", {}, "0", "401629.00"],
                    ["2026-11-16", "9", "9", "9", "9", "9", {}, "0", "43055418.00"],
                ]
            }
        }
    }
)


def _ok(url: str) -> str:
    if url == QUOTE_URL:
        return TENCENT
    if url == IFZQ_URL:
        return IFZQ
    if url == NEWFQ_URL:
        return NEWFQ
    raise AssertionError(url)


class Csi300Test(unittest.TestCase):
    def test_tencent_close_is_recorded_and_stays_out_of_weights(self) -> None:
        packet = collect(_ok)
        self.assertEqual(packet["status"], "已核")
        self.assertEqual(packet["session"], "收盘")
        self.assertEqual(packet["px"], 3979.80)
        self.assertEqual(packet["pct"], -0.91)
        self.assertEqual(packet["amount_yi"], 4305.54)
        self.assertEqual(packet["amount_status"], "已核")
        self.assertEqual(packet["source"], "qt.gtimg.cn")
        self.assertIn("web.ifzq.gtimg.cn", packet["bar_source"])
        self.assertEqual(packet["weights"], "不进W1–W8")
        self.assertEqual(packet["cushion"], "不进托住")
        self.assertIn("不进托住", packet["text"])
        last = packet["bars"][-1]
        self.assertEqual(last["date"], "2026-11-16")
        self.assertEqual(last["close"], 3979.80)
        self.assertEqual(last["high"], 3997.40)
        self.assertEqual(last["amount_yi"], 4305.54)
        self.assertEqual(packet["bars"][0]["amount_yi"], 40.16)

    def test_volume_on_the_bar_is_not_turnover(self) -> None:
        def get(url: str) -> str:
            if url == QUOTE_URL:
                return TENCENT
            if url == IFZQ_URL:
                return IFZQ
            if url == NEWFQ_URL:
                raise TimeoutError("dead")
            raise AssertionError(url)

        packet = collect(get)
        self.assertIsNone(packet["bars"][-1]["amount_yi"])
        self.assertEqual(packet["amount_status"], "已核")
        self.assertTrue(any(row["error"] == "TimeoutError" for row in packet["mounts"]))

    def test_vendor_percent_disagreement_keeps_both(self) -> None:
        raw = TENCENT.replace("~-0.91~", "~1.50~", 1)
        quote = parse_tencent_quote(raw)
        packet = assemble(quote, [], "", [])
        self.assertEqual(packet["status"], "未核")
        self.assertEqual(packet["vendor_pct"], 1.50)
        self.assertEqual(packet["pct"], -0.91)
        self.assertIn("两个都留", packet["text"])

    def test_amount_disagreement_keeps_both(self) -> None:
        quote = parse_tencent_quote(TENCENT)
        bars = [
            {
                "date": "2026-11-16",
                "open": 3984.77,
                "high": 3997.40,
                "low": 3959.93,
                "close": 3979.80,
                "prev": 4016.29,
                "pct": -0.91,
                "amount_yi": 4400.00,
            }
        ]
        packet = assemble(quote, bars, "proxy.finance.qq.com/newfqkline", [])
        self.assertEqual(packet["status"], "未核")
        self.assertEqual(packet["amount_yi"], 4305.54)
        self.assertEqual(packet["bar_amount_yi"], 4400.00)

    def test_missing_price_is_a_gap_and_empty_body_is_unmounted(self) -> None:
        self.assertEqual(parse_tencent_quote("   ")["status"], "未挂")
        quote = parse_tencent_quote(TENCENT.replace("~3979.80~", "~~", 1))
        packet = assemble(quote, [], "", [])
        self.assertEqual(packet["status"], "缺口")
        self.assertIn("缺现价", packet["text"])

    def test_later_source_does_not_cover_tencent(self) -> None:
        calls = []

        def get(url: str) -> str:
            calls.append(url)
            return _ok(url)

        collect(get)
        self.assertNotIn(SINA_QUOTE_URL, calls)
        self.assertNotIn(EM_QUOTE_URL, calls)
        self.assertNotIn(SINA_KLINE_URL, calls)
        self.assertNotIn(EM_KLINE_URL, calls)

    def test_sina_is_used_only_after_tencent_fails(self) -> None:
        def get(url: str) -> str:
            if url in {QUOTE_URL, IFZQ_URL, NEWFQ_URL}:
                raise ConnectionError("closed")
            if url == SINA_QUOTE_URL:
                return (
                    'var hq_str_sh000300="沪深300,3984.7731,4016.2897,3979.8035,'
                    '3997.4042,3959.9321,0,0,185439196,430554181505,'
                    + "0," * 20
                    + '2026-11-16,15:35:39,00,";'
                )
            if url == SINA_KLINE_URL:
                return json.dumps(
                    [
                        {
                            "day": "2026-11-16",
                            "open": "3984.773",
                            "high": "3997.404",
                            "low": "3959.932",
                            "close": "3979.804",
                            "volume": "18543919600",
                        }
                    ]
                )
            raise AssertionError(url)

        packet = collect(get)
        self.assertEqual(packet["source"], "hq.sinajs.cn")
        self.assertEqual(packet["bar_source"], "money.finance.sina.com.cn")
        self.assertIsNone(packet["bars"][-1]["amount_yi"])
        self.assertEqual(packet["status"], "已核")

    def test_eastmoney_is_last_and_a_502_stays_unmounted(self) -> None:
        def get(url: str) -> str:
            if url in {QUOTE_URL, IFZQ_URL, NEWFQ_URL, SINA_QUOTE_URL, SINA_KLINE_URL}:
                raise OSError("502")
            if url == EM_QUOTE_URL:
                return json.dumps(
                    {
                        "data": {
                            "f43": 397980,
                            "f44": 399740,
                            "f45": 395993,
                            "f46": 398477,
                            "f48": 430554181505,
                            "f57": "000300",
                            "f58": "沪深300",
                            "f60": 401629,
                            "f170": -91,
                            "f86": 1763280849,
                        }
                    }
                )
            if url == EM_KLINE_URL:
                return json.dumps(
                    {
                        "data": {
                            "klines": [
                                "2026-11-16,3984.77,3979.80,3997.40,3959.93,185439196,430554181505"
                            ]
                        }
                    }
                )
            raise AssertionError(url)

        packet = collect(get)
        self.assertEqual(packet["source"], "push2.eastmoney.com")
        self.assertEqual(packet["px"], 3979.80)
        self.assertEqual(packet["pct"], -0.91)
        self.assertEqual(packet["bars"][-1]["amount_yi"], 4305.54)
        self.assertTrue(packet["mounts"])

        def dead(_url: str) -> str:
            raise ConnectionResetError("closed")

        empty = collect(dead)
        self.assertEqual(empty["status"], "未挂")
        self.assertEqual(empty["text"], "沪深300 报价未挂")

    def test_session_words(self) -> None:
        self.assertEqual(session_word("2026-11-16 16:14:09"), "收盘")
        self.assertEqual(session_word("2026-11-16 10:00:00"), "盘中")
        self.assertEqual(session_word("2026-11-16 09:15:00"), "未开盘")
        self.assertEqual(session_word("2026-11-15 16:00:00"), "休市")

    def test_store_writes_snapshot_and_ten_sessions(self) -> None:
        bars = [
            {
                "date": f"2026-11-{day:02d}",
                "open": 4000.0,
                "high": 4010.0,
                "low": 3990.0,
                "close": 4000.0 + day,
                "amount_yi": 1000.0,
            }
            for day in range(1, 13)
            if day not in {7, 8}
        ]
        packet = assemble(parse_tencent_quote(TENCENT), bars[-10:], "fixture", [])
        with TemporaryDirectory() as folder:
            root = Path(folder)
            written = store(packet, root)
            saved = json.loads(Path(written["snapshot"]).read_text(encoding="utf-8"))
            kept = json.loads((root / "bars" / "000300.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["代码"], "000300")
        self.assertEqual(saved["托住"], "不进托住")
        self.assertEqual(len(kept), 10)
        self.assertEqual(kept[-1]["date"], bars[-1]["date"])

    def test_unmounted_fetch_keeps_the_last_snapshot(self) -> None:
        packet = assemble(parse_tencent_quote(TENCENT), [], "fixture", [])
        with TemporaryDirectory() as folder:
            root = Path(folder)
            first = store(packet, root)
            text = Path(first["snapshot"]).read_text(encoding="utf-8")
            kept = store({"status": "未挂", "bars": [], "text": "沪深300 报价未挂"}, root)
            self.assertEqual(kept["snapshot"], "保留上一份")
            self.assertEqual(Path(first["snapshot"]).read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()
