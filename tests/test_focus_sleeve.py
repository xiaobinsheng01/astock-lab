import unittest

from astock.focus_sleeve import cap_state, rank_rows, theme_state


class ThemeTest(unittest.TestCase):
    def test_five_names_do_not_qualify(self):
        self.assertEqual(theme_state(5, 5), "不成立")

    def test_fifteen_at_one_and_a_half(self):
        self.assertEqual(theme_state(15, 10), "只数够")
        self.assertEqual(theme_state(15, 11), "不成立")

    def test_missing_count(self):
        self.assertEqual(theme_state(None, 0), "未核")


class CapTest(unittest.TestCase):
    def test_six_hundred_stays_out(self):
        self.assertEqual(cap_state(599.99), "pass")
        self.assertEqual(cap_state(600), "fail")
        self.assertEqual(cap_state(None), "unchecked")


class RankTest(unittest.TestCase):
    def test_profit_then_the_ten_day_line(self):
        rows = [
            {"code": "600001", "cap": "pass", "near": "pass", "holder": "simple", "earnings": "pass", "profit": 1, "profit_yoy": 1, "ma10_gap_pct": 2},
            {"code": "600002", "cap": "pass", "near": "pass", "holder": "simple", "earnings": "pass", "profit": 5, "profit_yoy": 1, "ma10_gap_pct": -1},
            {"code": "600003", "cap": "fail", "near": "pass", "holder": "simple", "earnings": "pass", "profit": 9, "profit_yoy": 1, "ma10_gap_pct": -4},
            {"code": "002081", "cap": "pass", "near": "pass", "holder": "simple", "earnings": "pass", "profit": 8, "profit_yoy": 1, "ma10_gap_pct": 0},
        ]
        self.assertEqual([row["code"] for row in rank_rows(rows)], ["600002", "600001"])


if __name__ == "__main__":
    unittest.main()
