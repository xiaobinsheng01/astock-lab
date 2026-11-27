#!/usr/bin/env python3
"""The book is one file, and every calculator reads it the same way. No network."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import astock.holdings as holdings
from astock.close_inputs import CODES, index_decision, sell_checks, w6_scores
from astock.util import market_prefix, market_symbol, round_half_up, round_pct


def write_book(rows: list[dict], clock: str = "2026-11-26 00:24") -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    with handle as stream:
        json.dump({"状态": "已提供", "北京时间": clock, "持仓": rows}, stream, ensure_ascii=False)
    return Path(handle.name)


class BookTest(unittest.TestCase):
    def test_missing_file_is_an_empty_book(self) -> None:
        missing = Path(tempfile.gettempdir()) / "astock-lab-no-such-book.json"
        self.assertEqual(holdings.book(missing), [])
        self.assertEqual(holdings.codes(missing), [])
        self.assertEqual(holdings.clock(missing), "")

    def test_rows_without_a_code_are_dropped(self) -> None:
        path = write_book([
            {"代码": "000725", "名称": "京东方A"},
            {"名称": "没有代码"},
            {"代码": "000725", "名称": "重复"},
            {"代码": "600327", "名称": "大东方"},
        ])
        self.assertEqual(holdings.codes(path), ["000725", "600327"])

    def test_broken_json_is_an_empty_book_not_a_crash(self) -> None:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        with handle as stream:
            stream.write("{not json")
        self.assertEqual(holdings.book(Path(handle.name)), [])

    def test_the_real_book_is_the_seven_named_positions(self) -> None:
        # The checked-in book is the single source of truth for the desk.
        self.assertEqual(
            holdings.codes(),
            ["000725", "002081", "000559", "601061", "600715", "600327", "601188"],
        )
        self.assertEqual(holdings.clock(), "2026-11-26 00:24")

    def test_hard_gate_is_the_four_the_rules_name(self) -> None:
        # A held name is not automatically blocked; only these four are.
        self.assertEqual(set(holdings.HARD_GATE), {"002081", "601061", "000559", "601868"})


class RoundingTest(unittest.TestCase):
    def test_half_up_not_bankers(self) -> None:
        self.assertEqual(round_half_up(0.5), 1)
        self.assertEqual(round_half_up(1.5), 2)
        self.assertEqual(round_half_up(2.5), 3)
        self.assertEqual(round_half_up(-0.5), -1)
        self.assertEqual(round_half_up(-2.5), -3)
        self.assertEqual(round_half_up(0.49), 0)

    def test_w6_average_is_half_up(self) -> None:
        # Four scored dims averaging exactly +0.5 must land on +1, not 0.
        # breadth +1, limit 0, premium 0, height +1, no volume dim.
        scored = w6_scores(
            breadth_ratio=0.70,
            limit_up=30,
            limit_down=5,
            broken_ratio=0.30,
            premium=0.0,
            height=4,
            volume_ratio=None,
        )
        self.assertEqual(scored["scored_n"], 4)
        self.assertEqual(scored["dims"]["breadth"], 1)
        self.assertEqual(scored["dims"]["limit"], 0)
        self.assertEqual(scored["dims"]["premium"], 0)
        self.assertEqual(scored["dims"]["height"], 1)
        # sum = 2 over 4 dims = +0.5 → +1 under 四舍五入, 0 under bankers' rounding.
        self.assertEqual(scored["composite"], 1)

    def test_w6_negative_half_rounds_away_from_zero(self) -> None:
        # breadth 0, limit -1, premium -1, height 0 → -0.5 → -1, not 0.
        scored = w6_scores(
            breadth_ratio=0.50,
            limit_up=15,
            limit_down=5,
            broken_ratio=0.30,
            premium=-0.02,
            height=2,
            volume_ratio=None,
        )
        self.assertEqual(
            scored["dims"],
            {"breadth": 0, "limit": -1, "premium": -1, "height": 0},
        )
        self.assertEqual(scored["composite"], -1)

    def test_round_pct_is_half_up(self) -> None:
        self.assertEqual(round_pct(0.005), 0.01)
        self.assertEqual(round_pct(-0.005), -0.01)


class MarketSymbolTest(unittest.TestCase):
    def test_exchange_prefix(self) -> None:
        self.assertEqual(market_symbol("000001"), "sh000001")
        self.assertEqual(market_symbol("000725"), "sz000725")
        self.assertEqual(market_symbol("600327"), "sh600327")
        self.assertEqual(market_symbol("601188"), "sh601188")
        self.assertEqual(market_symbol("399811"), "sz399811")
        self.assertEqual(market_symbol("588330"), "sh588330")
        self.assertEqual(market_prefix("000993"), "sh")


class QuoteBasketTest(unittest.TestCase):
    def test_every_held_code_is_quoted(self) -> None:
        for code in holdings.codes():
            self.assertIn(market_symbol(code), CODES)

    def test_no_duplicates(self) -> None:
        self.assertEqual(len(CODES), len(set(CODES)))


class SellChecksTest(unittest.TestCase):
    def test_gate_flags_survive_the_refactor(self) -> None:
        quotes = {
            "002081": {"open": 3.90, "high": 4.10, "low": 3.95, "px": 4.05, "pct": 1.0},
            "601061": {"open": 9.40, "high": 9.50, "low": 9.30, "px": 9.45, "pct": -1.0},
            "000559": {"px": 9.80, "pct": -2.0},
        }
        rows = sell_checks(quotes)
        self.assertTrue(rows["002081"]["open_at_or_above_3_88"])
        self.assertTrue(rows["002081"]["traded_through_3_88_4_00"])
        self.assertTrue(rows["601061"]["close_below_9_55"])
        self.assertTrue(rows["601061"]["high_below_9_55"])

    def test_every_held_name_gets_a_row(self) -> None:
        rows = sell_checks({})
        for code in holdings.codes():
            self.assertIn(code, rows)

    def test_a_name_above_the_gate_is_false(self) -> None:
        rows = sell_checks({"601061": {"px": 9.61, "high": 9.70}})
        self.assertFalse(rows["601061"]["close_below_9_55"])
        self.assertFalse(rows["601061"]["high_below_9_55"])


class DecisionTest(unittest.TestCase):
    def test_only_the_three_named_sentences(self) -> None:
        cases = [
            ({"hedge": "opposite", "down_side": "growth", "bank_cushion": "bank_held",
              "shanghai_pct": -1.0}, "growth_down_bank_held"),
            ({"hedge": "opposite", "down_side": "banks", "bank_cushion": "bank_did_not_hold",
              "shanghai_pct": 1.0, "electronics_pct": 1.2}, "growth_led_rebound"),
            ({"hedge": "same_or_flat", "bank_cushion": "bank_did_not_hold",
              "shanghai_pct": -0.5}, "same_direction_bank_not_held"),
        ]
        for row, expected in cases:
            self.assertEqual(index_decision(row), expected)

    def test_anything_else_gets_no_sentence(self) -> None:
        # Uptrend without an opposite hedge is not one of the three sentences.
        self.assertIsNone(index_decision({
            "hedge": "same_or_flat", "bank_cushion": "bank_held",
            "shanghai_pct": 1.0, "electronics_pct": 1.0,
        }))
        self.assertIsNone(index_decision({"shanghai_pct": 1.0}))
        self.assertIsNone(index_decision({"hedge": "opposite", "shanghai_pct": None}))


if __name__ == "__main__":
    unittest.main()
