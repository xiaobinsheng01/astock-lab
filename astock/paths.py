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
