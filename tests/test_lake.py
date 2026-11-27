#!/usr/bin/env python3
"""Hot layer and archive. No network."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from astock.lake import finish_final, hot_quote_dates, read_bars, write_bars, write_news, write_quote


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
            moved = finish_final(root, "2026-11-09", trading_day=True)
            self.assertEqual(moved["status"], "已归档")
            self.assertFalse((root / "hot" / "quotes" / "2026-11-06.json").exists())
            self.assertTrue((root / "archive" / "quotes" / "2026-11-06.json").exists())
            self.assertTrue((root / "archive" / "news" / "2026-11-08.jsonl").exists())
            archived = (root / "archive" / "news" / "2026-11-08.jsonl").read_text(encoding="utf-8")
            self.assertIn("周六稿", archived)

    def test_bars_keep_full_history(self) -> None:
        """A ten-bar cap made every 20/60/250-day test impossible, so there is no cap."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"date": f"2026-{month:02d}-01", "close": month} for month in range(1, 13)]
            result = write_bars(Path(tmp), "000001", rows)
            self.assertEqual(result["kept"], 12)
            kept = json.loads((Path(tmp) / "bars" / "000001.json").read_text(encoding="utf-8"))
            self.assertEqual(kept[0]["date"], "2026-01-01")
            self.assertEqual(kept[-1]["date"], "2026-12-01")

    def test_bars_merge_by_date_and_keep_old_sessions(self) -> None:
        """A later write adds sessions; it does not replace the series with itself."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_bars(root, "000001", [{"date": "2026-11-03", "close": 1}, {"date": "2026-11-04", "close": 2}])
            write_bars(root, "000001", [{"date": "2026-11-04", "close": 20}, {"date": "2026-11-05", "close": 3}])
            kept = read_bars(root, "000001")
            self.assertEqual([row["date"] for row in kept], ["2026-11-03", "2026-11-04", "2026-11-05"])
            self.assertEqual(kept[1]["close"], 20)

    def test_read_bars_of_a_missing_code_is_empty(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_bars(Path(tmp), "999999"), [])

    def test_final_copies_snapshots_before_they_are_overwritten(self) -> None:
        """终分/初分 are single files; the archive must hold yesterday's judgment."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snap = root / "hot" / "snapshots"
            snap.mkdir(parents=True)
            (snap / "终分.json").write_text('{"判断": "涨"}', encoding="utf-8")
            (snap / "初分.json").write_text('{"判断": "平"}', encoding="utf-8")
            (snap / "手写持仓.json").write_text('{"持仓": []}', encoding="utf-8")
            finish_final(root, "2026-11-26", trading_day=True)
            archived = root / "archive" / "snapshots" / "2026-11-26"
            self.assertTrue((archived / "终分.json").exists())
            self.assertTrue((archived / "初分.json").exists())
            # The book is state, not a session judgment.
            self.assertFalse((archived / "手写持仓.json").exists())
            # The hot copy stays; the desk keeps reading it.
            self.assertTrue((snap / "终分.json").exists())


if __name__ == "__main__":
    unittest.main()
