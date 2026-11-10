#!/usr/bin/env python3
"""Hot layer and archive. No network."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from astock.lake import finish_final, hot_quote_dates, write_bars, write_news, write_quote


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
    def test_weekend_quote_is_not_written(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = write_quote(root, "2026-11-08", {"px": 1}, today_has_open=False)
            self.assertEqual(result["status"], "非交易日")
            self.assertFalse((root / "hot" / "quotes").exists())

    def test_news_survives_the_weekend_until_the_next_final(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_quote(root, "2026-11-06", {"px": 3600}, today_has_open=True)
            write_news(root, "2026-11-08", {"fact": "周六稿"})
            closed = finish_final(root, "2026-11-08", trading_day=False)
            self.assertEqual(closed["status"], "非交易日")
            self.assertTrue((root / "hot" / "news" / "2026-11-08.jsonl").exists())
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


if __name__ == "__main__":
    unittest.main()
