#!/usr/bin/env python3
"""Build one stock's fundamental portrait from public company facts.

The sheet is the company. Market news, the tape, and sentiment stay off it.
A missing cell is 未核. Nothing here changes W1–W8 or places an order.
"""

from __future__ import annotations

import argparse
import json
import sys

from astock.net import open_url
from astock.sector_drive import (
    _holder_name,
    earnings_state,
    prior_complex,
    state_capital,
)
from astock.intraday_screen import judge_holders

EARNINGS_WORD = {"pass": "过", "fail": "不过", "unchecked": "未核"}
GAP = "未核"


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _day(value) -> str:
    text = _text(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def _gap(value, digits: int | None = None):
    if value is None or value == "":
        return GAP
    number = _num(value)
    if number is None:
        text = _text(value)
        return text or GAP
    if digits is None:
        return number
    return round(number, digits)


def _yi(value):
    number = _num(value)
    if number is None:
        return GAP
    return round(number / 100000000.0, 2)


def normalize_code(code: str) -> str:
    text = code.strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if text.endswith((".SH", ".SZ", ".BJ")):
        text = text.split(".", 1)[0]
    if not text.isdigit() or len(text) != 6:
        raise ValueError(f"无法识别的代码: {code}")
    return text


def market_suffix(code: str) -> str:
    if code.startswith(("5", "6", "9")):
        return "SH"
    if code.startswith(("43", "83", "87", "92", "4", "8")):
        return "BJ"
    return "SZ"


def board_limit(code: str, name: str) -> dict:
    """The price-limit regime is a listing fact. ST uses the current name only."""
    label = _text(name).upper()
    risk = "是" if "ST" in label else "否"
    if code.startswith(("300", "301")):
        board, cap = "创业板", 20
    elif code.startswith(("688", "689")):
        board, cap = "科创板", 20
    elif code.startswith(("43", "83", "87", "92")):
        board, cap = "北交所", 30
    elif code.startswith(("600", "601", "603", "605", "000", "001", "002", "003")):
        board, cap = "主板", 10
    else:
        board, cap = GAP, None
    if risk == "是":
        cap = 5
    return {"板块": board, "涨跌幅上限": cap if cap is not None else GAP, "风险警示": risk}


def deducted_turn(latest, prior) -> str:
    """Two deducted-profit figures. A missing one stays 未核."""
    new = _num(latest)
    old = _num(prior)
    if new is None or old is None:
        return GAP
    if old < 0 < new:
        return "由负转正"
    if new < 0 < old:
        return "由正转负"
    if new > 0 and old > 0:
        return "连续为正"
    if new < 0 and old < 0:
        return "连续为负"
    return "触及零"


def holder_count_direction(ratio) -> str:
    number = _num(ratio)
    if number is None:
        return GAP
    if number < 0:
        return "下降"
    if number > 0:
        return "上升"
    return "不变"


def next_unlock(rows: list | None, as_of: str, listed_a) -> dict:
    """The earliest lift on or after as_of. A missing page stays 未核. No future batch is 无."""
    if rows is None:
        return {"状态": GAP}
    future = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        day = _day(row.get("LIFT_DATE"))
        if len(day) == 10 and day >= as_of:
            future.append(row)
    if not future:
        return {"状态": "无"}
    future.sort(key=lambda row: _day(row.get("LIFT_DATE")))
    chosen = future[0]
    shares = _num(chosen.get("LIFT_NUM"))
    listed = _num(listed_a)
    ratio = GAP
    if shares is not None and listed is not None and listed > 0:
        ratio = round(shares / listed * 100.0, 2)
    return {
        "状态": "有",
        "日期": _day(chosen.get("LIFT_DATE")),
        "数量": shares if shares is not None else GAP,
        "类型": _text(chosen.get("LIFT_TYPE")) or GAP,
        "占总股本比例": _gap(chosen.get("TOTAL_SHARES_RATIO"), 2),
        "占流通A股比例": ratio,
    }


def _holders_view(periods: list | None) -> dict:
    periods = periods or []
    judged = judge_holders(periods)
    current = periods[0] if periods else {}
    names = []
    for holder in (current.get("holders") or [])[:10]:
        names.append(
            {
                "名称": _holder_name(holder),
                "比例": _gap(holder.get("ratio"), 2),
                "变动": _change(holder.get("change")),
            }
        )
    capital = state_capital(current.get("holders") or [])
    prior_lists = [period.get("holders") or [] for period in periods]
    return {
        "本期": current.get("day") or GAP,
        "上一期": periods[1].get("day") if len(periods) > 1 else GAP,
        "名单": names,
        "结构": judged.get("simple") or GAP,
        "复杂股东": judged.get("complex_one") or "",
        "上一期复杂股东": prior_complex(prior_lists),
        "国资新进": judged.get("state") or GAP,
        "国资新进名单": [
            {"名称": hit.get("name"), "比例": _gap(hit.get("ratio"), 2)}
            for hit in judged.get("hits") or []
        ],
        "国资在列": [
            {"名称": row["name"], "比例": _gap(row.get("ratio"), 2)}
            for row in capital["listed"]
        ],
        "国有资产在旁": [
            {"名称": row["name"], "比例": _gap(row.get("ratio"), 2)}
            for row in capital["beside"]
        ],
    }


def _org_total(rows: list | None) -> dict:
    chosen = None
    for row in rows or []:
        if isinstance(row, dict) and _text(row.get("ORG_TYPE")) == "00":
            chosen = row
            break
    if chosen is None:
        return {"家数": GAP, "占流通股比例": GAP, "报告期": GAP}
    return {
        "家数": _gap(chosen.get("TOTAL_ORG_NUM")),
        "占流通股比例": _gap(chosen.get("TOTAL_SHARES_RATIO"), 2),
        "报告期": _day(chosen.get("REPORT_DATE")) or GAP,
    }


def _finance_row(rows: list | None, index: int) -> dict:
    if not rows or len(rows) <= index or not isinstance(rows[index], dict):
        return {}
    return rows[index]


def portrait(bundle: dict, as_of: str) -> dict:
    """Fold already fetched pages into one sheet. Missing pages stay 未核."""
    code = normalize_code(str(bundle.get("code") or ""))
    survey = bundle.get("survey") or {}
    basics = survey.get("jbzl") or {}
    offer = survey.get("fxxg") or {}
    name = _text(basics.get("agjc")) or _text(bundle.get("name")) or GAP
    finance = _finance_row(bundle.get("indicators"), 0)
    prior_finance = _finance_row(bundle.get("indicators"), 1)
    capital = {}
    rows = bundle.get("capital") or []
    if rows and isinstance(rows[0], dict):
        capital = rows[0]
    counts = bundle.get("holder_counts") or []
    latest_count = counts[0] if counts and isinstance(counts[0], dict) else {}
    prior_count = counts[1] if len(counts) > 1 and isinstance(counts[1], dict) else {}
    controller = {}
    controllers = bundle.get("controller") or []
    if controllers and isinstance(controllers[0], dict):
        controller = controllers[0]
    earnings = EARNINGS_WORD[earnings_state(
        finance.get("PARENTNETPROFIT"),
        finance.get("PARENTNETPROFITTZ"),
        finance.get("TOTALOPERATEREVETZ"),
    )]
    listed_a = capital.get("LISTED_A_SHARES")
    regime = board_limit(code, "" if name == GAP else name)
    former = _text(basics.get("cym"))
    return {
        "代码": code,
        "名称": name,
        "截止": as_of,
        "范围": "公司事实",
        "另开": ["市场信息", "技术面", "市场情绪"],
        "身份": {
            "公司全称": _text(basics.get("gsmc")) or GAP,
            "行业": _text(basics.get("sshy")) or GAP,
            "证监会行业": _text(basics.get("sszjhhy")) or GAP,
            "地区": _text(basics.get("qy")) or GAP,
            "上市日": _day(offer.get("ssrq")) or GAP,
            "证券类别": _text(basics.get("zqlb")) or GAP,
            "曾用名": former or "无",
        },
        "机构": {
            "报告期": _day(finance.get("REPORT_DATE")) or GAP,
            "报告名称": _text(finance.get("REPORT_DATE_NAME")) or GAP,
            "营业总收入亿元": _yi(finance.get("TOTALOPERATEREVE")),
            "营收同比": _gap(finance.get("TOTALOPERATEREVETZ"), 2),
            "归母净利润亿元": _yi(finance.get("PARENTNETPROFIT")),
            "归母同比": _gap(finance.get("PARENTNETPROFITTZ"), 2),
            "扣非净利润亿元": _yi(finance.get("KCFJCXSYJLR")),
            "扣非同比": _gap(finance.get("KCFJCXSYJLRTZ"), 2),
            "毛利率": _gap(finance.get("XSMLL"), 2),
            "净利率": _gap(finance.get("XSJLL"), 2),
            "加权ROE": _gap(finance.get("ROEJQ"), 2),
            "扣非加权ROE": _gap(finance.get("ROEKCJQ"), 2),
            "基本每股收益": _gap(finance.get("EPSJB"), 4),
            "每股净资产": _gap(finance.get("BPS"), 2),
            "每股经营现金流": _gap(finance.get("MGJYXJJE"), 4),
            "经营现金流占营收": _gap(finance.get("JYXJLYYSR"), 4),
            "资产负债率": _gap(finance.get("ZCFZL"), 2),
            "流动比率": _gap(finance.get("LD"), 2),
            "业绩": earnings,
            "扣非拐点": deducted_turn(
                finance.get("KCFJCXSYJLR"),
                prior_finance.get("KCFJCXSYJLR"),
            ),
        },
        "主力": {
            "实际控制人": _text(controller.get("HOLDER_NAME")) or GAP,
            "实控人披露持股比例": _gap(controller.get("HOLD_RATIO"), 2),
            "前十大": _holders_view(bundle.get("holders")),
            "股东户数": {
                "本期": _day(latest_count.get("END_DATE")) or GAP,
                "户数": _gap(latest_count.get("HOLDER_TOTAL_NUM")),
                "环比": _gap(latest_count.get("TOTAL_NUM_RATIO"), 2),
                "方向": holder_count_direction(latest_count.get("TOTAL_NUM_RATIO")),
                "来源原词": _text(latest_count.get("HOLD_FOCUS")) or GAP,
                "上一期": _day(prior_count.get("END_DATE")) or GAP,
                "上一期户数": _gap(prior_count.get("HOLDER_TOTAL_NUM")),
            },
            "机构合计": _org_total(bundle.get("institutions")),
            "解禁": next_unlock(bundle.get("unlocks"), as_of, listed_a),
        },
        "游资": {
            **regime,
            "总股本": _gap(capital.get("TOTAL_SHARES")),
            "流通A股": _gap(listed_a),
            "限售股": _gap(capital.get("LIMITED_SHARES")),
            "限售占总股本": _gap(capital.get("LIMITED_SHARES_RATIO"), 2),
            "解禁": next_unlock(bundle.get("unlocks"), as_of, listed_a),
            "股东户数环比": _gap(latest_count.get("TOTAL_NUM_RATIO"), 2),
            "户数方向": holder_count_direction(latest_count.get("TOTAL_NUM_RATIO")),
            "扣非拐点": deducted_turn(
                finance.get("KCFJCXSYJLR"),
                prior_finance.get("KCFJCXSYJLR"),
            ),
        },
    }


def _get_json(url: str):
    with open_url(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://emweb.securities.eastmoney.com/",
        },
        timeout=20,
    ) as resp:
        raw = resp.read().decode("utf-8", "replace").lstrip("\ufeff")
    if raw.lstrip().startswith("<"):
        return None
    return json.loads(raw)


def _fetch_page(url: str):
    try:
        return _get_json(url)
    except Exception:
        return None


def fetch_bundle(code: str) -> dict:
    """Public Eastmoney pages. A failed page is None and becomes 未核."""
    code = normalize_code(code)
    suffix = market_suffix(code)
    em = f"{suffix}{code}"
    survey = _fetch_page(
        "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
        f"?code={em}"
    )
    indicators = _fetch_page(
        "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew"
        f"?type=0&code={em}"
    )
    capital = _fetch_page(
        "https://emweb.securities.eastmoney.com/PC_HSF10/CapitalStockStructure/PageAjax"
        f"?code={em}"
    )
    research = _fetch_page(
        "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax"
        f"?code={em}"
    )
    holders_payload = _fetch_page(
        "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_F10_EH_HOLDERS"
        "&columns=END_DATE,HOLDER_RANK,HOLDER_NAME,HOLD_NUM_RATIO,HOLD_NUM_CHANGE"
        f"&filter=(SECUCODE=%22{code}.{suffix}%22)(IS_REPORT=%221%22)"
        "&pageNumber=1&pageSize=40&sortColumns=END_DATE,HOLDER_RANK&sortTypes=-1,1"
    )
    return {
        "code": code,
        "survey": survey if isinstance(survey, dict) else {},
        "indicators": (indicators or {}).get("data") if isinstance(indicators, dict) else None,
        "capital": (capital or {}).get("gbjg") if isinstance(capital, dict) else None,
        "unlocks": (capital or {}).get("xsjj") if isinstance(capital, dict) else None,
        "holder_counts": (research or {}).get("gdrs") if isinstance(research, dict) else None,
        "controller": (research or {}).get("sjkzr") if isinstance(research, dict) else None,
        "institutions": (research or {}).get("jgcc") if isinstance(research, dict) else None,
        "holders": _periods(holders_payload),
    }


def _periods(payload) -> list[dict]:
    data = ((payload or {}).get("result") or {}).get("data") or []
    periods: list[dict] = []
    current = None
    bucket: list[dict] = []
    for row in data:
        day = _day(row.get("END_DATE"))
        if day != current:
            if bucket:
                periods.append({"day": current, "holders": bucket})
            current = day
            bucket = []
        if len(bucket) < 10 and row.get("HOLDER_NAME"):
            bucket.append(
                {
                    "name": row["HOLDER_NAME"],
                    "ratio": row.get("HOLD_NUM_RATIO"),
                    "change": row.get("HOLD_NUM_CHANGE"),
                }
            )
    if bucket:
        periods.append({"day": current, "holders": bucket})
    return periods[:2]


def _line(label: str, value) -> str:
    if isinstance(value, float):
        shown = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        shown = value
    return f"{label}: {shown}"


def format_portrait(sheet: dict) -> str:
    identity = sheet["身份"]
    inst = sheet["机构"]
    force = sheet["主力"]
    hot = sheet["游资"]
    count = force["股东户数"]
    org = force["机构合计"]
    lines = [
        f"基本面画像 {sheet['代码']} {sheet['名称']}",
        f"截止: {sheet['截止']}",
        "这张表只写公司事实。市场信息、技术面、市场情绪另开。不进 W1–W8，不下单。",
        "身份",
        _line("公司全称", identity["公司全称"]),
        _line("行业", identity["行业"]),
        _line("证监会行业", identity["证监会行业"]),
        _line("地区", identity["地区"]),
        _line("上市日", identity["上市日"]),
        _line("证券类别", identity["证券类别"]),
        _line("曾用名", identity["曾用名"]),
        "机构",
        _line("报告期", f"{inst['报告期']} {inst['报告名称']}".strip()),
        _line("营业总收入亿元", inst["营业总收入亿元"]),
        _line("营收同比", inst["营收同比"]),
        _line("归母净利润亿元", inst["归母净利润亿元"]),
        _line("归母同比", inst["归母同比"]),
        _line("扣非净利润亿元", inst["扣非净利润亿元"]),
        _line("扣非同比", inst["扣非同比"]),
        _line("毛利率", inst["毛利率"]),
        _line("净利率", inst["净利率"]),
        _line("加权ROE", inst["加权ROE"]),
        _line("扣非加权ROE", inst["扣非加权ROE"]),
        _line("基本每股收益", inst["基本每股收益"]),
        _line("每股净资产", inst["每股净资产"]),
        _line("每股经营现金流", inst["每股经营现金流"]),
        _line("经营现金流占营收", inst["经营现金流占营收"]),
        _line("资产负债率", inst["资产负债率"]),
        _line("流动比率", inst["流动比率"]),
        _line("业绩", inst["业绩"]),
        _line("扣非拐点", inst["扣非拐点"]),
        "主力",
        _line("实际控制人", force["实际控制人"]),
        _line("实控人披露持股比例", force["实控人披露持股比例"]),
        _format_holders(force["前十大"]),
        _line("股东户数本期", count["本期"]),
        _line("股东户数", count["户数"]),
        _line("股东户数环比", count["环比"]),
        _line("户数方向", count["方向"]),
        _line("户数来源原词", count["来源原词"]),
        _line("上一期户数日", count["上一期"]),
        _line("上一期户数", count["上一期户数"]),
        _line("机构家数", org["家数"]),
        _line("机构占流通股比例", org["占流通股比例"]),
        _line("机构合计报告期", org["报告期"]),
        _format_unlock("解禁", force["解禁"]),
        "游资",
        _line("板块", hot["板块"]),
        _line("涨跌幅上限", hot["涨跌幅上限"]),
        _line("风险警示", hot["风险警示"]),
        _line("总股本", hot["总股本"]),
        _line("流通A股", hot["流通A股"]),
        _line("限售股", hot["限售股"]),
        _line("限售占总股本", hot["限售占总股本"]),
        _line("股东户数环比", hot["股东户数环比"]),
        _line("户数方向", hot["户数方向"]),
        _line("扣非拐点", hot["扣非拐点"]),
        _format_unlock("解禁", hot["解禁"]),
    ]
    return "\n".join(lines)


def _format_holders(block: dict) -> str:
    lines = [
        f"前十大本期: {block['本期']}",
        f"前十大上一期: {block['上一期']}",
        f"结构: {block['结构']}",
    ]
    if block["复杂股东"]:
        lines.append(f"复杂股东: {block['复杂股东']}")
    if block["上一期复杂股东"]:
        lines.append("上一期复杂股东: " + "、".join(block["上一期复杂股东"]))
    lines.append(f"国资新进: {block['国资新进']}")
    for hit in block["国资新进名单"]:
        lines.append(f"国资新进股东: {hit['名称']} {hit['比例']}")
    for row in block["国资在列"]:
        lines.append(f"国资在列: {row['名称']} {row['比例']}")
    for row in block["国有资产在旁"]:
        lines.append(f"国有资产在旁: {row['名称']} {row['比例']}")
    for row in block["名单"]:
        lines.append(f"股东: {row['名称']} {row['比例']} {row['变动']}")
    if not block["名单"]:
        lines.append("股东: 未核")
    return "\n".join(lines)


def _format_unlock(label: str, block: dict) -> str:
    if block.get("状态") == "无":
        return f"{label}: 无"
    if block.get("状态") != "有":
        return f"{label}: 未核"
    return (
        f"{label}: {block['日期']} {block['类型']} {_whole(block['数量'])}股"
        f" 占总股本{block['占总股本比例']}% 占流通A股{block['占流通A股比例']}%"
    )


def _change(value) -> str:
    text = _text(value)
    if not text:
        return GAP
    number = _num(text)
    if number is None:
        return text
    return f"{_whole(number)}股"


def _whole(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _sample_bundle() -> dict:
    holders = [{"name": f"股东{i}", "ratio": 1, "change": "不变"} for i in range(10)]
    holders[0] = {"name": "全国社保基金一零一组合", "ratio": 2.5, "change": "新进"}
    holders[1] = {"name": "香港中央结算有限公司", "ratio": 5.3, "change": "-349449803"}
    prior = [{"name": f"旧股东{i}", "ratio": 1, "change": "不变"} for i in range(10)]
    prior[0] = {"name": "示例企业管理合伙企业(有限合伙)", "ratio": 1, "change": "不变"}
    return {
        "code": "000725",
        "survey": {
            "jbzl": {
                "gsmc": "示例股份有限公司",
                "agjc": "示例",
                "sshy": "光学光电子",
                "sszjhhy": "制造业-计算机、通信和其他电子设备制造业",
                "qy": "北京",
                "zqlb": "深市A股",
                "cym": "*ST示例->示例",
            },
            "fxxg": {"ssrq": "2001-01-12 00:00:00"},
        },
        "indicators": [
            {
                "REPORT_DATE": "2026-09-30 00:00:00",
                "REPORT_DATE_NAME": "2026三季报",
                "TOTALOPERATEREVE": 151800000000,
                "TOTALOPERATEREVETZ": -1.77,
                "PARENTNETPROFIT": 4200000000,
                "PARENTNETPROFITTZ": -7.61,
                "KCFJCXSYJLR": 300000000,
                "KCFJCXSYJLRTZ": -4.3,
                "XSMLL": 15.27,
                "XSJLL": 2.23,
                "ROEJQ": 3.14,
                "ROEKCJQ": 2.1,
                "EPSJB": 0.11,
                "BPS": 3.55,
                "MGJYXJJE": 0.87,
                "JYXJLYYSR": 0.21,
                "ZCFZL": 53.26,
                "LD": 1.3,
            },
            {"KCFJCXSYJLR": -100000000},
        ],
        "capital": [{
            "TOTAL_SHARES": 1000,
            "LISTED_A_SHARES": 800,
            "LIMITED_SHARES": 200,
            "LIMITED_SHARES_RATIO": 20,
        }],
        "unlocks": [
            {
                "LIFT_DATE": "2020-01-01 00:00:00",
                "LIFT_NUM": 10,
                "LIFT_TYPE": "已过",
                "TOTAL_SHARES_RATIO": 1,
            },
            {
                "LIFT_DATE": "2026-12-01 00:00:00",
                "LIFT_NUM": 80,
                "LIFT_TYPE": "股权激励限售股份",
                "TOTAL_SHARES_RATIO": 8,
            },
        ],
        "holder_counts": [
            {
                "END_DATE": "2026-09-30 00:00:00",
                "HOLDER_TOTAL_NUM": 1800000,
                "TOTAL_NUM_RATIO": -6.36,
                "HOLD_FOCUS": "非常分散",
            },
            {"END_DATE": "2026-06-30 00:00:00", "HOLDER_TOTAL_NUM": 1920000},
        ],
        "controller": [{"HOLDER_NAME": "示例控股有限责任公司", "HOLD_RATIO": 3.46}],
        "institutions": [{
            "ORG_TYPE": "00",
            "REPORT_DATE": "2026-09-30 00:00:00",
            "TOTAL_ORG_NUM": 236,
            "TOTAL_SHARES_RATIO": 27.45,
        }],
        "holders": [
            {"day": "2026-09-30", "holders": holders},
            {"day": "2026-06-30", "holders": prior},
        ],
    }


def self_check() -> int:
    failed = 0

    def check(label, cond):
        nonlocal failed
        if not cond:
            failed += 1
            print("FAIL", label)

    sheet = portrait(_sample_bundle(), "2026-11-25")
    check("name", sheet["名称"] == "示例")
    check("earnings fail on a shrinking profit", sheet["机构"]["业绩"] == "不过")
    check("deducted turns positive", sheet["机构"]["扣非拐点"] == "由负转正")
    check("simple despite prior names", sheet["主力"]["前十大"]["结构"] == "简单")
    check(
        "prior partnership is named",
        sheet["主力"]["前十大"]["上一期复杂股东"] == ["示例企业管理合伙企业(有限合伙)"],
    )
    check("new social fund", sheet["主力"]["前十大"]["国资新进"] == "有")
    check("share delta keeps its unit", sheet["主力"]["前十大"]["名单"][1]["变动"] == "-349449803股")
    check("holder count down", sheet["主力"]["股东户数"]["方向"] == "下降")
    check("next unlock skips the past", sheet["游资"]["解禁"]["日期"] == "2026-12-01")
    check("unlock versus float", sheet["游资"]["解禁"]["占流通A股比例"] == 10.0)
    check("main board ten", sheet["游资"]["涨跌幅上限"] == 10)
    check("former st is not the current flag", sheet["游资"]["风险警示"] == "否")
    check("revenue in yi", sheet["机构"]["营业总收入亿元"] == 1518.0)
    empty = portrait({"code": "600000"}, "2026-11-25")
    check("empty finance stays unchecked", empty["机构"]["业绩"] == "未核")
    check("empty holders stay unchecked", empty["主力"]["前十大"]["结构"] == "未核")
    check("missing unlock page stays unchecked", empty["游资"]["解禁"]["状态"] == "未核")
    none_left = portrait({"code": "600000", "unlocks": []}, "2026-11-25")
    check("opened page with no future batch", none_left["游资"]["解禁"]["状态"] == "无")
    starred = board_limit("300001", "*ST示例")
    check("st cap is five", starred["涨跌幅上限"] == 5 and starred["风险警示"] == "是")
    star = board_limit("688981", "中芯国际")
    check("star board twenty", star["板块"] == "科创板" and star["涨跌幅上限"] == 20)
    text = format_portrait(sheet)
    check("sheet names the three readings", "机构" in text and "主力" in text and "游资" in text)
    for word in ("开仓", "加仓", "买入", "Buy"):
        check(f"no order word {word}", word not in text)
    if failed:
        print(failed, "failed")
        return 1
    print("ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="印出一只股票的基本面画像。不下单。")
    parser.add_argument("code", nargs="?", help="六位代码")
    parser.add_argument("--as-of", default="2026-11-25", help="解禁按这个日期看下一笔，北京时间的日期")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    if not args.code:
        parser.print_usage(sys.stderr)
        return 2
    try:
        code = normalize_code(args.code)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sheet = portrait(fetch_bundle(code), args.as_of)
    print(format_portrait(sheet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
