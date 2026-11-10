import unittest

from astock.event_card import event_destination


class CardTest(unittest.TestCase):
    def test_unmatched_statistic_stays_filed(self):
        text = "中国证券报引国家统计局，10月CPI环比持平，同比上涨0.7%。"
        self.assertEqual(event_destination("中证网", text, official_matched=False), "留档")

    def test_matched_statistic_enters_the_weight(self):
        text = "据国家统计局，10月CPI同比上涨0.7%。"
        self.assertEqual(event_destination("财联社", text, official_matched=True), "权重")

    def test_cailian_quote_stays_filed(self):
        self.assertEqual(event_destination("财联社", "日经225现涨3.0%，报60563.11点。"), "留档")

    def test_sector_etf_is_observation(self):
        self.assertEqual(event_destination("腾讯行情", "SOXX +7.49%", "us_sector"), "观察")

    def test_reprint_stays_filed(self):
        self.assertEqual(event_destination("财联社", "据财政部网站", "转载"), "留档")


if __name__ == "__main__":
    unittest.main()
