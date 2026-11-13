"""Locations that stay outside the rule text and the calculators."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules"
RUNTIME = ROOT / "runtime"
LEDGER = RUNTIME / "info-ledger.md"
HOLDERS_CACHE = RUNTIME / "cache" / "holders.json"
LAKE = RUNTIME / "lake"
LAKE_HOT = LAKE / "hot"
LAKE_ARCHIVE = LAKE / "archive"
# Portable desk state. These files are tracked by git so the cursor and the
# W1–W5 cells move with the repository, unlike the machine-local ledger.
STATE_DIR = LAKE / "state"
CURSOR_FILE = STATE_DIR / "cursor.json"
WEIGHTS_FILE = STATE_DIR / "weights.json"
SEEN_FILE = STATE_DIR / "seen-urls.txt"
