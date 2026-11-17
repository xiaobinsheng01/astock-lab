#!/usr/bin/env python3
"""HuaBao ChiNext-STAR 50 ETF on the data layer. No network."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from astock.csi300 import parse_eastmoney_quote
from astock.dual50 import collect, store

QUOTE = "https://qt.gtimg.cn/q=sh588330"
IFZQ = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh588330,day,,,12,qfq"
)
NEWFQ = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    "?param=sh588330,day,,,12,qfq"
)


def _tencent() -> str:
    parts = [""] * 40
    parts[1] = "双创50ETF华宝"
    parts[2] = "588330"
    parts[3] = "0.718"
    parts[4] = "0.761"
    parts[5] = "0.742"
    parts[30] = "20261116161453"
    parts[32] = "-5.65"
    parts[33] = "0.748"
    parts[34] = "0.711"
    parts[37] = "11036"
    return 'v_sh588330="' + "~".join(parts) + '";'


IFZQ_BODY = json.dumps(
    {
        "data": {
            "sh588330": {
                "day": [
                    ["2026-11-13", "0.770", "0.761", "0.780", "0.755", "999"],
                    ["2026-11-16", "0.742", "0.718", "0.748", "0.711", "1516190"],
                ]
            }
        }
    }
)
NEWFQ_BODY = json.dumps(
    {
        "data": {
            "sh588330": {
                "day": [
                    ["2026-11-13", "1", "1", "1", "1", "1", {}, "0", "9000.00"],
                    ["2026-11-16", "9", "9", "9", "9", "9", {}, "0", "11035.77"],
                ]
            }
        }
    }
)


class Dual50Test(unittest.TestCase):
    def test_close_keeps_three_decimals_and_stays_out_of_weights(self) -> None:
        def get(url: str) -> str:
            if url == QUOTE:
                return _tencent()
            if url == IFZQ:
                return IFZQ_BODY
            if url == NEWFQ:
                return NEWFQ_BODY
            raise AssertionError(url)

        packet = collect(get)
        self.assertEqual(packet["status"], "已核")
        self.assertEqual(packet["name"], "双创50ETF华宝")
        self.assertEqual(packet["code"], "588330")
        self.assertEqual(packet["session"], "收盘")
        self.assertEqual(packet["px"], 0.718)
        self.assertEqual(packet["pct"], -5.65)
        self.assertEqual(packet["amount_yi"], 1.10)
        self.assertEqual(packet["amount_status"], "已核")
        self.assertEqual(packet["bars"][-1]["high"], 0.748)
        self.assertEqual(packet["bars"][-1]["amount_yi"], 1.10)
        self.assertIn("0.718", packet["text"])
        self.assertNotIn("0.72，", packet["text"])
        self.assertEqual(packet["weights"], "不进W1–W8")
        self.assertEqual(packet["cushion"], "不进托住")

    def test_volume_is_not_turnover(self) -> None:
        def get(url: str) -> str:
            if url == QUOTE:
                return _tencent()
            if url == IFZQ:
                return IFZQ_BODY
            if url == NEWFQ:
                raise TimeoutError("dead")
            raise AssertionError(url)

        packet = collect(get)
        self.assertIsNone(packet["bars"][-1]["amount_yi"])
        self.assertEqual(packet["amount_yi"], 1.10)

    def test_eastmoney_fund_price_uses_thousandths(self) -> None:
        from astock.csi300 import DUAL50

        parsed = parse_eastmoney_quote(
            json.dumps(
                {
                    "data": {
                        "f43": 718,
                        "f44": 748,
                        "f45": 711,
                        "f46": 742,
                        "f48": 110357741.0,
                        "f57": "588330",
                        "f58": "双创50ETF华宝",
                        "f60": 761,
                        "f170": -565,
                        "f86": 1763280893,
                    }
                }
            ),
            DUAL50,
        )
        self.assertEqual(parsed["px"], 0.718)
        self.assertEqual(parsed["prev"], 0.761)
        self.assertEqual(parsed["vendor_pct"], -5.65)
        self.assertEqual(parsed["amount_yi"], 1.10)

    def test_store_uses_the_fund_name(self) -> None:
        def get(url: str) -> str:
            if url == QUOTE:
                return _tencent()
            if url == IFZQ:
                return IFZQ_BODY
            if url == NEWFQ:
                return NEWFQ_BODY
            raise AssertionError(url)

        packet = collect(get)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            written = store(packet, root)
            saved = json.loads(Path(written["snapshot"]).read_text(encoding="utf-8"))
            bars = json.loads((root / "bars" / "588330.json").read_text(encoding="utf-8"))
            kept = store({"status": "未挂", "name": "双创50ETF华宝", "code": "588330", "bars": []}, root)
        self.assertTrue(written["snapshot"].endswith("双创50ETF华宝.json"))
        self.assertEqual(saved["名称"], "双创50ETF华宝")
        self.assertEqual(saved["托住"], "不进托住")
        self.assertEqual(bars[-1]["close"], 0.718)
        self.assertEqual(kept["snapshot"], "保留上一份")


if __name__ == "__main__":
    unittest.main()
