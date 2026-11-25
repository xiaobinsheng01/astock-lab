#!/usr/bin/env python3
"""One record shape for every stock.

A new code gets the same keys as a holding. Empty public cells stay 未核 or
待收集. Sentences the pages cannot support stay 未填. The five human fields
stay 待填写 until the holding row supplies them. Research actions never
rewrite the hard gate.
"""

from __future__ import annotations

import json
from pathlib import Path

from astock.fundamental import (
    GAP,
    _day,
    _gap,
    _num,
    _text,
    _yi,
    board_limit,
    next_unlock,
    normalize_code,
)
from astock.paths import LAKE_HOT

HOLDINGS_PATH = LAKE_HOT / "snapshots" / "手写持仓.json"
BOOK_PATH = LAKE_HOT / "snapshots" / "持仓基本面.json"
SCHEMA_VERSION = 1

HUMAN_KEYS = ("持有理由", "关键假设", "验证指标", "破坏条件", "跟踪等级")
READY_KEYS = ("持有理由", "关键假设", "验证指标", "破坏条件")
LOGIC_WORDS = {"被验证", "被削弱", "被推翻"}
ACTION_WORDS = {"维持跟踪", "重点复核", "风险预警", "退出观察"}
OPEN = {"", "待填写", "待收集", "待提供", "未核", "未填", "未知"}

CALIBER = (
    "年报是全年。三季报是前三季度累计。单季等于同年三季报累计减中报累计。"
    "归母和扣非分开。经营现金流净额没有单列时保持待收集，不用每股现金流乘总股本。"
    "实控人比例只用披露字段，不用第一大股东比例代替。"
    "静态市盈率等于收盘价除以最近年报基本每股收益，每股收益不大于 0 时不计算。"
)

# Copied from rules/02-rules.md. A code that is not listed stays 无单列.
HARD_GATES = {
    "002081": "只卖",
    "601061": "现价低于 9.55 减 1000",
    "000559": "不加",
    "601868": "不加",
}

CORE_FIELDS = (
    "代码",
    "名称",
    "池别",
    "股数",
    "可用",
    "成本",
    "权重",
    "权重口径",
    "东财行业",
    "证监会行业",
    "总市值亿元",
    "持有理由",
    "关键假设",
    "验证指标",
    "破坏条件",
    "风险标签",
    "跟踪等级",
    "下次复核日",
    "当前逻辑",
    "研究动作",
    "硬门抄录",
    "核心池",
)


def _open(value) -> bool:
    return value is None or value in OPEN


def _has_st(name: str) -> bool:
    return "ST" in _text(name).upper()


def schema_paths(value, prefix: str = "") -> tuple[str, ...]:
    """Dict keys only. A list and a placeholder string occupy the same leaf."""
    if not isinstance(value, dict):
        return (prefix,)
    found: list[str] = []
    for key in value:
        path = f"{prefix}.{key}" if prefix else str(key)
        child = value[key]
        if isinstance(child, dict):
            found.extend(schema_paths(child, path))
        else:
            found.append(path)
    return tuple(found)


def blank_record(code: str, pool: str = "观察") -> dict:
    """The record a new code starts from. Pool is 实际持仓 or 观察."""
    code = normalize_code(code)
    return {
        "版本": SCHEMA_VERSION,
        "代码": code,
        "名称": GAP,
        "池别": pool,
        "取数": "未挂",
        "权重": "待提供",
        "权重口径": "待提供",
        "账户": {
            "股数": "待提供",
            "可用": "待提供",
            "成本": "待提供",
            "上一笔是否成交": "待提供",
            "行情日": "待收集",
            "收盘价": "待收集",
            "此后成交": "未知",
        },
        "人工": {key: "待填写" for key in HUMAN_KEYS},
        "画像": {
            "身份定位": {
                "公司全称": GAP,
                "概况简称": GAP,
                "行情简称": GAP,
                "东财行业": GAP,
                "证监会行业": GAP,
                "地区": GAP,
                "上市日": GAP,
                "上市板块": GAP,
                "涨跌幅上限": GAP,
                "风险警示": GAP,
                "曾用名": GAP,
                "经营范围": "待收集",
                "一句": "未填",
            },
            "行业景气": "未填",
            "商业模式": {"收入结构": "待收集", "一句": "未填"},
            "治理与股东": {
                "实控人": GAP,
                "实控人披露持股比例": GAP,
                "直接持股主体": GAP,
                "直接持股比例": GAP,
                "名册日": GAP,
                "一句": "未填",
            },
            "财务质量": {
                "口径": CALIBER,
                "覆盖": "待收集",
                "序列": "待收集",
                "毛利率": GAP,
                "净利率": GAP,
                "加权ROE": GAP,
                "经营现金流占营收": GAP,
                "经营现金流净额亿元": "待收集",
                "货币资金亿元": "待收集",
                "有息负债亿元": "待收集",
                "应收账款亿元": "待收集",
                "存货亿元": "待收集",
                "商誉亿元": "待收集",
                "非经常损益": "待收集",
                "一句": "未填",
            },
            "成长驱动": "未填",
            "估值与预期": {
                "行情日": "待收集",
                "收盘价": "待收集",
                "总股本": GAP,
                "总市值亿元": GAP,
                "静态市盈率": GAP,
                "市净率": GAP,
                "估值分位": "待收集",
                "分析师预期": "待收集",
                "一句": "未填",
            },
            "风险与跟踪": {
                "质押": GAP,
                "解禁": GAP,
                "减持": GAP,
                "处罚问询": GAP,
                "参股公司": "待收集",
                "下次复核日": "待收集",
                "一句": "未填",
            },
        },
        "当前逻辑": "未填",
        "研究动作": "待补逻辑",
        "硬门抄录": "无单列",
        "核心池": "否",
    }


def _report_named(rows: list, name: str) -> dict | None:
    for row in rows:
        if isinstance(row, dict) and _text(row.get("REPORT_DATE_NAME")) == name:
            return row
    return None


def _series_row(label: str, row: dict, with_yoy: bool) -> dict:
    item = {
        "报告": label,
        "营收亿元": _yi(row.get("TOTALOPERATEREVE")),
        "归母亿元": _yi(row.get("PARENTNETPROFIT")),
        "扣非亿元": _yi(row.get("KCFJCXSYJLR")),
        "营收同比": _gap(row.get("TOTALOPERATEREVETZ"), 2) if with_yoy else GAP,
        "归母同比": _gap(row.get("PARENTNETPROFITTZ"), 2) if with_yoy else GAP,
    }
    return item


def _single_quarter(later: dict, earlier: dict, label: str) -> dict:
    def subtract(key: str):
        new = _num(later.get(key))
        old = _num(earlier.get(key))
        if new is None or old is None:
            return GAP
        return round((new - old) / 100000000.0, 2)

    return {
        "报告": label,
        "营收亿元": subtract("TOTALOPERATEREVE"),
        "归母亿元": subtract("PARENTNETPROFIT"),
        "扣非亿元": subtract("KCFJCXSYJLR"),
        "营收同比": GAP,
        "归母同比": GAP,
    }


def _finance(rows: list | None) -> tuple[list | str, str, dict | None]:
    rows = [row for row in (rows or []) if isinstance(row, dict)]
    if not rows:
        return "待收集", "待收集", None
    annuals = [row for row in rows if _text(row.get("REPORT_DATE_NAME")).endswith("年报")]
    annuals.sort(key=lambda row: _day(row.get("REPORT_DATE")))
    annuals = annuals[-3:]
    series = [
        _series_row(_text(row.get("REPORT_DATE_NAME")), row, True) for row in annuals
    ]
    latest = rows[0]
    latest_name = _text(latest.get("REPORT_DATE_NAME"))
    if "三季" in latest_name or "中报" in latest_name:
        series.append(_series_row(latest_name, latest, True))
    if "三季" in latest_name:
        year = latest_name[:4]
        half = _report_named(rows, f"{year}中报")
        if half is not None:
            series.append(_single_quarter(latest, half, f"{year}三季单季"))
    cover = "、".join(item["报告"] for item in series) or "待收集"
    return series or "待收集", cover, latest


def _mix_percent(value) -> float | str:
    number = _num(value)
    if number is None:
        return GAP
    if abs(number) <= 1.5:
        number *= 100.0
    return round(number, 2)


def _revenue_mix(rows: list | None):
    rows = [row for row in (rows or []) if isinstance(row, dict) and row.get("ITEM_NAME")]
    if not rows:
        return "待收集"
    latest = max(_day(row.get("REPORT_DATE")) for row in rows)
    subset = [row for row in rows if _day(row.get("REPORT_DATE")) == latest]
    types = {_text(row.get("MAINOP_TYPE")) for row in subset}
    chosen = "2" if "2" in types else "1" if "1" in types else sorted(types)[0]
    label = {"1": "行业", "2": "产品", "3": "地区"}.get(chosen, chosen)
    picked = [row for row in subset if _text(row.get("MAINOP_TYPE")) == chosen]
    picked.sort(key=lambda row: _num(row.get("RANK")) or 0)
    return [
        {
            "报告期": latest,
            "口径": label,
            "项目": _text(row.get("ITEM_NAME")),
            "占比": _mix_percent(row.get("MBI_RATIO")),
        }
        for row in picked
    ]


def _cash_share(row: dict | None):
    if not row:
        return GAP
    number = _num(row.get("JYXJLYYSR"))
    if number is None:
        return GAP
    if abs(number) <= 2:
        number *= 100.0
    return round(number, 2)


def _risk_flag(survey_name: str, quote_name: str) -> str:
    survey = _text(survey_name)
    quote = _text(quote_name)
    if survey and quote and _has_st(survey) != _has_st(quote):
        return GAP
    if _has_st(survey or quote):
        return "是"
    if survey or quote:
        return "否"
    return GAP


def _unlock_text(block: dict) -> str:
    state = block.get("状态")
    if state == "无":
        return "无"
    if state != "有":
        return GAP
    amount = block.get("数量")
    if amount in (None, GAP):
        amount_text = GAP
    else:
        number = _num(amount)
        if number is not None and number.is_integer():
            amount_text = f"{int(number)}股"
        else:
            amount_text = f"{amount}股"
    return f"{block.get('日期', GAP)} {block.get('类型', GAP)} {amount_text}"


def _valuation(price, total_shares, annual: dict | None, latest: dict | None) -> dict:
    price_n = _num(price)
    shares_n = _num(total_shares)
    cap = GAP
    if price_n is not None and shares_n is not None:
        cap = round(shares_n * price_n / 100000000.0, 2)
    eps = _num((annual or {}).get("EPSJB")) if annual else None
    if price_n is None or eps is None:
        pe: object = GAP
    elif eps <= 0:
        pe = "年报每股收益为负，不计算"
    else:
        pe = round(price_n / eps, 2)
    bps = _num((latest or {}).get("BPS")) if latest else None
    if price_n is None or bps is None:
        pb: object = GAP
    elif bps <= 0:
        pb = "每股净资产不大于 0，不计算"
    else:
        pb = round(price_n / bps, 2)
    return {
        "总股本": shares_n if shares_n is not None else GAP,
        "总市值亿元": cap,
        "静态市盈率": pe,
        "市净率": pb,
    }


def _hard_gate(code: str, price) -> str:
    text = HARD_GATES.get(code)
    if text is None:
        return "无单列"
    if code != "601061":
        return text
    price_n = _num(price)
    if price_n is None:
        return "现价低于 9.55 减 1000，现价未核"
    if price_n < 9.55:
        return f"现价 {price_n} 低于 9.55，减 1000"
    return f"现价 {price_n} 不低于 9.55，减 1000 的价位未到"


def _apply_human(record: dict, holding: dict) -> None:
    for key in HUMAN_KEYS:
        value = holding.get(key)
        if not _open(value):
            record["人工"][key] = value
    ready = all(not _open(record["人工"][key]) for key in READY_KEYS)
    written = holding.get("当前逻辑")
    record["当前逻辑"] = written if ready and written in LOGIC_WORDS else "未填"
    action = holding.get("研究动作")
    if not ready:
        record["研究动作"] = "待补逻辑"
        record["核心池"] = "否"
        return
    record["研究动作"] = action if action in ACTION_WORDS else "维持跟踪"
    record["核心池"] = "是" if record["人工"]["跟踪等级"] == "核心" else "否"


def _apply_account(record: dict, holding: dict) -> None:
    account = record["账户"]
    for src, dest in (("股数", "股数"), ("可用", "可用"), ("成本", "成本")):
        if not _open(holding.get(src)):
            account[dest] = holding[src]
    if not _open(holding.get("上一笔是否成交")):
        account["上一笔是否成交"] = holding["上一笔是否成交"]
    if not _open(holding.get("名称")):
        record["名称"] = holding["名称"]
        record["画像"]["身份定位"]["行情简称"] = holding["名称"]
    price = holding.get("收")
    if not _open(price):
        account["收盘价"] = price
        record["画像"]["估值与预期"]["收盘价"] = price
    day = holding.get("收盘日")
    if not _open(day):
        account["行情日"] = day
        record["画像"]["估值与预期"]["行情日"] = day
    shot = (holding.get("截图") or {}).get("行情日") if isinstance(holding.get("截图"), dict) else None
    book_shot = holding.get("截图行情日")
    shot_day = book_shot or shot
    if shot_day and day and shot_day != day:
        account["此后成交"] = "截图日之后的成交未知"
    elif not _open(holding.get("此后成交")):
        account["此后成交"] = holding["此后成交"]


def apply_public(record: dict, bundle: dict | None, as_of: str) -> dict:
    """Fill public cells. A missing page leaves the slot untouched or 未核."""
    bundle = bundle or {}
    if not bundle or bundle.keys() <= {"code", "name"}:
        record["取数"] = "未挂"
        record["硬门抄录"] = _hard_gate(record["代码"], record["账户"]["收盘价"])
        return record
    record["取数"] = "已取"
    survey = bundle.get("survey") or {}
    basics = survey.get("jbzl") or {}
    offer = survey.get("fxxg") or {}
    identity = record["画像"]["身份定位"]
    survey_name = _text(basics.get("agjc"))
    if survey_name:
        identity["概况简称"] = survey_name
        if _open(record["名称"]) or record["名称"] == GAP:
            record["名称"] = survey_name
    quote_name = identity["行情简称"]
    if _open(quote_name) or quote_name == GAP:
        quote_name = record["名称"] if record["名称"] != GAP else survey_name
        identity["行情简称"] = quote_name or GAP
    identity["公司全称"] = _text(basics.get("gsmc")) or GAP
    identity["东财行业"] = _text(basics.get("sshy")) or GAP
    identity["证监会行业"] = _text(basics.get("sszjhhy")) or GAP
    identity["地区"] = _text(basics.get("qy")) or GAP
    identity["上市日"] = _day(offer.get("ssrq")) or GAP
    former = _text(basics.get("cym"))
    identity["曾用名"] = former or ("无" if survey_name else GAP)
    scope = _text(basics.get("jyfw"))
    if scope:
        identity["经营范围"] = scope
    flag = _risk_flag(survey_name, "" if quote_name == GAP else quote_name)
    identity["风险警示"] = flag
    regime_name = "" if flag == GAP else (quote_name if quote_name != GAP else survey_name)
    regime = board_limit(record["代码"], regime_name)
    identity["上市板块"] = regime["板块"]
    identity["涨跌幅上限"] = regime["涨跌幅上限"] if flag != GAP else GAP

    series, cover, latest = _finance(bundle.get("indicators"))
    finance = record["画像"]["财务质量"]
    finance["序列"] = series
    finance["覆盖"] = cover
    if latest:
        finance["毛利率"] = _gap(latest.get("XSMLL"), 2)
        finance["净利率"] = _gap(latest.get("XSJLL"), 2)
        finance["加权ROE"] = _gap(latest.get("ROEJQ"), 2)
        finance["经营现金流占营收"] = _cash_share(latest)

    mix = _revenue_mix(bundle.get("business"))
    record["画像"]["商业模式"]["收入结构"] = mix

    capital_rows = bundle.get("capital") or []
    capital = capital_rows[0] if capital_rows and isinstance(capital_rows[0], dict) else {}
    listed_a = capital.get("LISTED_A_SHARES")
    total_shares = capital.get("TOTAL_SHARES")
    annuals = [
        row for row in (bundle.get("indicators") or [])
        if isinstance(row, dict) and _text(row.get("REPORT_DATE_NAME")).endswith("年报")
    ]
    annuals.sort(key=lambda row: _day(row.get("REPORT_DATE")))
    annual = annuals[-1] if annuals else None
    price = record["账户"]["收盘价"]
    valued = _valuation(price, total_shares, annual, latest)
    estimate = record["画像"]["估值与预期"]
    estimate["总股本"] = valued["总股本"]
    estimate["总市值亿元"] = valued["总市值亿元"]
    estimate["静态市盈率"] = valued["静态市盈率"]
    estimate["市净率"] = valued["市净率"]

    controller_rows = bundle.get("controller") or []
    controller = controller_rows[0] if controller_rows and isinstance(controller_rows[0], dict) else {}
    govern = record["画像"]["治理与股东"]
    govern["实控人"] = _text(controller.get("HOLDER_NAME")) or GAP
    govern["实控人披露持股比例"] = _gap(controller.get("HOLD_RATIO"), 2)
    periods = bundle.get("holders") or []
    current = periods[0] if periods else {}
    holders = current.get("holders") or []
    if holders:
        top = holders[0]
        govern["直接持股主体"] = _text(top.get("name")) or GAP
        govern["直接持股比例"] = _gap(top.get("ratio"), 2)
        govern["名册日"] = current.get("day") or GAP

    record["画像"]["风险与跟踪"]["解禁"] = _unlock_text(
        next_unlock(bundle.get("unlocks"), as_of, listed_a)
    )
    record["硬门抄录"] = _hard_gate(record["代码"], price)
    return record


def build_record(code: str, bundle: dict | None, holding: dict | None, as_of: str, pool: str) -> dict:
    record = blank_record(code, pool)
    if holding:
        _apply_account(record, holding)
        _apply_human(record, holding)
    apply_public(record, bundle, as_of)
    if holding:
        _apply_human(record, holding)
    return record


def risk_label(record: dict) -> str:
    identity = record["画像"]["身份定位"]
    risk = record["画像"]["风险与跟踪"]
    known: list[str] = []
    pending: list[str] = []
    flag = identity["风险警示"]
    if flag == "是":
        known.append("风险警示")
    elif flag == GAP:
        pending.append("风险警示")
    for key in ("质押", "解禁", "减持", "处罚问询"):
        value = risk[key]
        if value in (GAP, "待收集"):
            pending.append(key)
        elif value == "无":
            known.append(f"{key}无")
        else:
            known.append(f"{key}{value}")
    if not known:
        return GAP
    if pending:
        return "；".join(known) + "；其余未核"
    return "；".join(known)


def core_row(record: dict) -> dict:
    identity = record["画像"]["身份定位"]
    return {
        "代码": record["代码"],
        "名称": record["名称"],
        "池别": record["池别"],
        "股数": record["账户"]["股数"],
        "可用": record["账户"]["可用"],
        "成本": record["账户"]["成本"],
        "权重": record["权重"],
        "权重口径": record["权重口径"],
        "东财行业": identity["东财行业"],
        "证监会行业": identity["证监会行业"],
        "总市值亿元": record["画像"]["估值与预期"]["总市值亿元"],
        "持有理由": record["人工"]["持有理由"],
        "关键假设": record["人工"]["关键假设"],
        "验证指标": record["人工"]["验证指标"],
        "破坏条件": record["人工"]["破坏条件"],
        "风险标签": risk_label(record),
        "跟踪等级": record["人工"]["跟踪等级"],
        "下次复核日": record["画像"]["风险与跟踪"]["下次复核日"],
        "当前逻辑": record["当前逻辑"],
        "研究动作": record["研究动作"],
        "硬门抄录": record["硬门抄录"],
        "核心池": record["核心池"],
    }


def apply_weights(records: list[dict]) -> None:
    """Weights need every row's shares and close. A gap does not become zero."""
    values = []
    for record in records:
        shares = _num(record["账户"]["股数"])
        price = _num(record["账户"]["收盘价"])
        values.append(None if shares is None or price is None else shares * price)
    if not records:
        return
    if all(value is None for value in values):
        weight = round(100.0 / len(records), 2)
        for record in records:
            record["权重"] = weight
            record["权重口径"] = "等权，股数未提供"
        return
    if any(value is None for value in values):
        for record in records:
            record["权重"] = "待提供"
            record["权重口径"] = "股数或收盘不齐，权重待提供"
        return
    total = sum(values)
    for record, value in zip(records, values):
        record["权重"] = round(value / total * 100.0, 2)
        record["权重口径"] = "持仓市值"


def _industry_counts(records: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for record in records:
        name = record["画像"]["身份定位"]["东财行业"]
        if _open(name) or name == GAP:
            name = "未核"
        counts[name] = counts.get(name, 0) + 1
    return counts


def _position_value(records: list[dict]):
    if any(record["权重口径"] != "持仓市值" for record in records):
        return "待提供"
    total = 0.0
    for record in records:
        shares = _num(record["账户"]["股数"])
        price = _num(record["账户"]["收盘价"])
        if shares is None or price is None:
            return "待提供"
        total += shares * price
    return round(total, 2)


def assemble_book(records: list[dict], as_of: str, note: str = "") -> dict:
    apply_weights(records)
    rows = [core_row(record) for record in records]
    ranked = sorted(
        (row for row in rows if isinstance(row["权重"], (int, float))),
        key=lambda row: row["权重"],
        reverse=True,
    )
    top = ranked[:5]
    top_share = round(sum(row["权重"] for row in top), 2) if top and len(ranked) == len(rows) else "待提供"
    return {
        "版本": SCHEMA_VERSION,
        "北京时间": as_of,
        "目标与边界": {
            "池别": "实际持仓",
            "跟踪频率": "周报写到点的事件，月报写组合，季报对财报",
            "目标": "逻辑验证、风险排查",
            "约束": "研究动作不下单。硬门另列，不在这里改写。",
        },
        "口径字典": CALIBER,
        "持仓总表": rows,
        "个股记录": records,
        "组合仪表盘": {
            "只数": len(records),
            "持仓市值": _position_value(records),
            "权重口径": records[0]["权重口径"] if records else "待提供",
            "东财行业只数": _industry_counts(records),
            "前五大代码": [row["代码"] for row in top] if top_share != "待提供" else "待提供",
            "前五大占比": top_share,
            "共同因子": "待填写",
            "事件重叠": "待收集",
            "变现天数": "待收集",
            "核心池": [record["代码"] for record in records if record["核心池"] == "是"],
            "硬门抄录": [
                {"代码": record["代码"], "名称": record["名称"], "硬门抄录": record["硬门抄录"]}
                for record in records
                if record["硬门抄录"] != "无单列"
            ],
        },
        "跟踪预警": [
            {
                "代码": record["代码"],
                "名称": record["名称"],
                "验证指标": record["人工"]["验证指标"],
                "频率": "待填写",
                "研究动作": record["研究动作"],
                "下次复核日": record["画像"]["风险与跟踪"]["下次复核日"],
            }
            for record in records
        ],
        "复盘记录": {
            "节奏": "周报、月报、季报、事件驱动",
            "条目": [],
        },
        "说明": note,
    }


def book_from_holdings(doc: dict, bundles: dict[str, dict] | None, as_of: str) -> dict:
    bundles = bundles or {}
    records = []
    shot_day = (doc.get("截图") or {}).get("行情日")
    for holding in doc.get("持仓") or []:
        if not isinstance(holding, dict) or not holding.get("代码"):
            continue
        code = normalize_code(str(holding["代码"]))
        merged = dict(holding)
        if shot_day and _open(merged.get("截图行情日")):
            merged["截图行情日"] = shot_day
        records.append(
            build_record(code, bundles.get(code), merged, as_of, "实际持仓")
        )
    note = _text(doc.get("说明"))
    return assemble_book(records, as_of, note)


def load_holdings(path: Path | None = None) -> dict:
    file = path or HOLDINGS_PATH
    return json.loads(file.read_text(encoding="utf-8"))


def dump_book(book: dict, path: Path | None = None) -> Path:
    file = path or BOOK_PATH
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return file


def self_check() -> int:
    failed = 0

    def check(label: str, cond: bool) -> None:
        nonlocal failed
        if not cond:
            failed += 1
            print("FAIL", label)

    fresh = blank_record("600000")
    other = blank_record("300001", "实际持仓")
    check("schema version", fresh["版本"] == 1)
    check("new codes share keys", schema_paths(fresh) == schema_paths(other))
    check("core field count", 20 <= len(CORE_FIELDS) <= 30)
    check("blank logic stays unwritten", fresh["当前逻辑"] == "未填" and fresh["研究动作"] == "待补逻辑")
    check("blank is outside the core pool", fresh["核心池"] == "否")
    row = core_row(fresh)
    check("core row keys", tuple(row) == CORE_FIELDS)

    bundle = {
        "code": "601061",
        "survey": {"jbzl": {"agjc": "中信金属", "gsmc": "中信金属股份有限公司", "sshy": "贸易行业", "sszjhhy": "批发业", "qy": "北京"}, "fxxg": {"ssrq": "2023-04-10"}},
        "indicators": [
            {"REPORT_DATE": "2026-09-30", "REPORT_DATE_NAME": "2026三季报", "TOTALOPERATEREVE": 300000000, "PARENTNETPROFIT": 20000000, "KCFJCXSYJLR": 18000000, "TOTALOPERATEREVETZ": 22.15, "PARENTNETPROFITTZ": 62.01, "XSMLL": 2.06, "XSJLL": 2.98, "ROEJQ": 15.38, "JYXJLYYSR": 0.0687, "EPSJB": 0.2, "BPS": 5.0},
            {"REPORT_DATE": "2026-06-30", "REPORT_DATE_NAME": "2026中报", "TOTALOPERATEREVE": 100000000, "PARENTNETPROFIT": 8000000, "KCFJCXSYJLR": 7000000},
            {"REPORT_DATE": "2025-12-31", "REPORT_DATE_NAME": "2025年报", "TOTALOPERATEREVE": 400000000, "PARENTNETPROFIT": -1000000, "KCFJCXSYJLR": 1000000, "EPSJB": -0.1, "BPS": 4.0},
        ],
        "capital": [{"TOTAL_SHARES": 100000000, "LISTED_A_SHARES": 100000000}],
        "controller": [{"HOLDER_NAME": "中国中信集团有限公司", "HOLD_RATIO": None}],
        "holders": [{"day": "2026-09-30", "holders": [{"name": "中信金属集团有限公司", "ratio": 89.71}]}],
        "unlocks": [],
        "business": [
            {"REPORT_DATE": "2026-06-30", "MAINOP_TYPE": "2", "ITEM_NAME": "有色金属产品", "MBI_RATIO": 0.8396, "RANK": 1},
        ],
    }
    holding = {"代码": "601061", "名称": "中信金属", "股数": 4000, "可用": 4000, "成本": 9.988, "收": 8.08, "收盘日": "2026-11-25", "上一笔是否成交": "截图未显示"}
    filled = build_record("601061", bundle, holding, "2026-11-25", "实际持仓")
    check("filled keeps the blank keys", schema_paths(filled) == schema_paths(fresh))
    govern = filled["画像"]["治理与股东"]
    check("controller ratio stays unchecked", govern["实控人披露持股比例"] == GAP)
    check("direct holder is separate", govern["直接持股主体"] == "中信金属集团有限公司" and govern["直接持股比例"] == 89.71)
    check("negative annual eps is not a pe", filled["画像"]["估值与预期"]["静态市盈率"] == "年报每股收益为负，不计算")
    check("single quarter is the difference", filled["画像"]["财务质量"]["序列"][-1]["报告"] == "2026三季单季")
    check("single quarter revenue", filled["画像"]["财务质量"]["序列"][-1]["营收亿元"] == 2.0)
    check("citic gate uses the close", filled["硬门抄录"] == "现价 8.08 低于 9.55，减 1000")
    check("gate is not the research action", filled["研究动作"] == "待补逻辑")
    check("mix uses the product share", filled["画像"]["商业模式"]["收入结构"][0]["占比"] == 83.96)

    conflict = build_record(
        "600715",
        {"survey": {"jbzl": {"agjc": "*ST文投", "sshy": "游戏"}}},
        {"代码": "600715", "名称": "文投控股"},
        "2026-11-25",
        "实际持仓",
    )
    check("conflicting st flag stays unchecked", conflict["画像"]["身份定位"]["风险警示"] == GAP)
    check("unchecked flag does not force the five-point cap", conflict["画像"]["身份定位"]["涨跌幅上限"] == GAP)

    ready = {
        "代码": "000001",
        "名称": "示例",
        "股数": 100,
        "收": 10,
        "收盘日": "2026-11-25",
        "持有理由": "示例理由",
        "关键假设": "价",
        "验证指标": "毛利率",
        "破坏条件": "毛利率跌破 10",
        "跟踪等级": "核心",
        "当前逻辑": "被验证",
        "研究动作": "维持跟踪",
    }
    admitted = build_record("000001", None, ready, "2026-11-25", "实际持仓")
    check("ready name can enter the core pool", admitted["核心池"] == "是" and admitted["当前逻辑"] == "被验证")
    ready["破坏条件"] = "待填写"
    refused = build_record("000001", None, ready, "2026-11-25", "实际持仓")
    check("core label without a break condition stays out", refused["核心池"] == "否" and refused["当前逻辑"] == "未填")

    book = book_from_holdings(
        {"持仓": [holding, {"代码": "600000", "名称": "浦发银行"}], "说明": "示例"},
        {"601061": bundle},
        "2026-11-25",
    )
    check("partial shares withhold every weight", all(row["权重"] == "待提供" for row in book["持仓总表"]))
    check("tracking row uses the stock's own indicator", book["跟踪预警"][0]["验证指标"] == "待填写")
    check("review log starts empty", book["复盘记录"]["条目"] == [])
    equal = book_from_holdings({"持仓": [{"代码": "600000"}, {"代码": "600004"}]}, {}, "2026-11-25")
    check("missing shares are labeled equal weight", equal["组合仪表盘"]["权重口径"] == "等权，股数未提供")
    mantis = build_record("002081", None, {"代码": "002081"}, "2026-11-25", "实际持仓")
    check("mantis gate stays sell-only", mantis["硬门抄录"] == "只卖" and mantis["研究动作"] == "待补逻辑")
    if failed:
        print(failed, "failed")
        return 1
    print("ok")
    return 0
