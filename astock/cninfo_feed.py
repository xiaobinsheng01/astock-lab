#!/usr/bin/env python3
"""Cninfo announcement check. A code-only empty result is not 'no announcement'."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"


def read_announcements(rows: list[dict], *, with_org: bool, code: str = "") -> dict:
    if not rows and not with_org:
        return {"status": "按代码返回0条，不写成没发公告", "items": []}
    if not rows:
        return {"status": "列表无这条", "items": []}
    code_digits = "".join(ch for ch in str(code) if ch.isdigit())
    items = []
    other = []
    for row in rows:
        row_code = "".join(ch for ch in str(row.get("secCode") or row.get("code") or "") if ch.isdigit())
        entry = {
            "title": row.get("announcementTitle") or row.get("title") or "",
            "date": row.get("announcementTime") or row.get("date") or "",
            "adjunct": row.get("adjunctUrl") or "",
            "secCode": row_code,
            "secName": row.get("secName") or "",
        }
        # A query may answer with a different company's paper. It is not this stock.
        if code_digits and row_code and row_code != code_digits:
            other.append(entry)
            continue
        items.append(entry)
    if not items and other:
        return {
            "status": "返回行不是这只股票，不写成有公告",
            "items": [],
            "other_company": other,
        }
    if not items:
        return {"status": "列表无这条", "items": []}
    return {"status": "有公告", "items": items}


def pdf_status(blob: bytes) -> str:
    if blob.startswith(b"%PDF"):
        return "数字来自巨潮 PDF"
    return "交易所 PDF 未挂"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="巨潮公告。打不开写未挂。不下单。")
    parser.add_argument("--code", default="")
    parser.add_argument("--org", default="")
    parser.add_argument("--json", default="", help="解析这个查询结果文件，不访问网络")
    parser.add_argument("--pdf", default="", help="只看这个文件的文件头是不是 PDF")
    args = parser.parse_args(argv)
    if args.pdf:
        blob = open(args.pdf, "rb").read(8)
        json.dump({"status": pdf_status(blob)}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    if args.json:
        payload = json.loads(open(args.json, encoding="utf-8").read())
        rows = payload.get("announcements") or []
        result = read_announcements(rows, with_org=bool(args.org), code=args.code)
    elif not args.code:
        result = {"status": "未挂", "items": [], "text": "未提供代码"}
    else:
        try:
            body = json.dumps(
                {"pageNum": 1, "pageSize": 30, "stock": f"{args.code},{args.org}" if args.org else args.code}
            ).encode()
            req = urllib.request.Request(
                QUERY_URL,
                data=body,
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
            rows = payload.get("announcements") or []
            result = read_announcements(rows, with_org=bool(args.org), code=args.code)
        except Exception as exc:  # noqa: BLE001 — a dead query is 未挂
            result = {"status": "未挂", "items": [], "error": type(exc).__name__}
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
