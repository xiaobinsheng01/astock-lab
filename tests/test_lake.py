#!/usr/bin/env python3
"""Hot layer and archive. No network."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from astock.lake import finish_final, hot_quote_dates, write_bars, write_news, write_quote, write_result


class HotDateTest(unittest.TestCase):
    def test_weekend_keeps_friday_and_adds_no_session(self) -> None:
        hot = hot_quote_dates(
            ["2026-11-06"],
            today="2026-11-08",
            today_has_open=False,
            final_dates=["2026-11-06"],
        )
        self.assertEqual(hot, ["2026-11-06"])

    def test_next_final_drops_the_previous_session(self) -> None:
        hot = hot_quote_dates(
            ["2026-11-06", "2026-11-09"],
            today="2026-11-09",
            today_has_open=True,
            final_dates=["2026-11-06", "2026-11-09"],
        )
        self.assertEqual(hot, ["2026-11-09"])

    def test_before_monday_final_friday_is_still_hot(self) -> None:
        hot = hot_quote_dates(
            ["2026-11-06", "2026-11-09"],
            today="2026-11-09",
            today_has_open=True,
            final_dates=["2026-11-06"],
        )
        self.assertEqual(hot, ["2026-11-06", "2026-11-09"])


class StoreTest(unittest.TestCase):
    def test_weekend_and_holiday_quotes_are_written(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            friday = write_quote(root, "2026-11-06", {"px": 3600}, today_has_open=True)
            weekend = write_quote(root, "2026-11-08", {"px": 1}, today_has_open=False)
            holiday = write_quote(root, "2026-10-01", {"px": 2}, today_has_open=False)
            self.assertEqual(friday["status"], "已写")
            self.assertFalse(friday["closed"])
            self.assertEqual(weekend["status"], "已写")
            self.assertTrue(weekend["closed"])
            self.assertEqual(holiday["status"], "已写")
            self.assertTrue(holiday["closed"])
            sunday = json.loads((root / "hot" / "quotes" / "2026-11-08.json").read_text(encoding="utf-8"))
            national = json.loads((root / "hot" / "quotes" / "2026-10-01.json").read_text(encoding="utf-8"))
            self.assertEqual(sunday["px"], 1)
            self.assertEqual(national["px"], 2)
            sessions = json.loads((root / "sessions.json").read_text(encoding="utf-8"))
            hot = hot_quote_dates(
                sessions,
                today="2026-11-08",
                today_has_open=False,
                final_dates=["2026-11-06"],
            )
            self.assertEqual(hot, ["2026-11-06", "2026-11-08"])

    def test_news_survives_the_weekend_until_the_next_final(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_quote(root, "2026-11-06", {"px": 3600}, today_has_open=True)
            write_news(root, "2026-11-08", {"fact": "周六稿"})
            closed = finish_final(root, "2026-11-08", trading_day=False)
            self.assertEqual(closed["status"], "非交易日")
            self.assertTrue((root / "hot" / "news" / "2026-11-08.jsonl").exists())
            blocked = finish_final(root, "2026-11-09", trading_day=True)
            self.assertEqual(blocked["status"], "未写终分")
            self.assertTrue((root / "hot" / "quotes" / "2026-11-06.json").exists())
            write_result(root, "2026-11-09", "终分", {"path": "窄区间"})
            frozen = write_result(root, "2026-11-09", "终分", {"path": "被盖掉"})
            self.assertEqual(frozen["status"], "已冻住")
            moved = finish_final(root, "2026-11-09", trading_day=True)
            self.assertEqual(moved["status"], "已归档")
            self.assertFalse((root / "hot" / "quotes" / "2026-11-06.json").exists())
            self.assertTrue((root / "archive" / "quotes" / "2026-11-06.json").exists())
            self.assertTrue((root / "archive" / "news" / "2026-11-08.jsonl").exists())
            archived = (root / "archive" / "news" / "2026-11-08.jsonl").read_text(encoding="utf-8")
            self.assertIn("周六稿", archived)

    def test_bars_keep_ten_sessions(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"date": f"2026-10-{day:02d}", "close": day} for day in range(1, 13)]
            result = write_bars(Path(tmp), "000001", rows)
            self.assertEqual(result["kept"], 10)
            kept = json.loads((Path(tmp) / "bars" / "000001.json").read_text(encoding="utf-8"))
            self.assertEqual(kept[0]["date"], "2026-10-03")
            self.assertEqual(kept[-1]["date"], "2026-10-12")

    def test_empty_quote_does_not_cover_prices_and_news_replaces_the_same_url(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_quote(root, "2026-11-09", {"px": 3600}, today_has_open=True)
            kept = write_quote(root, "2026-11-09", {}, today_has_open=True)
            self.assertEqual(kept["status"], "已有")
            stored = json.loads((root / "hot" / "quotes" / "2026-11-09.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["px"], 3600)
            closed = write_quote(root, "2026-11-08", {"状态": "休市"}, today_has_open=False)
            again = write_quote(root, "2026-11-08", {"状态": "休市"}, today_has_open=False)
            self.assertEqual(closed["status"], "已写")
            self.assertEqual(again["status"], "已有")
            gap = write_quote(root, "2026-11-07", {}, today_has_open=False)
            self.assertEqual(gap["status"], "未挂")
            first = write_news(root, "2026-11-09", {"url": "https://example.test/a", "fact": "旧"})
            second = write_news(root, "2026-11-09", {"url": "https://example.test/a", "fact": "新"})
            self.assertEqual(first["status"], "已写")
            self.assertEqual(second["status"], "已替换")
            lines = (root / "hot" / "news" / "2026-11-09.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("新", lines[0])

    def test_bars_keep_high_when_a_later_row_only_has_close(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_bars(root, "002081", [{"date": "2026-11-09", "open": 4.0, "high": 4.2, "low": 3.9, "close": 4.1}])
            write_bars(root, "002081", [{"date": "2026-11-09", "close": 4.05}])
            kept = json.loads((root / "bars" / "002081.json").read_text(encoding="utf-8"))
            self.assertEqual(kept[0]["high"], 4.2)
            self.assertEqual(kept[0]["low"], 3.9)
            self.assertEqual(kept[0]["close"], 4.05)

    def test_hot_list_keeps_the_days_before_archive(self) -> None:
        hot = hot_quote_dates(
            ["2026-11-06", "2026-11-07", "2026-11-08"],
            today="2026-11-09",
            today_has_open=True,
            final_dates=["2026-11-06"],
        )
        self.assertEqual(hot, ["2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09"])


if __name__ == "__main__":
    unittest.main()
