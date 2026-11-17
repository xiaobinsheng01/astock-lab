#!/usr/bin/env python3
"""CSI 300 for the data layer. Prices and daily bars, or a gap. No score, no order.

The index is recorded on its own. It does not enter W1–W8 and does not become
a cushion. Tencent is the first source. Sina, then Eastmoney, are used only
when Tencent has no price or the daily bars are empty. A later source never
overwrites a Tencent number. Volume is never turned into turnover.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astock.lake import write_bars
from astock.net import context as net_context
from astock.paths import LAKE

CODE = "000300"
NAME = "沪深300"
KEEP = 10
PCT_TOLERANCE = 0.05
AMOUNT_TOLERANCE_YI = 0.05
BEIJING = timezone(timedelta(hours=8))


class Product:
    """One tape. `em_div` is the Eastmoney integer price scale. Percent stays /100."""

    def __init__(self, code: str, name: str, symbol: str, secid: str, em_div: int, digits: int):
        self.code = code
        self.name = name
        self.symbol = symbol
        self.secid = secid
        self.em_div = em_div
        self.digits = digits


CSI300 = Product("000300", "沪深300", "sh000300", "1.000300", 100, 2)
DUAL50 = Product("588330", "双创50ETF华宝", "sh588330", "1.588330", 1000, 3)

QUOTE_URL = "https://qt.gtimg.cn/q=sh000300"
IFZQ_URL = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000300,day,,,12,qfq"
)
NEWFQ_URL = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    "?param=sh000300,day,,,12,qfq"
)
SINA_QUOTE_URL = "https://hq.sinajs.cn/list=sh000300"
SINA_KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData?symbol=sh000300&scale=240&ma=no&datalen=12"
)
EM_QUOTE_URL = (
    "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000300"
    "&fields=f43,f44,f45,f46,f48,f57,f58,f60,f86,f169,f170"
)
EM_KLINE_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000300"
    "&klt=101&fqt=1&lmt=12&end=20500101"
    "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
)


def _num(value):
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_pct(value: float) -> float:
    return int(value * 100 + (0.5 if value >= 0 else -0.5)) / 100.0


def _unmounted(error: str) -> dict:
    return {"status": "未挂", "error": error}


def _looks_closed(raw: str) -> bool:
    text = raw.strip()
    if not text:
        return True
    lowered = text.lower()
    if "请登录" in text or "访问校验" in text:
        return True
    if text.startswith("<") and "~" not in text and "{" not in text:
        return True
    if "login" in lowered and "~" not in text and "{" not in text:
        return True
    return False


def _loads(raw: str):
    text = raw.strip()
    if "=" in text[:20]:
        text = text.split("=", 1)[1]
    if text.endswith(";"):
        text = text[:-1]
    return json.loads(text)


def _clock_from_stamp(stamp: str) -> str:
    if len(stamp) >= 14 and stamp[:14].isdigit():
        return (
            f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} "
            f"{stamp[8:10]}:{stamp[10:12]}:{stamp[12:14]}"
        )
    return ""


def _clock_from_unix(value) -> str:
    number = _num(value)
    if number is None:
        return ""
    if number > 10**12:
        number = number / 1000
    moment = datetime.fromtimestamp(number, tz=BEIJING)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def session_word(clock: str) -> str:
    """Name the session from the quote clock. A weekend stamp is 休市."""
    if not clock or " " not in clock:
        return ""
    day, time_text = clock.split(" ", 1)
    try:
        moment = datetime.strptime(day, "%Y-%m-%d")
        hour, minute, *_rest = (int(part) for part in time_text.split(":"))
    except ValueError:
        return ""
    if moment.weekday() >= 5:
        return "休市"
    minutes = hour * 60 + minute
    if minutes >= 15 * 60:
        return "收盘"
    if minutes < 9 * 60 + 30:
        return "未开盘"
    return "盘中"


def parse_tencent_quote(raw: str, product: Product = CSI300) -> dict:
    if _looks_closed(raw) or "~" not in raw:
        return _unmounted("空")
    parts = raw.split('"', 1)[-1].split("~")
    if len(parts) < 35 or parts[2] != product.code:
        return _unmounted("空")
    amount_wan = _num(parts[37]) if len(parts) > 37 else None
    return {
        "name": parts[1].replace(" ", "") or product.name,
        "code": product.code,
        "px": _num(parts[3]),
        "prev": _num(parts[4]),
        "open": _num(parts[5]),
        "high": _num(parts[33]),
        "low": _num(parts[34]),
        "vendor_pct": _num(parts[32]),
        "amount_yi": None if amount_wan is None else round(amount_wan / 10000, 2),
        "clock": _clock_from_stamp(parts[30]),
        "source": "qt.gtimg.cn",
    }


def parse_sina_quote(raw: str, product: Product = CSI300) -> dict:
    marker = f"hq_str_{product.symbol}"
    if _looks_closed(raw) or marker not in raw or '"' not in raw:
        return _unmounted("空")
    fields = raw.split('"', 1)[1].split(",")
    if len(fields) < 32 or not fields[3]:
        return _unmounted("空")
    amount_yuan = _num(fields[9])
    clock = f"{fields[30]} {fields[31]}".strip()
    return {
        "name": fields[0] or product.name,
        "code": product.code,
        "open": _num(fields[1]),
        "prev": _num(fields[2]),
        "px": _num(fields[3]),
        "high": _num(fields[4]),
        "low": _num(fields[5]),
        "vendor_pct": None,
        "amount_yi": None if amount_yuan is None else round(amount_yuan / 100000000, 2),
        "clock": clock,
        "source": "hq.sinajs.cn",
    }


def _em_price(value, divisor: int = 100):
    number = _num(value)
    if number is None:
        return None
    whole = isinstance(value, int) or (isinstance(value, str) and value.lstrip("-").isdigit())
    if whole and divisor == 1000:
        return number / 1000
    if whole and abs(number) >= 10000:
        return number / 100
    return number


def _em_pct(value):
    number = _num(value)
    if number is None:
        return None
    if isinstance(value, int) or (isinstance(value, str) and value.lstrip("-").isdigit()):
        return number / 100
    return number


def parse_eastmoney_quote(raw: str, product: Product = CSI300) -> dict:
    if _looks_closed(raw):
        return _unmounted("登录")
    try:
        data = (_loads(raw).get("data") or {})
    except (json.JSONDecodeError, AttributeError):
        return _unmounted("空")
    if not data or data.get("f43") in (None, "", "-"):
        return _unmounted("空")
    amount_yuan = _num(data.get("f48"))
    return {
        "name": data.get("f58") or product.name,
        "code": str(data.get("f57") or product.code),
        "px": _em_price(data.get("f43"), product.em_div),
        "high": _em_price(data.get("f44"), product.em_div),
        "low": _em_price(data.get("f45"), product.em_div),
        "open": _em_price(data.get("f46"), product.em_div),
        "prev": _em_price(data.get("f60"), product.em_div),
        "vendor_pct": _em_pct(data.get("f170")),
        "amount_yi": None if amount_yuan is None else round(amount_yuan / 100000000, 2),
        "clock": _clock_from_unix(data.get("f86")),
        "source": "push2.eastmoney.com",
    }


def _bar(date, open_, close, high, low, amount_yi) -> dict | None:
    if not date or close is None or open_ is None or high is None or low is None:
        return None
    return {
        "date": str(date),
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "amount_yi": amount_yi,
    }


def _tencent_rows(raw: str, product: Product = CSI300) -> dict:
    if _looks_closed(raw):
        return _unmounted("登录")
    try:
        payload = _loads(raw)
        series = (payload.get("data") or {}).get(product.symbol) or {}
        rows = series.get("qfqday") or series.get("day") or []
    except (json.JSONDecodeError, AttributeError):
        return _unmounted("空")
    if not rows:
        return _unmounted("空列表")
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        amount = None
        if len(row) >= 9:
            wan = _num(row[8])
            if wan is not None:
                amount = round(wan / 10000, 2)
        built = _bar(row[0], _num(row[1]), _num(row[2]), _num(row[3]), _num(row[4]), amount)
        if built:
            out.append(built)
    if not out:
        return _unmounted("空列表")
    return {"rows": out}


def parse_ifzq(raw: str, product: Product = CSI300) -> dict:
    parsed = _tencent_rows(raw, product)
    if parsed.get("status") == "未挂":
        return parsed
    return {"rows": parsed["rows"], "source": "web.ifzq.gtimg.cn"}


def parse_newfq(raw: str, product: Product = CSI300) -> dict:
    parsed = _tencent_rows(raw, product)
    if parsed.get("status") == "未挂":
        return parsed
    return {"rows": parsed["rows"], "source": "proxy.finance.qq.com/newfqkline"}


def parse_sina_kline(raw: str) -> dict:
    if _looks_closed(raw):
        return _unmounted("登录")
    try:
        rows = _loads(raw)
    except json.JSONDecodeError:
        return _unmounted("空")
    if not isinstance(rows, list) or not rows:
        return _unmounted("空列表")
    out = []
    for row in rows:
        built = _bar(
            row.get("day"),
            _num(row.get("open")),
            _num(row.get("close")),
            _num(row.get("high")),
            _num(row.get("low")),
            None,
        )
        if built:
            out.append(built)
    if not out:
        return _unmounted("空列表")
    return {"rows": out, "source": "money.finance.sina.com.cn"}


def parse_eastmoney_kline(raw: str) -> dict:
    if _looks_closed(raw):
        return _unmounted("登录")
    try:
        rows = (_loads(raw).get("data") or {}).get("klines") or []
    except (json.JSONDecodeError, AttributeError):
        return _unmounted("空")
    if not rows:
        return _unmounted("空列表")
    out = []
    for line in rows:
        fields = str(line).split(",")
        if len(fields) < 6:
            continue
        amount_yuan = _num(fields[6]) if len(fields) > 6 else None
        built = _bar(
            fields[0],
            _num(fields[1]),
            _num(fields[2]),
            _num(fields[3]),
            _num(fields[4]),
            None if amount_yuan is None else round(amount_yuan / 100000000, 2),
        )
        if built:
            out.append(built)
    if not out:
        return _unmounted("空列表")
    return {"rows": out, "source": "push2his.eastmoney.com"}


def _with_pct(rows: list[dict]) -> list[dict]:
    ordered = sorted(rows, key=lambda item: item["date"])
    previous = None
    stamped = []
    for row in ordered:
        item = dict(row)
        if previous is not None and previous > 0:
            item["prev"] = previous
            item["pct"] = _round_pct((row["close"] - previous) / previous * 100)
        else:
            item["prev"] = None
            item["pct"] = None
        previous = row["close"]
        stamped.append(item)
    return stamped[-KEEP:]


def _fill_amount(ohlc: list[dict], amounts: list[dict]) -> list[dict]:
    by_date = {row["date"]: row.get("amount_yi") for row in amounts}
    filled = []
    for row in ohlc:
        item = dict(row)
        if item.get("amount_yi") is None and by_date.get(row["date"]) is not None:
            item["amount_yi"] = by_date[row["date"]]
        filled.append(item)
    return filled


def _read(get, url: str, parser, mounts: list[dict]) -> dict | None:
    try:
        raw = get(url)
    except Exception as exc:  # noqa: BLE001 — a dead host is 未挂, not a zero
        mounts.append({"source": url, "status": "未挂", "error": type(exc).__name__})
        return None
    parsed = parser(raw)
    if parsed.get("status") == "未挂":
        mounts.append({"source": url, "status": "未挂", "error": parsed.get("error") or "空"})
        return None
    return parsed


def _endpoints(product: Product) -> dict:
    """CSI 300 keeps the module constants so callers can match those URLs."""
    if product.code == CSI300.code and product.symbol == CSI300.symbol:
        return {
            "quote": ((QUOTE_URL, lambda raw: parse_tencent_quote(raw, product)),
                      (SINA_QUOTE_URL, lambda raw: parse_sina_quote(raw, product)),
                      (EM_QUOTE_URL, lambda raw: parse_eastmoney_quote(raw, product))),
            "ifzq": (IFZQ_URL, lambda raw: parse_ifzq(raw, product)),
            "newfq": (NEWFQ_URL, lambda raw: parse_newfq(raw, product)),
            "fallback": ((SINA_KLINE_URL, parse_sina_kline),
                         (EM_KLINE_URL, parse_eastmoney_kline)),
        }
    symbol = product.symbol
    return {
        "quote": (
            (f"https://qt.gtimg.cn/q={symbol}", lambda raw: parse_tencent_quote(raw, product)),
            (f"https://hq.sinajs.cn/list={symbol}", lambda raw: parse_sina_quote(raw, product)),
            (
                "https://push2.eastmoney.com/api/qt/stock/get?secid="
                f"{product.secid}&fields=f43,f44,f45,f46,f48,f57,f58,f60,f86,f169,f170",
                lambda raw: parse_eastmoney_quote(raw, product),
            ),
        ),
        "ifzq": (
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            f"?param={symbol},day,,,12,qfq",
            lambda raw: parse_ifzq(raw, product),
        ),
        "newfq": (
            "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
            f"?param={symbol},day,,,12,qfq",
            lambda raw: parse_newfq(raw, product),
        ),
        "fallback": (
            (
                "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=12",
                parse_sina_kline,
            ),
            (
                "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid="
                f"{product.secid}&klt=101&fqt=1&lmt=12&end=20500101"
                "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                parse_eastmoney_kline,
            ),
        ),
    }


def collect_for(get, product: Product = CSI300) -> dict:
    """Build one packet. `get(url)` returns the response body or raises."""
    ends = _endpoints(product)
    mounts: list[dict] = []
    quote = None
    for url, parser in ends["quote"]:
        parsed = _read(get, url, parser, mounts)
        if parsed:
            quote = parsed
            break

    ohlc = None
    bar_source = ""
    ifzq = _read(get, ends["ifzq"][0], ends["ifzq"][1], mounts)
    newfq = _read(get, ends["newfq"][0], ends["newfq"][1], mounts)
    if ifzq:
        rows = ifzq["rows"]
        bar_source = ifzq["source"]
        if newfq:
            rows = _fill_amount(rows, newfq["rows"])
            bar_source = f"{bar_source}+{newfq['source']}"
        ohlc = rows
    elif newfq:
        ohlc = newfq["rows"]
        bar_source = newfq["source"]
    else:
        for url, parser in ends["fallback"]:
            parsed = _read(get, url, parser, mounts)
            if parsed:
                ohlc = parsed["rows"]
                bar_source = parsed["source"]
                break

    return assemble(quote, _with_pct(ohlc or []), bar_source, mounts, product)


def collect(get) -> dict:
    """CSI 300 packet. `get(url)` returns the response body or raises."""
    return collect_for(get, CSI300)


def _px(value, digits: int) -> str:
    return f"{value:.{digits}f}"


def assemble(
    quote: dict | None,
    bars: list[dict],
    bar_source: str,
    mounts: list[dict],
    product: Product = CSI300,
) -> dict:
    label = product.name
    packet = {
        "code": product.code,
        "name": label,
        "status": "未挂",
        "session": "",
        "px": None,
        "prev": None,
        "open": None,
        "high": None,
        "low": None,
        "pct": None,
        "vendor_pct": None,
        "amount_yi": None,
        "bar_amount_yi": None,
        "amount_status": "未给",
        "clock": "",
        "source": "",
        "bar_source": bar_source,
        "bars": bars,
        "mounts": mounts,
        "weights": "不进W1–W8",
        "cushion": "不进托住",
        "text": f"{label} 报价未挂",
    }
    if not quote:
        if bars:
            packet["status"] = "缺口"
            packet["text"] = f"{label} 缺现价或前收"
        return packet
    packet.update(
        {
            "name": quote.get("name") or label,
            "code": quote.get("code") or product.code,
            "px": quote.get("px"),
            "prev": quote.get("prev"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "vendor_pct": quote.get("vendor_pct"),
            "amount_yi": quote.get("amount_yi"),
            "clock": quote.get("clock") or "",
            "source": quote.get("source") or "",
        }
    )
    label = packet["name"]
    missing = [
        name
        for name in ("px", "prev", "open", "high", "low", "clock")
        if packet[name] in (None, "")
    ]
    if missing or not packet["prev"]:
        packet["status"] = "缺口"
        packet["text"] = f"{label} 缺现价、前收或行情时间"
        return packet
    computed = _round_pct((packet["px"] - packet["prev"]) / packet["prev"] * 100)
    vendor = packet["vendor_pct"]
    packet["pct"] = computed
    packet["session"] = session_word(packet["clock"])
    if vendor is not None and abs(vendor - computed) > PCT_TOLERANCE:
        packet["status"] = "未核"
        packet["text"] = (
            f"{label} 来源涨跌幅 {vendor:.2f} 与现价前收算出的 {computed:.2f} 对不上，两个都留。"
            "不进权重，不进托住。"
        )
        return packet
    last = bars[-1] if bars else None
    quote_day = packet["clock"][:10]
    if last and last["date"] == quote_day and last.get("amount_yi") is not None and packet["amount_yi"] is not None:
        packet["bar_amount_yi"] = last["amount_yi"]
        if abs(last["amount_yi"] - packet["amount_yi"]) > AMOUNT_TOLERANCE_YI:
            packet["amount_status"] = "未核"
            packet["status"] = "未核"
            packet["text"] = (
                f"{label} 现价成交额 {packet['amount_yi']:.2f} 与日K成交额 {last['amount_yi']:.2f} 对不上，两个都留。"
                "不进权重，不进托住。"
            )
            return packet
    if packet["amount_yi"] is None:
        packet["amount_status"] = "未给"
        amount_bit = "，成交额未给"
    else:
        packet["amount_status"] = "已核"
        amount_bit = f"，成交额 {packet['amount_yi']:.2f} 亿元"
    bar_bit = "" if bars else "，日K未挂"
    packet["status"] = "已核"
    digits = product.digits
    packet["text"] = (
        f"{label} {packet['session']} {_px(packet['px'], digits)}，涨跌幅 {packet['pct']:.2f}%，"
        f"高 {_px(packet['high'], digits)}，低 {_px(packet['low'], digits)}{amount_bit}，"
        f"报价 {packet['clock']}{bar_bit}。不进权重，不进托住。"
    )
    return packet


def snapshot(result: dict) -> dict:
    return {
        "代码": result.get("code") or CODE,
        "名称": result.get("name") or NAME,
        "状态": result.get("status"),
        "时段": result.get("session") or "",
        "开": result.get("open"),
        "高": result.get("high"),
        "低": result.get("low"),
        "收": result.get("px"),
        "前收": result.get("prev"),
        "涨跌幅": result.get("pct"),
        "来源涨跌幅": result.get("vendor_pct"),
        "成交额": result.get("amount_yi"),
        "成交额状态": result.get("amount_status"),
        "日K成交额": result.get("bar_amount_yi"),
        "成交额单位": "亿元",
        "行情时间": result.get("clock") or "",
        "来源": result.get("source") or "",
        "日K来源": result.get("bar_source") or "",
        "日K": result.get("bars") or [],
        "未挂": result.get("mounts") or [],
        "权重": "不进W1–W8",
        "托住": "不进托住",
        "事实": result.get("text") or "",
    }


def store(result: dict, root: Path | None = None) -> dict:
    """Write the snapshot. A dead fetch does not replace the last good file.

    Daily bars are replaced only when this packet has some.
    """
    lake = root or LAKE
    name = result.get("name") or NAME
    code = str(result.get("code") or CODE)
    path = lake / "hot" / "snapshots" / f"{name}.json"
    written: dict = {}
    if result.get("status") == "未挂" and path.exists():
        written["snapshot"] = "保留上一份"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(snapshot(result), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written["snapshot"] = str(path)
    bars = result.get("bars") or []
    if bars:
        written["bars"] = write_bars(lake, code, bars)
    return written


def _live_get(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    if "sina" in url:
        headers["Referer"] = "https://finance.sina.com.cn"
    if "sinajs.cn" in url or url.startswith("https://qt.gtimg.cn/"):
        encoding = "gbk"
    else:
        encoding = "utf-8"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15, context=net_context()) as resp:
        return resp.read().decode(encoding, "replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="沪深300现价和日K。缺价写缺口。不下单。")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写资料湖")
    args = parser.parse_args(argv)
    result = collect(_live_get)
    if not args.dry_run:
        result["written"] = store(result)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
