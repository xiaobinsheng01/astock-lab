import unittest

from astock.etf_volume import anomaly, classify_amount, volume_state


class VolumeStateTest(unittest.TestCase):
    def test_edges(self):
        self.assertEqual(volume_state(1.30), "放量")
        self.assertEqual(volume_state(1.299), "平量")
        self.assertEqual(volume_state(0.70), "缩量")
        self.assertEqual(volume_state(0.701), "平量")
        self.assertEqual(volume_state(None), "未核")


class AnomalyTest(unittest.TestCase):
    def test_wide_never_names_an_industry(self):
        self.assertEqual(anomaly("wide", "000300", 3.0, 0.3, "放量"), "宽基")

    def test_expand_then_the_index(self):
        self.assertEqual(anomaly("sector", "399998", 1.32, 0.32, "放量"), "异动偏多")
        self.assertEqual(anomaly("sector", "399998", 1.20, 0.32, "放量"), "有量无异动")
        self.assertEqual(anomaly("sector", "399808", -1.0, 0.32, "放量"), "异动偏空")
        self.assertEqual(anomaly("sector", "399808", -0.99, 0.32, "放量"), "有量无异动")

    def test_flat_or_shrink_drops_the_move(self):
        self.assertEqual(anomaly("sector", "399998", 3.0, 0.3, "平量"), "不写异动")
        self.assertEqual(anomaly("sector", "399808", -2.0, 0.3, "缩量"), "不写异动")
        self.assertEqual(anomaly("sector", "399998", None, 0.3, "放量"), "未核")
        self.assertEqual(anomaly("sector", "", 3.0, 0.3, "放量"), "不写异动")


class AmountTest(unittest.TestCase):
    def test_ratio_uses_the_quote_after_the_bar_matches(self):
        bars = [(f"2026-11-0{i}", 100000.0) for i in range(3, 8)]
        bars.append(("2026-11-09", 130000.0))
        row = classify_amount(bars, "2026-11-09", 13.0)
        self.assertEqual(row["state"], "放量")
        self.assertAlmostEqual(row["ratio"], 1.30)

    def test_mismatch_stays_unchecked(self):
        bars = [(f"2026-11-0{i}", 100000.0) for i in range(4, 9)]
        bars.append(("2026-11-09", 130000.0))
        self.assertEqual(classify_amount(bars, "2026-11-09", 14.0)["state"], "未核")

    def test_short_history_stays_unchecked(self):
        bars = [("2026-11-09", 130000.0)]
        self.assertEqual(classify_amount(bars, "2026-11-09", 13.0)["state"], "未核")


if __name__ == "__main__":
    unittest.main()
