#!/usr/bin/env python3
"""The fetch chain stores printouts. It does not score and does not run 初分."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from astock.chain import EXCLUDED, STEPS, default_runners, run_chain


class ChainTest(unittest.TestCase):
    def test_steps_stay_on_the_fetch_list(self) -> None:
        self.assertEqual(
            STEPS,
            (
                "news",
                "close",
                "drive",
                "brief",
                "screen",
                "a50",
                "cctv",
                "cfbond",
                "cninfo",
                "cash",
            ),
        )
        self.assertNotIn("初分", STEPS)
        self.assertEqual(EXCLUDED, ("初分",))

    def test_default_runners_leave_brief_until_both_edges_exist(self) -> None:
        bare = default_runners()
        self.assertNotIn("brief", bare)
        self.assertNotIn("初分", bare)
        edged = default_runners(low=3580.0, high=3624.0)
        self.assertIn("brief", edged)

    def test_chain_writes_snapshots_and_skips_prelim(self) -> None:
        called: list[str] = []

        def fake(name: str):
            def run() -> tuple[int, str]:
                called.append(name)
                return 0, json.dumps({"step": name}, ensure_ascii=False) + "\n"

            return run

        runners = {name: fake(name) for name in STEPS}
        runners["初分"] = fake("初分")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = run_chain(root, runners, low=1.0, high=2.0)
            self.assertEqual([row["name"] for row in payload["steps"]], list(STEPS))
            self.assertNotIn("初分", called)
            self.assertEqual(payload["excluded"], ["初分"])
            for row in payload["steps"]:
                self.assertEqual(row["status"], "已写")
                self.assertTrue(Path(row["path"]).is_file())
            saved = json.loads((root / "hot" / "chain.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["chain"], list(STEPS))

    def test_brief_without_edges_is_not_run(self) -> None:
        called: list[str] = []

        def run() -> tuple[int, str]:
            called.append("brief")
            return 0, "不应出现\n"

        with tempfile.TemporaryDirectory() as tmp:
            payload = run_chain(Path(tmp), {"brief": run})
            brief = next(row for row in payload["steps"] if row["name"] == "brief")
            self.assertEqual(brief["status"], "未跑")
            self.assertEqual(called, [])
            text = Path(brief["path"]).read_text(encoding="utf-8")
            self.assertIn("缺低点或高点", text)

    def test_empty_printout_is_unmounted(self) -> None:
        def run() -> tuple[int, str]:
            return 0, "  \n"

        with tempfile.TemporaryDirectory() as tmp:
            payload = run_chain(Path(tmp), {"news": run}, low=1.0, high=2.0)
            news = next(row for row in payload["steps"] if row["name"] == "news")
            self.assertEqual(news["status"], "未挂")


if __name__ == "__main__":
    unittest.main()
