#!/usr/bin/env python3
"""Check one fact sentence against the page snippet. No network, no score.

Composer 2.5 Fast may propose the sentence. This module accepts it only when
every number in the sentence already appears in the snippet. The data window
calls it. The analysis window does not.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

TAIL = "不改行为分、不改主路径、不改 9:15。不进四档、不改 14:55。"
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def numbers(text: str) -> list[str]:
    """Decimal numbers as written. Percent signs and units stay outside the match."""
    cleaned = text.translate(str.maketrans("０１２３４５６７８９．", "0123456789."))
    return _NUMBER.findall(cleaned)


def _gap(kind: str) -> str:
    if kind == "业绩":
        head = "页面未给业绩数字"
    else:
        head = "页面未给价格"
    return f"{head}。{TAIL}"


def already_clear(snippet: str) -> bool:
    """A single finished sentence that already contains a number."""
    text = snippet.strip()
    return bool(numbers(text)) and text.count("。") == 1 and len(text) <= 160


def _with_tail(sentence: str) -> str:
    body = sentence.strip().rstrip("。")
    return f"{body}。{TAIL}"


def seal(snippet: str, model_sentence: str | None = None, kind: str = "价格") -> dict:
    """Return the ledger sentence and whether the model text was kept.

    `kind` is `业绩` or `价格`. It only chooses the gap phrase.
    """
    if kind not in {"业绩", "价格"}:
        raise ValueError("kind 只能是业绩或价格")
    if not numbers(snippet or ""):
        return {"accepted": False, "called_model": False, "text": _gap(kind)}
    if model_sentence is None or not model_sentence.strip():
        if already_clear(snippet):
            return {"accepted": True, "called_model": False, "text": _with_tail(snippet.strip())}
        return {"accepted": False, "called_model": False, "need_model": True, "text": _gap(kind)}
    source = set(numbers(snippet))
    extra = [item for item in numbers(model_sentence) if item not in source]
    if extra or not numbers(model_sentence):
        return {"accepted": False, "called_model": True, "text": _gap(kind)}
    return {"accepted": True, "called_model": True, "text": _with_tail(model_sentence)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验事实一句。不改权重，不下单。")
    parser.add_argument("--snippet", required=True, help="页面截出的原文片段")
    parser.add_argument("--model", default="", help="模型给出的一句。空则只在片段已清楚时采用片段")
    parser.add_argument("--kind", default="价格", choices=("价格", "业绩"))
    args = parser.parse_args(argv)
    try:
        result = seal(args.snippet, args.model or None, args.kind)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
