#!/usr/bin/env python3
"""A股交易员角色的 claim 草稿与校验。全部离线，不联网。

重点测三件事：缺数时格子空着而不是给默认方向；草稿和 `forecast` 用同一套准入
规则，不分叉；校验通过的草稿，`predict` 一定收得下。
"""

from __future__ import annotations

import unittest

from astock.forecast import validate
from astock.trader import SLOTS, check, draft, slot_prompt

DAY = "2026-11-26"


def quotes(**over) -> dict:
    base = {
        "000001": {
            "px": 3485.36,
            "pct": 0.24,
            "prev_high": 3520.0,
            "prev_low": 3440.0,
        }
    }
    base.update(over)
    return base


def sectors(**over) -> dict:
    base = {
        "有色金属": {"pct": 1.87, "pick": "仅进攻"},
        "银行": {"pct": 0.91, "pick": "仅防御"},
        "电子": {"pct": 0.82, "pick": "仅进攻"},
    }
    base.update(over)
    return base


class SlotPromptTest(unittest.TestCase):
    def test_every_slot_has_a_read(self) -> None:
        payload = slot_prompt(DAY)
        self.assertEqual([item["slot"] for item in payload["slots"]], list(SLOTS))
        for item in payload["slots"]:
            self.assertTrue(item["read"])

    def test_the_prompt_carries_the_wave_and_check_rules(self) -> None:
        """波浪不做成 check、没有核对条件不写，这两条必须在提示里说死。"""
        text = " ".join(slot_prompt(DAY)["rules"])
        self.assertIn("波浪", text)
        self.assertIn("核对条件", text)


class DraftTest(unittest.TestCase):
    def test_missing_quote_leaves_the_slot_empty(self) -> None:
        """没数就不给方向。猜一个方向比留空更糟。"""
        payload = draft(as_of=DAY, name="上证", quotes={}, sectors={}, breadth=None)
        self.assertEqual(payload["claims"], [])
        self.assertEqual(payload["missing"], list(SLOTS))

    def test_direction_follows_the_quote(self) -> None:
        payload = draft(as_of=DAY, name="上证", quotes=quotes())
        slot = {item["slot"]: item for item in payload["claims"]}
        self.assertEqual(slot["index_dir"]["checks"][0]["want"], "up")

    def test_zone_uses_prior_day_high_and_low(self) -> None:
        # 前高 3520、前低 3440，中点 3480，现价 3485.36 落在硬区间上半段。
        payload = draft(as_of=DAY, name="上证", quotes=quotes())
        slot = {item["slot"]: item for item in payload["claims"]}
        self.assertEqual(slot["index_path"]["checks"][0]["want"], "hard_upper")

    def test_no_prior_band_means_no_path_claim(self) -> None:
        """没有上一交易日高低点就不写主路径，不拿当日高低点顶替。"""
        payload = draft(
            as_of=DAY,
            name="上证",
            quotes={"000001": {"px": 3485.36, "pct": 0.24}},
        )
        self.assertIn("index_path", payload["missing"])

    def test_sector_strong_needs_a_one_point_gap(self) -> None:
        # 上证 +0.24%，有色 +1.87%，差 1.63 个百分点 ≥ 1，算强。
        payload = draft(as_of=DAY, name="上证", quotes=quotes(), sectors=sectors())
        slot = {item["slot"]: item for item in payload["claims"]}
        self.assertEqual(slot["sector_strong"]["checks"][0]["sector"], "有色金属")
        self.assertEqual(slot["sector_strong"]["checks"][0]["margin_pp"], 1.0)

    def test_a_sector_below_the_gap_is_not_named(self) -> None:
        # 电子 +0.82% 与上证 +0.24% 只差 0.58 个百分点，差不到 1，不写。
        payload = draft(
            as_of=DAY,
            name="上证",
            quotes=quotes(),
            sectors={"电子": {"pct": 0.82, "pick": "仅进攻"}},
        )
        self.assertIn("sector_strong", payload["missing"])

    def test_sector_state_only_takes_judged_picks(self) -> None:
        payload = draft(
            as_of=DAY,
            name="上证",
            quotes=quotes(),
            sectors={
                "有色金属": {"pct": 1.87, "pick": "仅进攻"},
                "某行业": {"pct": 0.5, "pick": "未核"},
            },
        )
        slot = {item["slot"]: item for item in payload["claims"]}
        named = [item["sector"] for item in slot["sector_state"]["checks"]]
        self.assertIn("有色金属", named)
        self.assertNotIn("某行业", named)

    def test_breadth_becomes_a_risk_claim(self) -> None:
        payload = draft(as_of=DAY, name="上证", quotes=quotes(), breadth=0.42)
        slot = {item["slot"]: item for item in payload["claims"]}
        self.assertEqual(slot["risk"]["checks"][0]["kind"], "breadth")

    def test_volume_slot_is_never_auto_filled(self) -> None:
        """量价四态要看日线，取数包里没有就不写，不拿涨跌方向冒充。"""
        payload = draft(as_of=DAY, name="上证", quotes=quotes(), sectors=sectors())
        self.assertIn("volume", payload["missing"])


class CheckTest(unittest.TestCase):
    def test_every_drafted_slot_passes_forecast_validation(self) -> None:
        """草稿和 forecast 共用同一套准入规则，不能分叉。"""
        payload = draft(
            as_of=DAY,
            name="上证",
            quotes=quotes(),
            sectors=sectors(),
            breadth=0.42,
        )
        for claim in payload["claims"]:
            record = {
                "date": DAY,
                "name": "上证",
                "checks": claim["checks"],
            }
            self.assertEqual(validate(record), [], msg=claim["slot"])

    def test_empty_draft_is_refused(self) -> None:
        result = check({"as_of": DAY, "name": "上证", "claims": []})
        self.assertFalse(result["ok"])
        self.assertTrue(result["problems"])

    def test_unknown_slot_is_refused(self) -> None:
        result = check(
            {
                "as_of": DAY,
                "name": "上证",
                "claims": [{"slot": "vibes", "checks": [{"kind": "breadth", "want": 0.5}]}],
            }
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any("slot" in item for item in result["problems"]))

    def test_a_slot_without_a_check_is_refused(self) -> None:
        result = check(
            {"as_of": DAY, "name": "上证", "claims": [{"slot": "index_dir", "checks": []}]}
        )
        self.assertFalse(result["ok"])

    def test_accepted_records_are_ready_for_predict(self) -> None:
        payload = draft(
            as_of=DAY,
            name="上证",
            quotes=quotes(),
            sectors=sectors(),
            breadth=0.42,
        )
        result = check(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["accepted"]), len(payload["claims"]))
        for item in result["accepted"]:
            self.assertIn(".", item["record"]["name"])


if __name__ == "__main__":
    unittest.main()
