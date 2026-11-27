#!/usr/bin/env python3
"""结构化预测、结算与记分板。全部离线，不联网。

重点测三件事：写不出核对条件的句子收不下；缺数据判 unchecked 而不是 miss；
已经结算的记录不会被后来的行情改写。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astock.forecast import (
    HIT,
    MISS,
    UNCHECKED,
    judge_breadth,
    judge_pct,
    judge_pick,
    judge_quote_above,
    judge_sector_vs_index,
    judge_zone,
    read_forecasts,
    resolve_all,
    resolve_record,
    scoreboard,
    summarize,
    validate,
    write_forecast,
)


def day_packet(**over) -> dict:
    base = {
        "date": "2026-11-26",
        "quotes": {
            "000001": {"px": 3476.88, "pct": -0.35, "high": 3500.0, "low": 3450.0},
            "399006": {"px": 2100.0, "pct": -1.2, "high": 2130.0, "low": 2090.0},
        },
        "prev": {
            "000001": {"high": 3520.0, "low": 3440.0},
        },
        "sectors": {
            "有色金属": {"pct": 1.87, "pick": "仅进攻"},
            "银行": {"pct": 0.91, "pick": "仅防御"},
        },
        "breadth": 0.42,
    }
    base.update(over)
    return base


class ValidateTest(unittest.TestCase):
    def test_a_sentence_without_a_check_is_rejected(self) -> None:
        """规则原文：写不出核对条件的句子不算预测。"""
        problems = validate({"date": "2026-11-26", "name": "上证"})
        self.assertTrue(any("checks" in item for item in problems))

    def test_missing_name_is_rejected(self) -> None:
        problems = validate(
            {"date": "2026-11-26", "checks": [{"kind": "breadth", "want": 0.5}]}
        )
        self.assertTrue(any("name" in item for item in problems))

    def test_unknown_kind_is_rejected(self) -> None:
        """收下来却永远核不了的话，比没写更糟。"""
        problems = validate(
            {
                "date": "2026-11-26",
                "name": "上证",
                "checks": [{"kind": "vibes", "want": "up"}],
            }
        )
        self.assertTrue(any("kind" in item for item in problems))

    def test_a_check_without_want_is_rejected(self) -> None:
        problems = validate(
            {"date": "2026-11-26", "name": "上证", "checks": [{"kind": "index_pct", "code": "000001"}]}
        )
        self.assertTrue(any("want" in item for item in problems))

    def test_sector_vs_index_needs_a_margin(self) -> None:
        problems = validate(
            {
                "date": "2026-11-26",
                "name": "发力板块",
                "checks": [{"kind": "sector_vs_index", "sector": "电子", "want": True}],
            }
        )
        self.assertTrue(any("margin_pp" in item for item in problems))

    def test_a_good_record_passes(self) -> None:
        record = {
            "date": "2026-11-26",
            "name": "上证",
            "checks": [
                {"kind": "index_pct", "code": "000001", "want": "down"},
                {"kind": "index_zone", "want": "narrow_lower"},
                {"kind": "breadth", "want": 0.5},
            ],
        }
        self.assertEqual(validate(record), [])

    def test_more_than_six_checks_is_rejected(self) -> None:
        record = {
            "date": "2026-11-26",
            "name": "上证",
            "checks": [{"kind": "breadth", "want": 0.5}] * 7,
        }
        self.assertTrue(any("最多" in item for item in validate(record)))


class WriteForecastTest(unittest.TestCase):
    def test_a_bad_record_does_not_half_write(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "forecasts.jsonl"
            with self.assertRaises(ValueError):
                write_forecast({"date": "2026-11-26", "name": "上证"}, path=path)
            self.assertFalse(path.exists())

    def test_good_record_is_appended(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "forecasts.jsonl"
            record = {
                "date": "2026-11-26",
                "name": "上证",
                "checks": [{"kind": "index_pct", "code": "000001", "want": "down"}],
            }
            write_forecast(record, path=path)
            write_forecast(record, path=path)
            self.assertEqual(len(read_forecasts(path)), 2)

    def test_wave_text_is_kept_but_not_scored(self) -> None:
        """波浪只写文字，存下来给复盘读，结算和记分板都不看它。"""
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "forecasts.jsonl"
            record = {
                "date": "2026-11-26",
                "name": "上证",
                "wave": "周线级别第 3 浪的回调",
                "checks": [{"kind": "index_pct", "code": "000001", "want": "down"}],
            }
            stored = write_forecast(record, path=path)
            self.assertEqual(stored["wave"], "周线级别第 3 浪的回调")
            day = day_packet()
            result = resolve_record(stored, day)
            self.assertNotIn("wave", json.dumps(result["resolution"]))


class JudgeTest(unittest.TestCase):
    def test_missing_data_is_unchecked_not_miss(self) -> None:
        """没数据不等于错。这条是结算的地基。"""
        self.assertEqual(judge_pct(None, "down"), UNCHECKED)
        self.assertEqual(judge_zone(None, 10.0, 20.0, "hard_upper"), UNCHECKED)
        self.assertEqual(judge_quote_above(None, 10.0), UNCHECKED)
        self.assertEqual(judge_sector_vs_index(None, 1.0, 1.0, True), UNCHECKED)
        self.assertEqual(judge_breadth(None, 0.5), UNCHECKED)
        self.assertEqual(judge_pick(None, "主线"), UNCHECKED)

    def test_pct_directions(self) -> None:
        self.assertEqual(judge_pct(-0.35, "down"), HIT)
        self.assertEqual(judge_pct(-0.35, "up"), MISS)
        self.assertEqual(judge_pct(0.0, "flat"), HIT)
        self.assertEqual(judge_pct(0.0, "up"), MISS)

    def test_zone_uses_the_same_boundaries_as_session_path(self) -> None:
        # 低点 3440、高点 3520，中点 3480。
        self.assertEqual(judge_zone(3476.88, 3440.0, 3520.0, "narrow_lower"), HIT)
        self.assertEqual(judge_zone(3500.0, 3440.0, 3520.0, "hard_upper"), HIT)
        self.assertEqual(judge_zone(3530.0, 3440.0, 3520.0, "above_hard"), HIT)
        self.assertEqual(judge_zone(3400.0, 3440.0, 3520.0, "below_hard"), HIT)
        self.assertEqual(judge_zone(3476.88, 3440.0, 3520.0, "hard_upper"), MISS)

    def test_quote_above_is_strict(self) -> None:
        self.assertEqual(judge_quote_above(10.01, 10.0), HIT)
        self.assertEqual(judge_quote_above(10.0, 10.0), MISS)

    def test_sector_vs_index_respects_the_margin(self) -> None:
        # 行业 +1.87%，上证 -0.35%，差 2.22 个百分点。
        self.assertEqual(judge_sector_vs_index(1.87, -0.35, 1.0, True), HIT)
        self.assertEqual(judge_sector_vs_index(1.87, -0.35, 3.0, True), MISS)
        self.assertEqual(judge_sector_vs_index(1.87, -0.35, 3.0, False), HIT)

    def test_breadth_threshold_is_inclusive(self) -> None:
        self.assertEqual(judge_breadth(0.5, 0.5), HIT)
        self.assertEqual(judge_breadth(0.49, 0.5), MISS)


class SummarizeTest(unittest.TestCase):
    def test_all_hit_is_a_hit(self) -> None:
        out = summarize([{"result": HIT}, {"result": HIT}])
        self.assertEqual(out["state"], HIT)

    def test_one_miss_is_not_a_hit(self) -> None:
        out = summarize([{"result": HIT}, {"result": MISS}])
        self.assertEqual(out["state"], "partial")
        self.assertEqual(out["miss"], 1)

    def test_all_missing_data_is_unchecked(self) -> None:
        out = summarize([{"result": UNCHECKED}, {"result": UNCHECKED}])
        self.assertEqual(out["state"], UNCHECKED)

    def test_all_miss_is_a_miss(self) -> None:
        self.assertEqual(summarize([{"result": MISS}])["state"], MISS)

    def test_hit_plus_unchecked_is_partial_not_hit(self) -> None:
        """有一条没核上，就不能说这条预测全中。"""
        out = summarize([{"result": HIT}, {"result": UNCHECKED}])
        self.assertEqual(out["state"], "partial")


class ResolveTest(unittest.TestCase):
    def _record(self, checks):
        return {"date": "2026-11-26", "name": "上证", "written_at": "2026-11-26 09:10", "checks": checks}

    def test_record_is_judged_against_the_day(self) -> None:
        record = self._record(
            [
                {"kind": "index_pct", "code": "000001", "want": "down"},
                {"kind": "sector_vs_index", "sector": "有色金属", "margin_pp": 1.0, "want": True},
                {"kind": "industry_pick", "sector": "银行", "want": "仅防御"},
            ]
        )
        done = resolve_record(record, day_packet())
        self.assertEqual(done["resolution"]["summary"]["state"], HIT)
        self.assertEqual(len(done["resolution"]["results"]), 3)

    def test_original_record_is_not_mutated(self) -> None:
        record = self._record([{"kind": "index_pct", "code": "000001", "want": "down"}])
        resolve_record(record, day_packet())
        self.assertNotIn("resolution", record)

    def test_a_missing_sector_is_unchecked(self) -> None:
        record = self._record([{"kind": "sector_pct", "sector": "美容护理", "want": "up"}])
        done = resolve_record(record, day_packet())
        self.assertEqual(done["resolution"]["summary"]["state"], UNCHECKED)

    def test_resolve_does_not_reopen_a_settled_record(self) -> None:
        """预测写下那一刻的话，不能被后来的行情改写。"""
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "forecasts.jsonl"
            write_forecast(
                self._record([{"kind": "index_pct", "code": "000001", "want": "down"}]),
                path=path,
            )
            first = resolve_all(day_packet(), path=path)
            self.assertEqual(first["resolved"], 1)
            # 第二天上证涨了，已经结算的那条不该翻案。
            later = day_packet(
                date="2026-11-27",
                quotes={"000001": {"px": 3600.0, "pct": 3.0, "high": 3600.0, "low": 3480.0}},
            )
            second = resolve_all(later, path=path)
            self.assertEqual(second["resolved"], 0)
            stored = read_forecasts(path)
            self.assertEqual(stored[0]["resolution"]["results"][0]["result"], HIT)

    def test_future_dated_record_is_not_settled(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "forecasts.jsonl"
            write_forecast(
                {
                    "date": "2026-12-01",
                    "name": "上证",
                    "checks": [{"kind": "index_pct", "code": "000001", "want": "down"}],
                },
                path=path,
            )
            out = resolve_all(day_packet(), path=path)
            self.assertEqual(out["resolved"], 0)

    def test_unresolvable_record_stays_open_rather_than_becoming_miss(self) -> None:
        """一条都判不出来时留着等数据，不写成终局。"""
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "forecasts.jsonl"
            write_forecast(
                self._record([{"kind": "sector_pct", "sector": "查无此行业", "want": "up"}]),
                path=path,
            )
            out = resolve_all(day_packet(), path=path)
            self.assertEqual(out["resolved"], 0)
            self.assertNotIn("resolution", read_forecasts(path)[0])


class ScoreboardTest(unittest.TestCase):
    def _settled(self, name, results, date="2026-11-26"):
        return {
            "date": date,
            "name": name,
            "checks": [{"kind": "breadth", "want": 0.5}] * len(results),
            "resolution": {
                "results": [{"result": item} for item in results],
                "summary": summarize([{"result": item} for item in results]),
            },
        }

    def test_unchecked_is_not_in_the_denominator(self) -> None:
        board = scoreboard([self._settled("上证", [HIT, UNCHECKED])])
        row = board["rows"][0]
        self.assertEqual(row["judged"], 1)
        self.assertEqual(row["rate"], 1.0)
        self.assertEqual(row["unchecked"], 1)

    def test_unsettled_records_do_not_count(self) -> None:
        board = scoreboard([{"date": "2026-11-26", "name": "上证", "checks": []}])
        self.assertEqual(board["rows"], [])
        self.assertIsNone(board["total"]["rate"])

    def test_names_are_ranked_by_rate(self) -> None:
        board = scoreboard(
            [
                self._settled("甲", [MISS, MISS]),
                self._settled("乙", [HIT, HIT]),
            ]
        )
        self.assertEqual([row["name"] for row in board["rows"]], ["乙", "甲"])
        self.assertAlmostEqual(board["total"]["rate"], 0.5)

    def test_zero_judged_has_no_rate_rather_than_zero_percent(self) -> None:
        """全未核不能写成 0% 命中，那是两件事。"""
        board = scoreboard([self._settled("上证", [UNCHECKED])])
        self.assertIsNone(board["rows"][0]["rate"])


if __name__ == "__main__":
    unittest.main()
