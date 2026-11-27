#!/usr/bin/env python3
"""全部行业与概念的板块表，按上证涨跌日分两栏算历史。不打分，不下单。

原来的板块表只跟四个科技行业，"板块的历史选择"要的是全部行业。这里按两套
口径各算一张表：

  行业：申万 31 个一级行业全覆盖。
  概念：题材板块，看轮动。

行业这一层不用代理指数。腾讯 `pt0180xxxx` 就是申万一级行业的成员表，代码与
申万编码一一对应，成员股一次能取全。把成员股按等权拼成行业日收益：

  行业日收益 = 成员股当日涨跌幅的等权平均

这比拿一个近似的指数顶替准确，也不会出现两个行业共用一个指数、两行数据一模
一样的情况。成分股用新浪日线，历史深度可指定。

每个板块按上证涨跌日分两栏，只用两边都有数的交易日：

  进攻：上证上涨的那些日子，这个板块的中位涨幅和上涨胜率。
  防御：上证下跌的那些日子，这个板块的中位涨幅和上涨胜率。

两栏合一句分类。分类只描述历史，不预测明天。今天谁涨得多不改分类，分类也
不改板块四态。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

from astock.lake import read_bars, write_bars
from astock.paths import LAKE
from astock.sector_drive import _fetch, _num

BENCHMARK = "000001"

# 中证官网行情，做基准和个别指数的第二源。
CSINDEX = (
    "https://www.csindex.com.cn/csindex-home/perf/index-perf"
    "?indexCode={code}&startDate={beg}&endDate={end}"
)

# 新浪日线，深度可指定。成分股和指数都走它。
SINA = (
    "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20x=/CN_MarketDataService.getKLineData"
    "?symbol={symbol}&scale=240&ma=no&datalen={count}"
)

# 腾讯前复权日线，单只票一次能取 250 根以上，含成交量。
QQ_KLINE = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    "?param={symbol},day,,,{count},qfq"
)
QQ_KLINE_BACKUP = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    "?param={symbol},day,,,{count},qfq"
)

# 腾讯板块成员表。一个请求能拿全一个板块的成员。
#
# 排序必须用 turnover（成交额），不能用 price：price 是按股价从高到低排的，
# 取前 60 只等于把 128 元的小票和 300 元的次新拼成一个「高价股指数」，
# 跟行业涨跌没关系。turnover 排序能覆盖全量成员，再按流通市值挑头部。
QQ_MEMBERS = (
    "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
    "?board_code={board}&sort_type=turnover&direct=down&offset=0&count=200"
)

# 腾讯板块报价，用来一次校验全部板块代码和名称。
QQ_QUOTE = "https://qt.gtimg.cn/q="

DAYS = 250

# 两栏各少于此数就不点名。样本不足记「样本不足」，不记 0。
MIN_DAYS = 20

# 成员少于这个数的板块不拼等权指数：三只股票的平均不是行业。
MIN_MEMBERS = 5

# 一次最多取多少只成分股。取流通市值靠前的一批，足够代表行业，也不必为长尾
# 小票多打几十个请求。
MAX_MEMBERS = 60

# 并发取数。只并行网络等待，不并行计算，结果与串行一致。
FETCH_WORKERS = 8

REGISTRY = Path(__file__).resolve().parent / "data" / "boards.json"

# 申万一级行业：名称 → 腾讯板块代码。代码与申万编码一致，`pt01` + 6 位。
SW_LEVEL1 = {
    "农林牧渔": "pt01801010",
    "基础化工": "pt01801030",
    "钢铁": "pt01801040",
    "有色金属": "pt01801050",
    "电子": "pt01801080",
    "家用电器": "pt01801110",
    "食品饮料": "pt01801120",
    "纺织服饰": "pt01801130",
    "轻工制造": "pt01801140",
    "医药生物": "pt01801150",
    "公用事业": "pt01801160",
    "交通运输": "pt01801170",
    "房地产": "pt01801180",
    "商贸零售": "pt01801200",
    "社会服务": "pt01801210",
    "综合": "pt01801230",
    "建筑材料": "pt01801710",
    "建筑装饰": "pt01801720",
    "电力设备": "pt01801730",
    "国防军工": "pt01801740",
    "计算机": "pt01801750",
    "传媒": "pt01801760",
    "通信": "pt01801770",
    "银行": "pt01801780",
    "非银金融": "pt01801790",
    "汽车": "pt01801880",
    "机械设备": "pt01801890",
    "煤炭": "pt01801950",
    "石油石化": "pt01801960",
    "环保": "pt01801970",
    "美容护理": "pt01801980",
}


def today() -> str:
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def _get(url: str, *, tries: int = 3, pause: float = 1.2) -> bytes:
    """上游会在连续请求下断连。断连和 5xx 重试，4xx 直接放过。

    4xx 是代码或参数不对，重试没有意义，直接交给调用方写「未核」。
    """
    import urllib.error

    last: Exception | None = None
    for attempt in range(tries):
        try:
            return _fetch(url)
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise
            last = exc
        except Exception as exc:  # noqa: BLE001 — 断连值得再问一次
            last = exc
        if attempt + 1 < tries:
            time.sleep(pause * (attempt + 1))
    raise last if last else RuntimeError("fetch failed")


def stock_bars(code: str, *, count: int = DAYS) -> list[dict]:
    """单只股票的前复权日线，`{date, close, volume}`，按日期升序。

    必须用前复权。新浪给的是不复权价，除权那天价格会跳空，等权平均会把那个
    缺口当成真实下跌，一只票的一次分红就能把整年的行业收益拉歪。
    """
    symbol = code if code[:2].isalpha() else ("sh" if code[0] == "6" else "sz") + code
    for template in (QQ_KLINE, QQ_KLINE_BACKUP):
        try:
            raw = _get(template.format(symbol=symbol, count=int(count))).decode("utf-8", "replace")
            if "=" in raw[:40]:
                raw = raw.split("=", 1)[1]
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001 — 换下一个主机
            continue
        series = (payload.get("data") or {}).get(symbol) or {}
        rows = series.get("qfqday") or series.get("day") or []
        out = []
        for bar in rows:
            if len(bar) < 3:
                continue
            day = str(bar[0])
            close = _num(bar[2])
            volume = bar[5] if len(bar) > 5 else None
            if day and close is not None and close > 0:
                out.append({"date": day, "close": close, "volume": _num(volume)})
        if out:
            return sorted(out, key=lambda item: item["date"])
    return []


def sina_bars(code: str, *, count: int = DAYS) -> list[dict]:
    """新浪日线全字段，`{date, open, high, low, close, volume}`，按日期升序。

    不复权，只用于没有前复权源时的兜底，以及需要原始成交量的场合。
    """
    symbol = code if code[:2].isalpha() else ("sh" if code[0] == "6" else "sz") + code
    try:
        raw = _get(SINA.format(symbol=symbol, count=int(count))).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — 取不到就是未挂
        return []
    body = raw.split("var x=", 1)[-1].strip().rstrip(";").strip()
    if body.startswith("("):
        body = body[1:-1]
    try:
        rows = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        day = str(row.get("day") or "")
        close = _num(row.get("close"))
        volume = _num(row.get("volume"))
        if not day or close is None or close <= 0:
            continue
        out.append({
            "date": day,
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "close": close,
            "volume": volume,
        })
    return sorted(out, key=lambda item: item["date"])


def sina_klines(code: str, *, count: int = DAYS) -> dict[str, float]:
    """新浪日线，日期 → 收盘。取不到返回空字典。"""
    return {bar["date"]: bar["close"] for bar in sina_bars(code, count=count)}


def _cap(row: dict) -> float:
    """流通市值，单位亿。取不到记 0，排到后面。"""
    try:
        return float(row.get("ltsz") or 0)
    except (TypeError, ValueError):
        return 0.0


def board_members(board: str, *, limit: int = MAX_MEMBERS) -> list[str]:
    """腾讯板块成员代码，按流通市值从大到小取前 `limit` 只。取不到返回空表。

    「行业涨跌」对头部权重更敏感，按市值挑出来的一篮子才跟指数走得动。按股价
    排会挑出一堆小盘高价票，等于换了个赛道。ST 不进池：涨跌停制度和退市风险
    都不是行业属性。
    """
    try:
        payload = json.loads(_get(QQ_MEMBERS.format(board=board)).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 — 板块成员取不到就让这张表写未核
        return []
    rows = (payload.get("data") or {}).get("rank_list") or []
    picked = [
        row for row in rows
        if "ST" not in str(row.get("name") or "").upper()
        and len("".join(ch for ch in str(row.get("code") or "") if ch.isdigit())) == 6
    ]
    picked.sort(key=_cap, reverse=True)
    out = []
    for row in picked[:limit]:
        code = "".join(ch for ch in str(row.get("code") or "") if ch.isdigit())
        if len(code) == 6:
            out.append(code)
    return out


def _member_cache_path(code: str):
    day = today()
    return LAKE / "members" / day[:7] / f"{code}.json"


def member_series(code: str, *, count: int = DAYS) -> dict[str, dict]:
    """单只成分股的前复权日线（含成交量），按当月缓存。

    缓存只对当月有效：跨月后旧文件不再读，避免把上个月的数据当成今天的数据。
    缓存键带 `qfq` 前缀，旧的未复权缓存不会被误读。
    """
    path = _member_cache_path(code)
    if path.exists():
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 坏缓存当作没有
            rows = {}
        if isinstance(rows, list) and rows and rows[0].get("qfq"):
            return {str(bar["date"]): bar for bar in rows if bar.get("date")}
    bars = stock_bars(code, count=count)
    if bars:
        path.parent.mkdir(parents=True, exist_ok=True)
        marked = [{**bar, "qfq": True} for bar in bars]
        path.write_text(json.dumps(marked, ensure_ascii=False) + "\n", encoding="utf-8")
    return {bar["date"]: bar for bar in bars}


def member_series_many(codes: list[str], *, count: int = DAYS, workers: int = FETCH_WORKERS) -> dict[str, dict[str, dict]]:
    """一次取多只成分股，只把网络等待并行掉，算出来的东西和串行完全相同。

    一只票一个请求，串行跑 31 个行业要半小时。并发只影响什么时候拿到数据，
    不影响拿到之后怎么算；取不到的票照旧返回空表，由调用方按缺数据处理。
    """
    if not codes:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(codes)))) as pool:
        results = list(pool.map(lambda code: _safe_series(code, count), codes))
    return dict(zip(codes, results))


def _safe_series(code: str, count: int) -> dict[str, dict]:
    try:
        return member_series(code, count=count)
    except Exception:  # noqa: BLE001 — 一只票取不到不该拖垮整个行业
        return {}


# 一只票少于这个根数就当它没有可用的历史，不计入行业均值。
MIN_SERIES = 30

# 当天有数的成员少于此数，这一天不算行业均值：一只票的涨跌不是行业的涨跌。
MIN_DAY_MEMBERS = 3


def need_series(members: list[str], min_series: int = MIN_SERIES) -> int:
    """一个行业至少要有几只成员的历史，才算得出这张表。

    申万的行业大小差得远：综合只有 19 只，有色 133 只。一律要求 30 只会让小
    行业永远算不出来，所以取「过半成员」和 `min_series` 里更小的那个，再兜底
    `MIN_MEMBERS`。大行业要一半以上成员有历史，小行业只要过半、且不少于 5 只。
    """
    return max(MIN_MEMBERS, min(min_series, (len(members) + 1) // 2))


def equal_weight_returns(members: list[str], *, count: int = DAYS, min_series: int = MIN_SERIES) -> dict[str, float]:
    """成员股等权日收益，日期 → 百分比。

    每天只把当天有数的成员平均进去：某只停牌或数据短，不会把整天的均值拉偏，
    也不会因为一只票缺数据就把这一天丢掉。成员不足 `MIN_MEMBERS` 返回空表，
    可用历史不够 `need_series` 的票数时返回空表。
    """
    if len(members) < MIN_MEMBERS:
        return {}
    per_day: dict[str, list[float]] = {}
    usable = 0
    fetched = member_series_many(list(members), count=count + 5)
    for code in members:
        series = fetched.get(code) or {}
        if len(series) < 2:
            continue
        usable += 1
        days = sorted(series)
        for index in range(1, len(days)):
            day = days[index]
            px = series[day].get("close")
            prev = series[days[index - 1]].get("close")
            if px and prev and prev > 0:
                per_day.setdefault(day, []).append((px / prev - 1.0) * 100.0)
    if usable < need_series(members, min_series):
        return {}
    # 当天只有一两只票有数时，那不是行业，是个股，丢掉这一天。
    return {
        day: sum(values) / len(values)
        for day, values in per_day.items()
        if len(values) >= MIN_DAY_MEMBERS
    }


def index_returns(code: str, *, count: int = DAYS) -> dict[str, float]:
    """指数日收益，先用本地日线，再问中证。"""
    stored = read_bars(LAKE, code)
    series = {str(row.get("date")): _num(row.get("close")) for row in stored}
    series = {day: px for day, px in series.items() if day and px is not None}
    if len(series) < count:
        from datetime import date, timedelta

        end = date.fromisoformat(today())
        beg = end - timedelta(days=int(count * 1.5))
        url = CSINDEX.format(code=code, beg=beg.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
        try:
            payload = json.loads(_get(url).decode("utf-8", "replace"))
            for row in payload.get("data") or []:
                day = str(row.get("tradeDate") or "")
                px = _num(row.get("close"))
                if len(day) == 8 and day.isdigit():
                    day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
                if day and px is not None and px > 0:
                    series[day] = px
        except Exception:  # noqa: BLE001 — 用本地已有的
            pass
    days = sorted(series)
    out: dict[str, float] = {}
    for index in range(1, len(days)):
        prev = series[days[index - 1]]
        if prev and prev > 0:
            out[days[index]] = (series[days[index]] / prev - 1.0) * 100.0
    return out


def returns(series: list[tuple[str, float]]) -> dict[str, float]:
    """日期 → 相对前一根收盘的百分比。"""
    out: dict[str, float] = {}
    for index in range(1, len(series)):
        day, px = series[index]
        prev = series[index - 1][1]
        if prev and prev > 0:
            out[day] = (px / prev - 1.0) * 100.0
    return out


def _half(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "median": None, "win": None, "state": "未核"}
    return {
        "n": len(values),
        "median": median(values),
        "win": sum(1 for value in values if value > 0) / len(values),
        "state": "已核",
    }


def state_table(board_returns: dict[str, float], index_returns: dict[str, float]) -> dict:
    """按上证方向切样本，两栏分别描述。只在两边都有数的日子上算。"""
    days = sorted(set(board_returns) & set(index_returns))
    up = [board_returns[day] for day in days if index_returns[day] > 0]
    down = [board_returns[day] for day in days if index_returns[day] < 0]
    return {
        "days": len(days),
        "up": _half(up),
        "down": _half(down),
        "flat": len([day for day in days if index_returns[day] == 0]),
    }


def classify(board: dict) -> str:
    """两栏合一句。样本不足时不点名。"""
    up, down = board["up"], board["down"]
    if up["n"] < MIN_DAYS or down["n"] < MIN_DAYS:
        return "样本不足"
    if up["median"] > 0 and down["median"] >= 0:
        return "主线"
    if up["median"] > 0:
        return "仅进攻"
    if down["median"] >= 0:
        return "仅防御"
    return "无"


def rank(rows: list[dict]) -> list[dict]:
    """主线在前，同档按下跌日中位排，「跌的时候不亏」才是能过坏周的那一条。

    「样本不足」排在「无」前面：没算过不等于算过且不行。
    """
    order = {"主线": 0, "仅进攻": 1, "仅防御": 2, "样本不足": 3, "无": 4, "未核": 5}

    def key(row: dict):
        down = row["down"]["median"]
        up = row["up"]["median"]
        return (
            order.get(row["pick"], 9),
            -(down if down is not None else -999),
            -(up if up is not None else -999),
        )

    return sorted(rows, key=key)


def load_registry(path: Path = REGISTRY) -> list[dict]:
    """东财板块登记表，只用于概念表。"""
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 缺文件就当没名单
        return []
    return [row for row in rows if str(row.get("code") or "").startswith("BK")]


def concept_pool() -> list[dict]:
    """概念板块名单。`f111=0` 里名字带题材味的，剔除行业味和策略味。"""
    skip = ("重仓", "新进", "减仓", "增仓", "持股", "解禁", "破净", "破发", "超跌",
            "新高", "预增", "预减", "扭亏", "摘帽", "回购", "股", "综指", "成份")
    pool = []
    for row in load_registry():
        if row.get("level") != 0:
            continue
        name = str(row.get("name") or "")
        if not name or any(word in name for word in skip):
            continue
        if name.endswith(("概念", "产业", "技术", "经济")):
            pool.append(row)
    return pool


def analyse_industry(*, count: int = DAYS, limit: int = MAX_MEMBERS) -> dict:
    """行业这一层：申万 31 个一级行业，成员股等权。"""
    bench = index_returns(BENCHMARK, count=count)
    if not bench:
        return {"status": "未挂", "reason": "基准日线没有取到", "rows": [],
                "benchmark": {"code": BENCHMARK, "n": 0}}
    rows = []
    for name, board in SW_LEVEL1.items():
        members = board_members(board, limit=limit)
        daily = equal_weight_returns(members, count=count) if members else {}
        if not daily:
            rows.append({"name": name, "board": board, "members": len(members),
                         "pick": "未核", "days": 0, "up": _half([]), "down": _half([]),
                         "error": "成员日线没有取到" if members else "成员表没有取到"})
            continue
        table = state_table(daily, bench)
        pick = classify(table)
        rows.append({"name": name, "board": board, "members": len(members), **table, "pick": pick})
    return {
        "status": "已算",
        "method": "成员股等权",
        "benchmark": {"code": BENCHMARK, "n": len(bench)},
        "rows": rank(rows),
    }


def industry_frame(name: str, *, count: int = DAYS, limit: int = MAX_MEMBERS) -> list[dict]:
    """一个行业的等权日线，转成日线形状，供量价四态和均线使用。

    行业也有一根「日 K」：成员等权涨跌幅累乘出来的等权指数。量取成员成交量
    之和，价格取等权指数点位。没有成员就返回空表。
    """
    board = SW_LEVEL1.get(name)
    if not board:
        return []
    members = board_members(board, limit=limit)
    if not members:
        return []
    per_day: dict[str, list[float]] = {}
    volume: dict[str, float] = {}
    fetched = member_series_many(list(members), count=count + 5)
    for code in members:
        series = fetched.get(code) or {}
        if len(series) < 2:
            continue
        days = sorted(series)
        for index in range(1, len(days)):
            day = days[index]
            bar = series[day]
            prev = series[days[index - 1]].get("close")
            close = bar.get("close")
            if not (prev and close and prev > 0):
                continue
            per_day.setdefault(day, []).append((close / prev - 1.0) * 100.0)
            vol = bar.get("volume") or 0
            if vol > 0:
                volume[day] = volume.get(day, 0.0) + vol
    if not per_day:
        return []
    # 等权指数从 1000 起，逐日累乘平均涨幅。点位只是相对值，不对外当指数报价。
    #
    # 成交量取「当天有数的成员的平均量」，不取总和：某只成员停牌或少一天数据，
    # 总和会凭空掉一大截，被量价四态当成缩量，读出一根不存在的缩量阴线。
    # 而当天的成员不足 `need_members` 时整天不写：3 只票的平均涨跌不是行业。
    need_members = need_series(list(members))
    out = []
    level = 1000.0
    for day in sorted(per_day):
        values = per_day[day]
        if len(values) < MIN_DAY_MEMBERS or len(values) < need_members:
            continue
        pct = sum(values) / len(values)
        level *= 1.0 + pct / 100.0
        total = volume.get(day)
        out.append({
            "date": day,
            "close": level,
            "volume": (total / len(values)) if total else None,
            "members": len(values),
            "pct": pct,
        })
    return out


def analyse_concepts(*, count: int = DAYS, limit: int = MAX_MEMBERS) -> dict:
    """概念这一层：题材板块，成员股等权。

    概念板块在东财体系里。腾讯成员表只有申万口径的 `pt` 板块，对 `BK` 代码
    取不到成员，所以概念这一层要么由 `--concepts-from` 给一份名单到成员的映
    射，要么写「成员表没有取到」。不拿行业成员冒充概念成员。
    """
    bench = index_returns(BENCHMARK, count=count)
    pool = concept_pool()
    if not pool or not bench:
        return {"status": "未挂", "reason": "概念名单为空或基准没有取到", "rows": [],
                "benchmark": {"code": BENCHMARK, "n": len(bench)}}
    rows = []
    for item in pool:
        members = board_members(item["code"], limit=limit)
        daily = equal_weight_returns(members, count=count) if members else {}
        if not daily:
            rows.append({"name": item["name"], "code": item["code"], "members": len(members),
                         "pick": "未核", "days": 0, "up": _half([]), "down": _half([]),
                         "error": "成员表没有取到"})
            continue
        table = state_table(daily, bench)
        rows.append({"name": item["name"], "code": item["code"], "members": len(members),
                     **table, "pick": classify(table)})
    return {
        "status": "已算",
        "method": "成员股等权",
        "benchmark": {"code": BENCHMARK, "n": len(bench)},
        "rows": rank(rows),
    }


def _fmt(value, digits: int = 2) -> str:
    return "未核" if value is None else f"{value:+.{digits}f}"


def _pct(value) -> str:
    return "未核" if value is None else f"{value * 100:.0f}%"


def format_table(payload: dict, *, kind: str = "行业") -> str:
    if payload["status"] != "已算":
        return f"{kind}表：未挂。{payload.get('reason', '上游没有返回')}。"
    lines = [
        f"{kind} {len(payload['rows'])} 个，{payload.get('method', '')}，"
        f"基准上证 {payload['benchmark']['n']} 个交易日",
        f"{kind}\t分类\t上涨日中位\t上涨日胜率\t下跌日中位\t下跌日胜率\t样本\t成员",
    ]
    for row in payload["rows"]:
        up, down = row["up"], row["down"]
        lines.append(
            f"{row['name']}\t{row['pick']}\t"
            f"{_fmt(up['median'])}\t{_pct(up['win'])}\t"
            f"{_fmt(down['median'])}\t{_pct(down['win'])}\t{row['days']}\t{row.get('members', 0)}"
        )
    gaps = [f"{row['name']}（{row['error']}）" for row in payload["rows"] if row.get("error")]
    if gaps:
        lines.append("")
        lines.append("没算出来的，写明原因：" + "；".join(gaps))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="全部行业与概念的上下行统计。不打分，不下单。")
    parser.add_argument("--kind", default="行业", choices=["行业", "概念"], help="行业或概念")
    parser.add_argument("--days", type=int, default=DAYS, help="取多少根日线")
    parser.add_argument("--members", type=int, default=MAX_MEMBERS, help="每个板块取多少只成员")
    parser.add_argument("--json", action="store_true", help="印 JSON")
    args = parser.parse_args(argv)
    if args.kind == "概念":
        payload = analyse_concepts(count=args.days, limit=args.members)
    else:
        payload = analyse_industry(count=args.days, limit=args.members)
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(format_table(payload, kind=args.kind))
    return 0 if payload["status"] == "已算" else 1


if __name__ == "__main__":
    raise SystemExit(main())
