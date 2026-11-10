import unittest

from astock.cls_feed import beijing_clock, sign, telegraph_rows


class SignTest(unittest.TestCase):
    def test_sorted_query_is_stable(self):
        params = {"rn": "20", "app": "CailianpressWeb", "os": "web", "sv": "8.7.9"}
        self.assertEqual(sign(params), sign(dict(reversed(list(params.items())))))
        self.assertEqual(len(sign(params)), 32)


class ClockTest(unittest.TestCase):
    def test_unix_is_beijing(self):
        self.assertEqual(beijing_clock(1794268800), "2026-11-10 08:00")


class RowTest(unittest.TestCase):
    def _item(self, item_id, content, title="", ctime=1794269790):
        return {"id": item_id, "ctime": ctime, "content": content, "title": title, "is_ad": 0}

    def test_own_flash_is_raw_material(self):
        rows = telegraph_rows(
            [self._item(1, "财联社11月10日电，日经225指数涨幅扩大，现涨3.0%，最新报60563.11点。")],
            "",
        )
        self.assertEqual(rows[0]["status"], "原料")
        self.assertFalse(rows[0]["weight"])
        self.assertEqual(rows[0]["url"], "https://www.cls.cn/detail/1")

    def test_official_citation_is_a_reprint(self):
        rows = telegraph_rows(
            [self._item(2, "财联社11月10日电，据财政部网站，对话于11月8日至9日举行。", title="第二次中加经济财金战略对话")],
            "",
        )
        self.assertEqual(rows[0]["status"], "转载")

    def test_comment_product_stays_out(self):
        rows = telegraph_rows([self._item(3, "盘中宝：机器人方向早盘走强。", title="盘中宝机器人")], "")
        self.assertEqual(rows[0]["status"], "不进W1–W5")

    def test_known_address_is_dropped(self):
        rows = telegraph_rows(
            [self._item(4, "财联社11月10日电，上证指数报3660点。")],
            "https://www.cls.cn/detail/4",
        )
        self.assertEqual(rows, [])

    def test_older_than_cursor_is_a_gap(self):
        rows = telegraph_rows(
            [self._item(5, "财联社11月10日电，上证指数报3660点。", ctime=1794240000)],
            "",
            cursor="2026-11-10 08:00",
        )
        self.assertEqual(rows[0]["status"], "缺口")


if __name__ == "__main__":
    unittest.main()
