#!/usr/bin/env python3
"""技术面与全行业统计。全部离线，不联网。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astock.industry import (
    classify,
    rank,
    returns,
    state_table,
)
from astock.technique import (
    above_all,
    averages,
    cycle,
    hot_concepts,
    thematic,
    volume_read,
    volume_state,
)


class VolumeStateTest(unittest.TestCase):
    def test_four_states(self) -> None:
        cases = [
            (200, 100, 11.0, 10.0, "量增价涨"),
            (50, 100, 11.0, 10.0, "量缩价涨"),
            (200, 100, 9.0, 10.0, "量增价跌"),
            (50, 100, 9.0, 10.0, "量缩价跌"),
        ]
        for volume, prev_volume, close, prev_close, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    volume_state(volume, prev_volume, close, prev_close)["state"],
                    expected,
                )

    def test_volume_just_above_the_tolerance_is_a_signal_when_price_moves(self) -> None:
        """量能超出 3% 容差就是信号，不因为「差得不多」被并成持平。"""
        self.assertEqual(volume_state(104, 100, 11.0, 10.0)["state"], "量增价涨")

    def test_a_rise_just_past_the_price_tolerance_is_a_signal(self) -> None:
        """价和量分开留容差：涨过 3% 就是信号，缩量时写成量缩价涨。

        规则里量平、价平各留 3%（`rules/08-portrait.md`），所以 3.5% 才算离开
        价平这一格。
        """
        self.assertEqual(volume_state(80, 100, 10.35, 10.0)["state"], "量缩价涨")

    def test_flat_price_is_not_force_fit_into_a_cell(self) -> None:
        self.assertEqual(volume_state(200, 100, 10.0, 10.0)["state"], "量价持平")

    def test_price_inside_tolerance_is_flat(self) -> None:
        self.assertEqual(volume_state(200, 100, 10.1, 10.0)["state"], "量价持平")

    def test_industry_tolerance_keeps_the_four_states_apart(self) -> None:
        """行业等权指数单日振幅被抹平，用个股的 3% 会让整张表清一色持平。

        实测行业单日中位涨跌约 0.9%，最大的行业也只到 2.5%。行业按 1% 留容差，
        涨 1.9% 就该写成量增价涨，而不是跟 30 个行业一起并成持平。
        """
        self.assertEqual(
            volume_state(200, 100, 10.19, 10.0)["state"], "量价持平"
        )
        self.assertEqual(
            volume_state(200, 100, 10.19, 10.0, price_flat=0.01)["state"], "量增价涨"
        )

    def test_missing_volume_is_unchecked_not_zero(self) -> None:
        out = volume_state(None, 100, 11.0, 10.0)
        self.assertEqual(out["state"], "未核")
        self.assertNotIn("vol_ratio", out)

    def test_missing_previous_close_is_unchecked(self) -> None:
        self.assertEqual(volume_state(200, 100, 11.0, None)["state"], "未核")

    def test_every_state_has_a_read(self) -> None:
        for state in ("量增价涨", "量缩价涨", "量增价跌", "量缩价跌", "量价持平"):
            self.assertNotEqual(volume_read(state), "未核，不读。")
        self.assertEqual(volume_read("未知"), "未核，不读。")


class AverageTest(unittest.TestCase):
    def test_window_shorter_than_needed_is_unchecked(self) -> None:
        bars = [{"close": float(px)} for px in range(1, 11)]
        table = averages(bars, (5, 10, 20, 60))
        self.assertEqual(table["ma5"]["state"], "已核")
        self.assertEqual(table["ma10"]["state"], "已核")
        self.assertEqual(table["ma20"]["state"], "未核")
        self.assertIsNone(table["ma20"]["ma"])

    def test_average_and_distance(self) -> None:
        bars = [{"close": float(px)} for px in (10, 10, 10, 10, 12)]
        table = averages(bars, (5,))
        self.assertAlmostEqual(table["ma5"]["ma"], 10.4)
        self.assertAlmostEqual(table["ma5"]["dist"], 12 / 10.4 - 1.0)

    def test_non_positive_window_is_not_counted_as_above(self) -> None:
        """A window with no data must not be reported as 站上."""
        bars = [{"close": float(px)} for px in range(1, 11)]
        out = above_all(bars, (5, 20))
        self.assertEqual(out["checked"], 1)
        self.assertEqual(out["above"], 1)
        self.assertEqual(out["state"], "站上全部")

    def test_nothing_checked_is_unchecked(self) -> None:
        self.assertEqual(above_all([], (20,))["state"], "未核")


class IndustryTableTest(unittest.TestCase):
    def test_every_sw_level1_industry_is_covered(self) -> None:
        """全部行业 means 31, not 4 and not a merged subset."""
        from astock.industry import SW_LEVEL1

        self.assertEqual(len(SW_LEVEL1), 31)
        for name, board in SW_LEVEL1.items():
            self.assertTrue(board.startswith("pt01"), f"{name} 的板块代码不对：{board}")

    def test_no_two_industries_share_a_board(self) -> None:
        """Two industries on one board would print identical rows."""
        from astock.industry import SW_LEVEL1

        boards = list(SW_LEVEL1.values())
        self.assertEqual(len(boards), len(set(boards)))

    def test_returns_skip_the_first_bar(self) -> None:
        series = [("2026-11-03", 100.0), ("2026-11-04", 110.0), ("2026-11-05", 99.0)]
        table = returns(series)
        self.assertEqual(list(table), ["2026-11-04", "2026-11-05"])
        self.assertAlmostEqual(table["2026-11-04"], 10.0)

    def test_only_days_present_in_both_series_are_used(self) -> None:
        board = {"2026-11-03": 1.0, "2026-11-04": -2.0, "2026-11-05": 3.0}
        index = {"2026-11-04": 1.0, "2026-11-05": -1.0, "2026-11-06": 0.5}
        table = state_table(board, index)
        self.assertEqual(table["days"], 2)
        self.assertEqual(table["up"]["n"], 1)
        self.assertEqual(table["down"]["n"], 1)
        # 11-03 exists only on the board side and must not be counted.
        self.assertEqual(table["up"]["median"], -2.0)
        self.assertEqual(table["down"]["median"], 3.0)

    def test_a_half_with_no_days_is_unchecked_not_zero(self) -> None:
        table = state_table({"2026-11-03": 1.0}, {"2026-11-03": 1.0})
        self.assertEqual(table["down"]["n"], 0)
        self.assertIsNone(table["down"]["median"])
        self.assertEqual(table["down"]["state"], "未核")

    def test_classify_needs_both_halves(self) -> None:
        def half(values):
            if not values:
                return {"n": 0, "median": None, "win": None, "state": "未核"}
            return {"n": len(values), "median": sorted(values)[len(values) // 2], "win": 0.5, "state": "已核"}

        self.assertEqual(classify({"up": half([1.0] * 5), "down": half([0.0] * 30)}), "样本不足")
        self.assertEqual(classify({"up": half([1.0] * 30), "down": half([0.0] * 30)}), "主线")
        self.assertEqual(classify({"up": half([1.0] * 30), "down": half([-1.0] * 30)}), "仅进攻")
        self.assertEqual(classify({"up": half([-1.0] * 30), "down": half([0.0] * 30)}), "仅防御")
        self.assertEqual(classify({"up": half([-1.0] * 30), "down": half([-1.0] * 30)}), "无")

    def test_rank_puts_main_line_first(self) -> None:
        def row(pick, down, up, proxy=False):
            return {"pick": pick, "proxy": proxy, "down": {"median": down}, "up": {"median": up}}

        rows = [row("无", -3, 1), row("主线", 1, 2), row("仅进攻", -1, 3), row("样本不足", None, None)]
        # 样本不足 sits above 无: never measured is not worse than measured and bad.
        self.assertEqual([item["pick"] for item in rank(rows)], ["主线", "仅进攻", "样本不足", "无"])

    def test_equal_weight_averages_only_members_with_data_that_day(self) -> None:
        """一只票停牌不能把整天的均值拉偏，而要用当天有数的成员平均。"""
        from astock import industry

        data = {
            "600001": {"2026-11-03": {"close": 10.0}, "2026-11-04": {"close": 11.0}},
            "600002": {"2026-11-03": {"close": 10.0}, "2026-11-04": {"close": 10.0}},
            "600003": {"2026-11-03": {"close": 10.0}, "2026-11-04": {"close": 10.0}},
            "600004": {"2026-11-03": {"close": 10.0}, "2026-11-04": {"close": 12.0}},
            "600005": {"2026-11-03": {"close": 10.0}, "2026-11-04": {"close": 10.0}},
            "600006": {"2026-11-03": {"close": 10.0}},
        }
        original = industry.member_series
        industry.member_series = lambda code, count=0: data.get(code, {})
        try:
            out = industry.equal_weight_returns(sorted(data), count=5, min_series=5)
        finally:
            industry.member_series = original
        # 04 日只有 5 只有数：(+10% +0% +0% +20% +0%) / 5 = +6%，停牌那只不进分母
        self.assertAlmostEqual(out["2026-11-04"], 6.0)

    def test_too_few_members_is_not_an_industry(self) -> None:
        from astock import industry

        self.assertEqual(industry.equal_weight_returns(["600001", "600002"]), {})

    def test_small_industry_only_needs_half_its_members(self) -> None:
        """申万「综合」只有 19 只成员，一律要 30 只会让它永远算不出来。"""
        from astock import industry

        self.assertEqual(industry.need_series([f"6000{i:02d}" for i in range(19)]), 10)
        self.assertEqual(industry.need_series([f"6000{i:02d}" for i in range(133)]), 30)
        self.assertEqual(industry.need_series(["600001", "600002", "600003"]), 5)


class IndustryFrameVolumeTest(unittest.TestCase):
    """行业那根「日 K」的成交量必须是成员平均量，不能是总和。

    总和会随成员进出凭空跳：某只票停牌一天，总量掉一大截，量价四态读出一根
    不存在的缩量阴线。原来就是这样把有色某天的量比做成 12.9 倍。
    """

    def _run(self, data: dict[str, dict[str, tuple[float, float]]]):
        from astock import industry

        series = {
            code: {day: {"close": px, "volume": vol} for day, (px, vol) in days.items()}
            for code, days in data.items()
        }
        original_many = industry.member_series_many
        original_board = industry.board_members
        industry.member_series_many = lambda codes, count=0: series
        industry.board_members = lambda board, limit=0: sorted(series)
        try:
            return industry.industry_frame("有色金属", count=5, limit=30)
        finally:
            industry.member_series_many = original_many
            industry.board_members = original_board

    def test_volume_is_average_per_member_not_the_sum(self) -> None:
        data = {
            f"6000{i:02d}": {
                "2026-11-03": (10.0, 100.0),
                "2026-11-04": (10.0, 100.0),
            }
            for i in range(10)
        }
        bars = self._run(data)
        # 10 只各 100 手，平均量是 100，不是 1000。
        self.assertAlmostEqual(bars[-1]["volume"], 100.0)

    def test_one_member_going_missing_does_not_look_like_shrinking_volume(self) -> None:
        data = {
            f"6000{i:02d}": {
                "2026-11-03": (10.0, 100.0),
                "2026-11-04": (10.0, 100.0),
            }
            for i in range(10)
        }
        # 一只票 04 日停牌：总和会从 1000 掉到 900，平均量仍然是 100。
        del data["600000"]["2026-11-04"]
        bars = self._run(data)
        self.assertAlmostEqual(bars[-1]["volume"], 100.0)
    def test_a_day_below_the_member_floor_is_dropped(self) -> None:
        data = {
            f"6000{i:02d}": {
                "2026-11-03": (10.0, 100.0),
                "2026-11-04": (10.0, 100.0),
                "2026-11-05": (10.0, 100.0),
            }
            for i in range(10)
        }
        # 05 日只剩 2 只有数：不足 MIN_DAY_MEMBERS，那一天不写；04 日照常写。
        for i in range(2, 10):
            del data[f"6000{i:02d}"]["2026-11-05"]
        bars = self._run(data)
        self.assertEqual([bar["date"] for bar in bars], ["2026-11-04"])


class MemberPickTest(unittest.TestCase):
    """成员怎么挑，决定了这张表算的是不是行业。

    按股价排会挑出小盘高价票，拼出来的是「高价股指数」；必须按流通市值挑头部，
    并剔掉 ST。
    """

    def _payload(self, rows):
        return json.dumps({"data": {"rank_list": rows}}, ensure_ascii=False).encode()

    def test_picks_largest_cap_not_highest_price(self) -> None:
        from astock import industry

        rows = [
            {"code": "sz300835", "name": "龙磁科技", "ltsz": "88.49", "zxj": "107.66"},
            {"code": "sh601899", "name": "紫金矿业", "ltsz": "4893.10", "zxj": "23.75"},
            {"code": "sh600111", "name": "北方稀土", "ltsz": "1117.20", "zxj": "30.90"},
        ]
        original = industry._get
        industry._get = lambda url, **kw: self._payload(rows)
        try:
            picked = industry.board_members("pt01801050", limit=2)
        finally:
            industry._get = original
        self.assertEqual(picked, ["601899", "600111"])

    def test_st_is_not_an_industry_member(self) -> None:
        from astock import industry

        rows = [
            {"code": "sh600001", "name": "*ST某某", "ltsz": "900.0"},
            {"code": "sh600002", "name": "正常股份", "ltsz": "100.0"},
        ]
        original = industry._get
        industry._get = lambda url, **kw: self._payload(rows)
        try:
            picked = industry.board_members("pt01801050", limit=5)
        finally:
            industry._get = original
        self.assertEqual(picked, ["600002"])

    def test_bad_cap_sorts_last_instead_of_crashing(self) -> None:
        from astock import industry

        rows = [
            {"code": "sh600003", "name": "无市值", "ltsz": "-"},
            {"code": "sh600004", "name": "有市值", "ltsz": "50.0"},
        ]
        original = industry._get
        industry._get = lambda url, **kw: self._payload(rows)
        try:
            picked = industry.board_members("pt01801050", limit=5)
        finally:
            industry._get = original
        self.assertEqual(picked, ["600004", "600003"])


class CycleTest(unittest.TestCase):
    def test_one_day_cycle_when_attack_share_is_high(self) -> None:
        rows = [{"pick": "仅进攻"}] * 8 + [{"pick": "主线"}] * 1 + [{"pick": "无"}] * 1
        out = cycle(rows)
        self.assertEqual(out["state"], "一日游居多")
        self.assertAlmostEqual(out["share"], 0.8)

    def test_main_line_cycle_when_attack_share_is_low(self) -> None:
        rows = [{"pick": "主线"}] * 8 + [{"pick": "仅进攻"}] * 1 + [{"pick": "无"}] * 1
        self.assertEqual(cycle(rows)["state"], "主线为主")

    def test_empty_sample_is_unchecked(self) -> None:
        out = cycle([{"pick": "样本不足"}, {"pick": "未核"}])
        self.assertEqual(out["state"], "未核")
        self.assertIsNone(out["share"])

    def test_hot_concepts_sorted_by_up_day_median(self) -> None:
        rows = [
            {"name": "甲", "up": {"median": 0.5}},
            {"name": "乙", "up": {"median": 2.0}},
            {"name": "丙", "up": {"median": None}},
        ]
        self.assertEqual([row["name"] for row in hot_concepts(rows, 2)], ["乙", "甲"])


class ThematicTest(unittest.TestCase):
    def test_new_high_is_detected(self) -> None:
        bars = [{"close": float(px)} for px in (10, 11, 12, 13, 14)]
        out = thematic(bars, window=5)
        self.assertTrue(out["new_high"])
        self.assertAlmostEqual(out["from_high"], 0.0)

    def test_short_series_is_unchecked(self) -> None:
        self.assertEqual(thematic([{"close": 1.0}])["state"], "未核")


if __name__ == "__main__":
    unittest.main()
