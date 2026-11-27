#!/usr/bin/env python3
"""Print one stock portrait in six blocks that update on different clocks.

Filled cells come from public pages already wired. Everything else stays
待收集, and a sentence that needs those cells stays 未填. Nothing here
changes W1–W8 or places an order.
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


NOT_APPLICABLE = "不适用"

FINANCE_INDUSTRIES = ("银行", "保险", "券商信托", "多元金融")

# 银行、保险、券商各用一张资产负债表，科目名互不相同。用错报表名拿到的是
# 空表，看起来像「页面挂了」，其实只是问错了表。
FINANCE_BALANCE_REPORTS = {
    "银行": "RPT_F10_FINANCE_BBALANCE",
    "保险": "RPT_F10_FINANCE_IBALANCE",
    "券商信托": "RPT_F10_FINANCE_SBALANCE",
    "多元金融": "RPT_F10_FINANCE_SBALANCE",
}


def _finance_report(industry: str) -> str | None:
    text = _text(industry)
    for word, report in FINANCE_BALANCE_REPORTS.items():
        if word in text:
            return report
    return None


def _is_finance(industry: str) -> bool:
    return any(word in _text(industry) for word in FINANCE_INDUSTRIES)


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


def _restricted(capital: dict) -> tuple:
    """Restricted A-shares, or a gap when the page does not let us tell.

    Some H-share issuers leave LIMITED_SHARES empty even though the same page
    carries total, listed-A and H-share counts. When total minus listed-A minus
    H shares is exactly zero, restricted A is zero by arithmetic on that page.
    Anything else stays 未核 rather than being inferred.
    """
    limited = _num(capital.get("LIMITED_SHARES"))
    if limited is not None:
        return limited, _num(capital.get("LIMITED_SHARES_RATIO"))
    total = _num(capital.get("TOTAL_SHARES"))
    listed_a = _num(capital.get("LISTED_A_SHARES"))
    h_free = _num(capital.get("H_FREE_SHARE")) or 0.0
    b_free = _num(capital.get("B_FREE_SHARE")) or 0.0
    if total is None or listed_a is None:
        return None, None
    remainder = total - listed_a - h_free - b_free
    if abs(remainder) < 1:
        return 0.0, 0.0 if total else None
    return None, None


def _finance_row(rows: list | None, index: int) -> dict:
    if not rows or len(rows) <= index or not isinstance(rows[index], dict):
        return {}
    return rows[index]


def _report_series(rows: list | None, *, limit: int = 5, industry: str = "") -> list[dict]:
    """Recent report periods, newest first. Only periods that carry a revenue.

    The indicator page already returns nine periods and only two were read. The
    rules ask for a three-year plus latest-quarter series, so this keeps what
    the page gives instead of reporting a fetched series as 待收集.
    """
    out = []
    for row in (rows or [])[:limit]:
        if not isinstance(row, dict):
            continue
        revenue = _num(row.get("TOTALOPERATEREVE"))
        if revenue is None:
            continue
        out.append(
            {
                "报告期": _text(row.get("REPORT_DATE_NAME")) or _day(row.get("REPORT_DATE")),
                "营业总收入亿元": round(revenue / 100000000.0, 2),
                "营收同比": _gap(row.get("TOTALOPERATEREVETZ"), 2),
                "归母净利润亿元": _yi(row.get("PARENTNETPROFIT")),
                "归母同比": _gap(row.get("PARENTNETPROFITTZ"), 2),
                "扣非净利润亿元": _yi(row.get("KCFJCXSYJLR")),
                "毛利率": NOT_APPLICABLE
                if _gap(row.get("XSMLL"), 2) == GAP and _is_finance(industry)
                else _gap(row.get("XSMLL"), 2),
                "净利率": _gap(row.get("XSJLL"), 2),
                "加权ROE": _gap(row.get("ROEJQ"), 2),
            }
        )
    return out


def _quote_view(quote: dict | None) -> dict:
    """The price cells. A failed quote keeps every cell 未核."""
    quote = quote or {}
    if not quote:
        return {"状态": GAP}
    return {
        "状态": "已核",
        "行情日期": quote.get("行情日期") or GAP,
        "行情时刻": quote.get("行情时刻") or GAP,
        "是否收盘": quote.get("是否收盘") or GAP,
        "现价": quote.get("收盘", GAP),
        # 行情接口给的是流通市值，不是自由流通市值。自由流通要剔除大股东和
        # 一致行动人锁定部分，公开页没有这个数，所以这一格不拿流通市值顶替。
        "流通市值亿": quote.get("流通市值亿", GAP),
        "总市值亿": quote.get("总市值亿", GAP),
        "换手率": quote.get("换手率", GAP),
        "量比": quote.get("量比", GAP),
    }


def _balance_view(rows: list | None, *, industry: str = "") -> dict:
    """Latest balance-sheet items plus the interest-bearing debt total.

    The rules name money in the bank, receivables, inventory and goodwill, and
    an interest-bearing debt figure. All of them are separate balance-sheet
    rows; none of them needed a new source, only a fetch that was never wired.

    A null row on a balance sheet means the statement has no such line, which is
    a zero balance — Moutai carries no goodwill and no borrowings. That is not
    the same as a page that failed to load, so the two are reported apart.
    """
    if rows is None:
        return {"状态": GAP}
    if not rows:
        return {"状态": "无"}
    row = rows[0] if isinstance(rows[0], dict) else {}
    report = _finance_report(industry)
    if report == "RPT_F10_FINANCE_BBALANCE":
        # 银行报表没有应收和存货。CURRENCY 是记账币种（值就是 CNY），不是
        # 货币资金；银行对得上的现金科目是存放央行款项 CASH_DEPOSIT_PBC。
        return {
            "状态": "已核",
            "报告期": _day(row.get("REPORT_DATE")) or GAP,
            "货币资金亿元": _yi(row.get("CASH_DEPOSIT_PBC")),
            "货币资金口径": "存放中央银行款项",
            "应收账款亿元": NOT_APPLICABLE,
            "存货亿元": NOT_APPLICABLE,
            "商誉亿元": _yi(row.get("GOODWILL")),
            "有息负债亿元": NOT_APPLICABLE,
            "有息负债未列示": True,
            "短期借款亿": NOT_APPLICABLE,
            "长期借款亿": NOT_APPLICABLE,
            "应付债券亿": NOT_APPLICABLE,
            "一年内到期亿": NOT_APPLICABLE,
            "金融科目": {
                "贷款及垫款亿元": _yi(row.get("LOAN_ADVANCE")),
                "吸收存款亿元": _yi(row.get("ACCEPT_DEPOSIT")),
                "应付债券亿元": _yi(row.get("BOND_PAYABLE")),
            },
        }
    if report in ("RPT_F10_FINANCE_IBALANCE", "RPT_F10_FINANCE_SBALANCE"):
        # 保险和券商的报表有货币资金和应收，但资产负债表里没有存货科目，
        # 借款也不按「短期/长期借款」拆分，只有长期借款一行。券商把应收
        # 存在 RECEIVABLES，保险存在 ACCOUNTS_RECE，两个名字都要认。
        receivable = row.get("RECEIVABLES")
        if receivable is None:
            receivable = row.get("ACCOUNTS_RECE")
        # 金融股的有息负债不能只取长期借款：券商和保险的大头在应付债券，
        # 只算长借款会把中信证券 2114 亿债券漏掉，印出 0.07 亿这种数。
        loan = _num(row.get("LONG_LOAN"))
        bond = _num(row.get("BOND_PAYABLE"))
        given = [v for v in (loan, bond) if v is not None]
        return {
            "状态": "已核",
            "报告期": _day(row.get("REPORT_DATE")) or GAP,
            "货币资金亿元": _yi(row.get("MONETARYFUNDS")),
            "应收账款亿元": _yi(receivable),
            "存货亿元": NOT_APPLICABLE,
            "商誉亿元": _yi(row.get("GOODWILL")),
            "有息负债亿元": round(sum(given) / 100000000.0, 2),
            "有息负债未列示": not given,
            "长期借款亿": _yi(row.get("LONG_LOAN")),
            "应付债券亿": _yi(row.get("BOND_PAYABLE")),
            "金融股本报表": True,
        }
    parts = {
        "短期借款亿": row.get("SHORT_LOAN"),
        "长期借款亿": row.get("LONG_LOAN"),
        "应付债券亿": row.get("BOND_PAYABLE"),
        "一年内到期亿": row.get("NONCURRENT_LIAB_1YEAR"),
    }
    given = {k: _num(v) for k, v in parts.items() if _num(v) is not None}
    return {
        "状态": "已核",
        "报告期": _day(row.get("REPORT_DATE")) or GAP,
        "货币资金亿元": _yi(row.get("MONETARYFUNDS")),
        "应收账款亿元": _yi(row.get("ACCOUNTS_RECE")),
        "存货亿元": _yi(row.get("INVENTORY")),
        "商誉亿元": _yi(row.get("GOODWILL")),
        # 报表没有有息负债行就是零余额；写未核会让人反复重试一个不存在的行。
        "有息负债亿元": round(sum(given.values()) / 100000000.0, 2),
        "有息负债未列示": not given,
        **{k: _yi(v) for k, v in parts.items()},
    }


def _dividend_view(rows: list | None) -> dict:
    """Dividend plans, newest first. A plan with no per-share figure keeps its text.

    A pre-disclosed plan says "每10股派发现金红利应不少于3.8元" and carries no
    per-share number yet. Writing 0 there would read as "pays nothing", which is
    the opposite of what the plan says, so the raw plan text is kept instead.
    """
    if rows is None:
        return {"状态": GAP}
    plans = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        # PRETAX_BONUS_RMB 是「每 10 股派息（元）」，不是每股。曾经按每股再乘
        # 10，把茅台 10 派 280.24 印成 10 派 2802.42，整整放大十倍。方案原文
        # 同时留下，两者对不上时以原文为准。
        per_ten = _num(row.get("PRETAX_BONUS_RMB"))
        if per_ten is None:
            per_ten = _num(row.get("BONUS_IT_RATIO"))
        profile = _text(row.get("IMPL_PLAN_PROFILE"))
        plans.append(
            {
                "报告期": _day(row.get("REPORT_DATE")) or GAP,
                "除权除息日": _day(row.get("EX_DIVIDEND_DATE")) or GAP,
                "进度": _text(row.get("ASSIGN_PROGRESS")) or GAP,
                "每10股派元": round(per_ten, 4) if per_ten is not None else GAP,
                "方案原文": profile or "",
            }
        )
    return {"状态": "已核", "期数": len(plans), "明细": plans[:5]}


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
    restricted, restricted_ratio = _restricted(capital)
    regime = board_limit(code, "" if name == GAP else name)
    former = _text(basics.get("cym"))
    industry = _text(basics.get("sshy"))
    balance = _balance_view(bundle.get("balance"), industry=industry)
    dividends = _dividend_view(bundle.get("dividends"))
    # 扣非加权ROE 只在半年报和年报披露，季报页面给空值是「本期不披露」，
    # 不是「取数失败」。两者都写未核会把一个正常的披露节奏报成故障。
    deduct_roe = finance.get("ROEKCJQ")
    if deduct_roe is None:
        report_name = _text(finance.get("REPORT_DATE_NAME"))
        deduct_roe = "本期不披露" if "季报" in report_name else GAP
    else:
        deduct_roe = _gap(deduct_roe, 2)
    # 金融报表没有毛利润和流动资产/流动负债，毛利率与流动比率这两格在
    # 银行、保险、券商身上是不适用，不是缺数。写未核会让人一直重试。
    gross_margin = _gap(finance.get("XSMLL"), 2)
    current_ratio = _gap(finance.get("LD"), 2)
    if _is_finance(industry):
        gross_margin = NOT_APPLICABLE if gross_margin == GAP else gross_margin
        current_ratio = NOT_APPLICABLE if current_ratio == GAP else current_ratio
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
            "毛利率": gross_margin,
            "净利率": _gap(finance.get("XSJLL"), 2),
            "加权ROE": _gap(finance.get("ROEJQ"), 2),
            "扣非加权ROE": deduct_roe,
            "基本每股收益": _gap(finance.get("EPSJB"), 4),
            "每股净资产": _gap(finance.get("BPS"), 2),
            "每股经营现金流": _gap(finance.get("MGJYXJJE"), 4),
            "经营现金流占营收": _gap(finance.get("JYXJLYYSR"), 4),
            "资产负债率": _gap(finance.get("ZCFZL"), 2),
            "流动比率": current_ratio,
            "业绩": earnings,
            "扣非拐点": deducted_turn(
                finance.get("KCFJCXSYJLR"),
                prior_finance.get("KCFJCXSYJLR"),
            ),
            "报表序列": _report_series(bundle.get("indicators"), industry=industry),
            "资产负债分项": balance,
            "分红": dividends,
        },
        "主力": {
            # 接口给了行但名称为空，是「无实际控制人」（股权分散的银行、保险
            # 常见），不是取数失败。写未核会让人反复去抓一个本来就不存在的名字。
            "实际控制人": _text(controller.get("HOLDER_NAME")) or (
                "无实际控制人" if controllers else GAP
            ),
            # sjkzr 这一页的 HOLD_RATIO 长期为 null，是接口没给，不是取数失败。
            # 写未核会让人一遍遍重试一个永远不来的字段。
            "实控人披露持股比例": _gap(controller.get("HOLD_RATIO"), 2)
            if _num(controller.get("HOLD_RATIO")) is not None
            else "接口未披露",
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
            "限售股": _gap(restricted),
            "限售占总股本": _gap(restricted_ratio, 2),
            "行情": _quote_view(bundle.get("quote")),
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
    raw = _get_bytes(url).decode("utf-8", "replace").lstrip("\ufeff")
    if raw.lstrip().startswith("<"):
        return None
    return json.loads(raw)


def _get_bytes(url: str) -> bytes:
    """One public page, decompressed if the host sent it packed.

    Eastmoney sometimes answers a gzip body without honouring our headers. The
    old code decoded those bytes straight as text, got mojibake, and the whole
    identity block became 未核 from one packed response — no exception, no
    retry, silently blank. Detect the magic bytes instead of trusting the
    header, and retry once: a single flaky page should not erase a block.
    """
    import gzip
    import zlib

    def once() -> bytes:
        with open_url(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://emweb.securities.eastmoney.com/",
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=20,
        ) as resp:
            return resp.read()

    last: Exception | None = None
    for _ in range(2):
        try:
            body = once()
            break
        except Exception as exc:  # noqa: BLE001 — 一次抖动不该让整块变未核
            last = exc
    else:
        raise last if last else RuntimeError("fetch failed")
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    elif body[:2] == b"\x78\x9c" or body[:2] == b"\x78\xda":
        body = zlib.decompress(body)
    return body


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
        "balance": _balance(code, suffix, industry=_text(
            ((survey or {}).get("jbzl") or {}).get("sshy")
            if isinstance(survey, dict) else ""
        )),
        "dividends": _dividends(code, suffix),
        "quote": _quote(code),
    }


def _datacenter(report: str, code: str, suffix: str, columns: str, *, size: int = 12):
    """One datacenter report, newest first. A dead page is None, not an empty list."""
    url = (
        "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        f"?reportName={report}&columns={columns}"
        f"&filter=(SECUCODE%3D%22{code}.{suffix}%22)"
        f"&pageNumber=1&pageSize={size}&sortColumns=REPORT_DATE&sortTypes=-1"
    )
    payload = _fetch_page(url)
    if not isinstance(payload, dict):
        return None
    return ((payload.get("result") or {}).get("data")) or []


def _balance(code: str, suffix: str, *, industry: str = ""):
    """Balance-sheet items the rules name but the indicator page does not carry.

    Money in the bank, receivables, inventory and goodwill are separate rows on
    the balance sheet. They were 待收集 only because nothing fetched them, not
    because they were unavailable.

    Banks, insurers and brokers each file their own statement shape. Reading a
    bank with the industrial column names returns an empty table, which used to
    look like a dead page rather than a wrong question.
    """
    report = _finance_report(industry)
    if report == "RPT_F10_FINANCE_BBALANCE":
        return _datacenter(
            report,
            code,
            suffix,
            "SECUCODE,REPORT_DATE,CASH_DEPOSIT_PBC,GOODWILL,TOTAL_ASSETS,"
            "TOTAL_LIABILITIES,LOAN_ADVANCE,ACCEPT_DEPOSIT,BOND_PAYABLE",
            size=8,
        )
    if report == "RPT_F10_FINANCE_IBALANCE":
        return _datacenter(
            report,
            code,
            suffix,
            "SECUCODE,REPORT_DATE,MONETARYFUNDS,ACCOUNTS_RECE,GOODWILL,"
            "TOTAL_ASSETS,TOTAL_LIABILITIES,LONG_LOAN,BOND_PAYABLE",
            size=8,
        )
    if report == "RPT_F10_FINANCE_SBALANCE":
        # 券商报表的应收叫 RECEIVABLES，不是 ACCOUNTS_RECE。列名写错时整张表
        # 返回空，和「页面挂了」长得一模一样，所以这一列要单列。
        return _datacenter(
            report,
            code,
            suffix,
            "SECUCODE,REPORT_DATE,MONETARYFUNDS,RECEIVABLES,GOODWILL,"
            "TOTAL_ASSETS,TOTAL_LIABILITIES,LONG_LOAN,BOND_PAYABLE",
            size=8,
        )
    return _datacenter(
        "RPT_F10_FINANCE_GBALANCE",
        code,
        suffix,
        "SECUCODE,REPORT_DATE,MONETARYFUNDS,ACCOUNTS_RECE,INVENTORY,GOODWILL,"
        "TOTAL_ASSETS,TOTAL_LIABILITIES,SHORT_LOAN,LONG_LOAN,BOND_PAYABLE,"
        "NONCURRENT_LIAB_1YEAR",
        size=8,
    )


def _dividends(code: str, suffix: str):
    return _datacenter(
        "RPT_SHAREBONUS_DET",
        code,
        suffix,
        "SECUCODE,REPORT_DATE,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB,"
        "BONUS_IT_RATIO,ASSIGN_PROGRESS,IMPL_PLAN_PROFILE,NOTICE_DATE",
        size=8,
    )


def _quote(code: str) -> dict:
    """One live quote, only for the two cells that need a price.

    Free float market cap cannot be a report-period figure: it moves with the
    close. The rules require it to carry its quote date, and the Tencent payload
    already prints float cap in 亿 and the timestamp, so this reads those two
    fields and nothing else. A failed fetch stays 未核 rather than guessing.
    """
    symbol = f"{market_suffix(code).lower()}{code}"
    try:
        raw = _get_bytes(f"https://qt.gtimg.cn/q={symbol}").decode("gbk", "replace")
    except Exception:  # noqa: BLE001 — 一行行情取不到不该拖垮整张画像
        return {}
    parts = raw.split('"', 1)[-1].split("~")
    if len(parts) < 50:
        return {}

    def positive(index: int):
        value = _num(parts[index]) if len(parts) > index else None
        return value if value is not None and value > 0 else None

    stamp = _text(parts[30]) if len(parts) > 30 else ""
    # 腾讯的时间戳是 yyyyMMddHH，没有分隔符。旧写法按 yyyy-MM-dd 切，得到的
    # 是一串不像日期的数字；盘中的小时也要留下，否则 11 点的价会被当成收盘价。
    day = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) >= 8 else GAP
    hour = stamp[8:10] if len(stamp) >= 10 else ""
    return {
        "收盘": positive(3),
        "行情日期": day,
        "行情时刻": f"{day} {hour}:00" if hour else day,
        # 15 点前是盘中读数，不是收盘价：自由流通市值能算，但不能当收盘定格。
        "是否收盘": "是" if hour and hour >= "15" else "否（盘中）",
        "流通市值亿": positive(44),
        "总市值亿": positive(45),
        "换手率": positive(38),
        "量比": positive(49),
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
    """Six blocks. A cell with no source stays 待收集. A conclusion stays 未填."""
    identity = sheet["身份"]
    inst = sheet["机构"]
    force = sheet["主力"]
    hot = sheet["游资"]
    count = force["股东户数"]
    org = force["机构合计"]
    lines = [
        f"个股画像 {sheet['代码']} {sheet['名称']}",
        f"截止: {sheet['截止']}",
        "六块按更新时钟分开。不进 W1–W8，不下单。缺资料写待收集，缺了资料的结论写未填。",
        "一、身份档案",
        _line("公司全称", identity["公司全称"]),
        _line("简称", sheet["名称"]),
        _line("上市板块", hot["板块"]),
        _line("涨跌幅上限", hot["涨跌幅上限"]),
        _line("风险警示", hot["风险警示"]),
        _line("曾用名", identity["曾用名"]),
        _line("行业", identity["行业"]),
        _line("证监会行业", identity["证监会行业"]),
        _line("地区", identity["地区"]),
        _line("上市日", identity["上市日"]),
        _line("证券类别", identity["证券类别"]),
        "一句话定性: 待收集",
        "核心子公司与参股: 待收集",
        "可比公司: 待收集",
        "二、生意与报表",
        _line("最新报告期", f"{inst['报告期']} {inst['报告名称']}".strip()),
        *_format_series(inst["报表序列"]),
        _line("最新营业总收入亿元", inst["营业总收入亿元"]),
        _line("最新营收同比", inst["营收同比"]),
        _line("最新归母净利润亿元", inst["归母净利润亿元"]),
        _line("最新归母同比", inst["归母同比"]),
        _line("最新扣非净利润亿元", inst["扣非净利润亿元"]),
        _line("最新扣非同比", inst["扣非同比"]),
        _line("最新毛利率", inst["毛利率"]),
        _line("最新净利率", inst["净利率"]),
        _line("最新加权ROE", inst["加权ROE"]),
        _line("最新扣非加权ROE", inst["扣非加权ROE"]),
        _line("业绩三格", inst["业绩"]),
        _line("扣非拐点", inst["扣非拐点"]),
        "收入结构: 待收集",
        _line("每股经营现金流", inst["每股经营现金流"]),
        _line("经营现金流占营收", inst["经营现金流占营收"]),
        "利润与现金流是否匹配: 未填",
        _line("资产负债率", inst["资产负债率"]),
        _line("流动比率", inst["流动比率"]),
        *_format_balance(inst["资产负债分项"]),
        "业绩预告与说明会: 待收集",
        *_format_dividends(inst["分红"]),
        "产品产能产量销量与定价模式: 待收集",
        "上下游: 待收集",
        "核心壁垒: 待收集",
        "成本与盈亏平衡: 待收集",
        "生意属性: 未填",
        "业绩驱动因子: 未填",
        "三、催化库",
        "行业供需与价格指标: 待收集",
        "正向催化: 待收集",
        "负向催化: 待收集",
        "龙头与海外对标动态: 待收集",
        "监管与审批: 待收集",
        "跟着商品还是跟着消息: 未填",
        "四、筹码与交易者",
        _line("实际控制人", force["实际控制人"]),
        _line("实控人披露持股比例", force["实控人披露持股比例"]),
        _format_holders(force["前十大"]),
        _line("总股本", hot["总股本"]),
        _line("流通A股", hot["流通A股"]),
        _line("限售股", hot["限售股"]),
        _line("限售占总股本", hot["限售占总股本"]),
        _format_unlock("下一笔解禁", force["解禁"]),
        *_format_quote(hot["行情"]),
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
        "筹码峰与获利盘: 待收集",
        "北向持仓变化: 待收集",
        "公募私募持仓变化: 待收集",
        "融资余额变化: 待收集",
        "龙虎榜席位: 待收集",
        "大宗交易: 待收集",
        "换手基线: 待收集",
        "股性样本: 待收集",
        "五、价格结构",
        "日线笔中枢背驰比较段: 待收集",
        "30分钟结构: 待收集",
        "5分钟结构: 待收集",
        "关键价位: 待收集",
        "背驰历史样本: 待收集",
        "均线压制与支撑: 待收集",
        "量价规律: 待收集",
        "盯盘阈值与买卖观察区: 未填",
        "六、情景与失效",
        "乐观情景: 未填",
        "中性情景: 未填",
        "悲观情景: 未填",
        "核心风险: 待收集",
        "仓位: 沿用硬门和操作令",
        "失效信号: 待收集",
        "取数清单",
        *[_format_query(row) for row in fetch_queries(sheet)],
    ]
    return "\n".join(lines)


def fetch_queries(sheet: dict) -> list[dict]:
    """Turn filled cells into the data and news this fetch must request.

    A blank cell adds nothing. The industry name is not a query by itself.
    """
    code = sheet["代码"]
    rows = [
        {"来源": "代码", "查询": code, "资料": "行情", "刷新": "按日"},
        {"来源": "代码", "查询": code, "资料": "定期报告与业绩预告", "刷新": "按期"},
        {"来源": "代码", "查询": code, "资料": "公司公告", "刷新": "按消息"},
        {"来源": "前十大", "查询": code, "资料": "前十大与股东户数", "刷新": "按期"},
    ]
    controller = sheet["主力"]["实际控制人"]
    if controller not in (GAP, "", None, "无实际控制人"):
        rows.append({"来源": "实控人", "查询": controller, "资料": "控制权与股东公告", "刷新": "按消息"})
    seen_connect = False
    for holder in sheet["主力"]["前十大"].get("名单") or []:
        if seen_connect or "香港中央结算" not in str(holder.get("名称") or ""):
            continue
        seen_connect = True
        rows.append({"来源": "前十大", "查询": "香港中央结算", "资料": "北向持仓", "刷新": "按日"})
    unlock = sheet["主力"]["解禁"]
    if unlock.get("状态") == "有" and unlock.get("日期") not in (GAP, "", None):
        rows.append({"来源": "解禁", "查询": unlock["日期"], "资料": "解禁规模", "刷新": "按期"})
    return rows


def _format_quote(block: dict) -> list[str]:
    """Float cap, and only the float cap we can actually name.

    The cell is 自由流通市值. The quote gives 流通市值. Writing one under the
    other's label is how a reader ends up sizing a position against a number
    that excludes nothing. 自由流通 stays 待收集 until a source for the
    deducted base is wired; 流通市值 is printed separately so the gap is visible
    rather than papered over.
    """
    if block.get("状态") != "已核":
        return [
            "自由流通市值: 未核",
            "流通市值: 未核",
        ]

    def gap(value, unit: str) -> str:
        return "未核" if value == GAP else f"{value}{unit}"

    return [
        "自由流通市值: 待收集(公开页只给流通市值，不含大股东锁定剔除)",
        f"流通市值: {gap(block['流通市值亿'], '亿')}"
        f" (行情 {block['行情时刻']}，收盘价{block['是否收盘']})",
        f"总市值: {gap(block['总市值亿'], '亿')}"
        f" 现价 {gap(block['现价'], '')}"
        f" 换手率 {gap(block['换手率'], '%')}"
        f" 量比 {gap(block['量比'], '')}",
    ]


def _format_series(rows: list) -> list[str]:
    """One line per report period. Nothing to show stays 未核, not an empty list."""
    if not rows:
        return ["近3年及最新单季序列: 未核"]

    def pct(value) -> str:
        # 缺数就写未核，不拼出「同比未核%」这种账面残缺的句子。
        return "未核" if value == GAP else f"{value}%"

    def yi(value) -> str:
        return "未核" if value == GAP else f"{value}亿"

    lines = []
    for row in rows:
        lines.append(
            f"报告期 {row['报告期']}: 营收{yi(row['营业总收入亿元'])}"
            f" 同比{pct(row['营收同比'])} 归母{yi(row['归母净利润亿元'])}"
            f" 同比{pct(row['归母同比'])} 扣非{yi(row['扣非净利润亿元'])}"
            f" 毛利率{pct(row['毛利率'])} 净利率{pct(row['净利率'])}"
            f" ROE{pct(row['加权ROE'])}"
        )
    return lines


def _format_balance(block: dict) -> list[str]:
    if block.get("状态") != "已核":
        if block.get("状态") == "无":
            return ["资产负债分项: 无"]
        return ["资产负债分项: 未核"]

    def yi(value) -> str:
        # 报表没有这一行就是零余额，不拼成「商誉未核」这种半截结论。
        if value == NOT_APPLICABLE:
            return NOT_APPLICABLE
        return "0亿" if value == GAP else f"{value}亿"

    debt_detail = " ".join(
        f"{label}{yi(block[key])}"
        for label, key in (
            ("短借", "短期借款亿"),
            ("长借", "长期借款亿"),
            ("债券", "应付债券亿"),
            ("一年内到期", "一年内到期亿"),
        )
        if key in block
    )
    lines = [
        f"资产负债分项({block['报告期']}) 货币资金{yi(block['货币资金亿元'])}"
        f" 应收账款{yi(block['应收账款亿元'])} 存货{yi(block['存货亿元'])}"
        f" 商誉{yi(block['商誉亿元'])} 有息负债{yi(block['有息负债亿元'])}"
        f" ({debt_detail})"
    ]
    if block.get("货币资金口径"):
        # 银行的现金不是「货币资金」，标出口径，避免跟工商企业的现金混读。
        lines.append(f"货币资金口径: {block['货币资金口径']}")
    finance_items = block.get("金融科目") or {}
    if finance_items:
        shown = " ".join(f"{name}{yi(value)}" for name, value in finance_items.items())
        lines.append(f"金融科目: {shown}")
    return lines


def _format_dividends(block: dict) -> list[str]:
    if block.get("状态") != "已核":
        if block.get("状态") == "无":
            return ["分红历史: 无"]
        return ["分红历史: 未核"]
    lines = [f"分红历史: {block['期数']}期在案"]
    for plan in block["明细"]:
        paid = plan["每10股派元"]
        tail = f" 每10股派{paid}元" if paid != GAP else ""
        text = f" 方案原文「{plan['方案原文']}」" if plan["方案原文"] else ""
        lines.append(
            f"分红 {plan['报告期']} {plan['进度']}{tail}"
            f" 除权除息{plan['除权除息日']}{text}"
        )
    return lines


def _format_query(row: dict) -> str:
    return f"查询: {row['来源']} {row['查询']} {row['资料']} {row['刷新']}"


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
        "balance": [{
            "REPORT_DATE": "2026-09-30 00:00:00",
            "MONETARYFUNDS": 10000000000,
            "ACCOUNTS_RECE": 2000000000,
            "INVENTORY": 3000000000,
            "GOODWILL": 500000000,
            "SHORT_LOAN": 1000000000,
            "LONG_LOAN": 2000000000,
            "BOND_PAYABLE": None,
            "NONCURRENT_LIAB_1YEAR": None,
        }],
        "dividends": [
            {
                "REPORT_DATE": "2026-06-30 00:00:00",
                "EX_DIVIDEND_DATE": None,
                "ASSIGN_PROGRESS": "预披露",
                "PRETAX_BONUS_RMB": None,
                "BONUS_IT_RATIO": None,
                "IMPL_PLAN_PROFILE": "每10股派发现金红利应不少于3.8元(含税)",
            },
            {
                "REPORT_DATE": "2026-03-31 00:00:00",
                "EX_DIVIDEND_DATE": "2026-08-21 00:00:00",
                "ASSIGN_PROGRESS": "实施分配",
                # 真实接口把「每 10 股派息」放在 PRETAX_BONUS_RMB。样例也照这个放，
                # 否则错误单位永远测不出来。
                "PRETAX_BONUS_RMB": 4.2,
                "BONUS_IT_RATIO": None,
                "IMPL_PLAN_PROFILE": "10派4.20元(含税)",
            },
        ],
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

    # 报表序列：指标页本来就给了多期，不能标成待收集。
    series = sheet["机构"]["报表序列"]
    check("series keeps the period that carries revenue", len(series) == 1)
    check("series keeps the newest period first", series[0]["报告期"] == "2026三季报")
    check("a period without revenue is not a series row",
          all(row["报告期"] != "" for row in series))
    check("series says 未核 when the page is empty", portrait({"code": "600000"}, "2026-11-25")["机构"]["报表序列"] == [])

    # 扣非ROE 季报不披露，是披露节奏，不是取数失败。
    quarterly = portrait(
        {"code": "600000", "indicators": [{"REPORT_DATE_NAME": "2026三季报"}]},
        "2026-11-25",
    )["机构"]["扣非加权ROE"]
    check("quarterly deducted roe says not disclosed", quarterly == "本期不披露")
    annual = portrait(
        {"code": "600000", "indicators": [{"REPORT_DATE_NAME": "2025年报", "ROEKCJQ": 12.5}]},
        "2026-11-25",
    )
    check("annual deducted roe is read", annual["机构"]["扣非加权ROE"] == 12.5)

    # 资产负债分项：接口没接之前是待收集，现在必须真取到。
    bal = sheet["机构"]["资产负债分项"]
    check("balance block is wired", bal["状态"] == "已核")
    check("money in bank in yi", bal["货币资金亿元"] == 100.0)
    check("goodwill in yi", bal["商誉亿元"] == 5.0)
    empty_bal = portrait({"code": "600000"}, "2026-11-25")["机构"]["资产负债分项"]
    check("missing balance page stays unchecked", empty_bal["状态"] == "未核")
    no_debt = portrait(
        {"code": "600000", "balance": [{"REPORT_DATE": "2026-09-30 00:00:00", "GOODWILL": None,
                                        "SHORT_LOAN": None, "LONG_LOAN": None,
                                        "BOND_PAYABLE": None, "NONCURRENT_LIAB_1YEAR": None}]},
        "2026-11-25",
    )["机构"]["资产负债分项"]
    check("a missing balance row is a zero balance", no_debt["有息负债亿元"] == 0)
    check("zero balance is flagged as unlisted", no_debt["有息负债未列示"] is True)

    # 分红：方案原文要留，预披露没有每股数字不能写成 0。
    divs = sheet["机构"]["分红"]
    check("dividends wired", divs["状态"] == "已核")
    check("pre-disclosed plan keeps its text", "不少于3.8元" in divs["明细"][0]["方案原文"])
    check("pre-disclosed plan has no per-share figure", divs["明细"][0]["每10股派元"] == GAP)
    check("implemented plan reads per ten shares", divs["明细"][1]["每10股派元"] == 4.2)
    check("missing dividend page stays unchecked",
          portrait({"code": "600000"}, "2026-11-25")["机构"]["分红"]["状态"] == "未核")

    # 限售股：H 股公司留空时，用同一页的数字算出来，不猜。
    h_share = portrait(
        {"code": "601899", "capital": [{"TOTAL_SHARES": 1000, "LISTED_A_SHARES": 700,
                                        "H_FREE_SHARE": 300, "LIMITED_SHARES": None}]},
        "2026-11-25",
    )
    check("restricted shares resolve to zero on an H-share count", h_share["游资"]["限售股"] == 0)
    unclear = portrait(
        {"code": "601899", "capital": [{"TOTAL_SHARES": 1000, "LISTED_A_SHARES": 700,
                                        "LIMITED_SHARES": None}]},
        "2026-11-25",
    )
    check("an unresolved remainder stays unchecked", unclear["游资"]["限售股"] == GAP)

    # 实控人比例这一页长期为 null，要写「接口未披露」而不是无限重试。
    check("controller ratio is read when the page gives it",
          sheet["主力"]["实控人披露持股比例"] == 3.46)
    null_ratio = portrait(
        {"code": "600000", "controller": [{"HOLDER_NAME": "示例", "HOLD_RATIO": None}]},
        "2026-11-25",
    )
    check("controller ratio says the interface omits it",
          null_ratio["主力"]["实控人披露持股比例"] == "接口未披露")

    # 金融股：报表没有毛利率和流动比率，现金口径不同，常常没有实控人。
    bank = portrait(
        {"code": "600036", "survey": {"jbzl": {"sshy": "银行"}},
         "indicators": [{"REPORT_DATE_NAME": "2026三季报", "TOTALOPERATEREVE": 1e10}],
         "controller": [{"HOLDER_NAME": None, "HOLD_RATIO": None}],
         "balance": [{"REPORT_DATE": "2026-09-30 00:00:00", "CASH_DEPOSIT_PBC": 5e11,
                      "GOODWILL": 1e10, "LOAN_ADVANCE": 7e12, "ACCEPT_DEPOSIT": 1e13,
                      "BOND_PAYABLE": 1e11}]},
        "2026-11-25",
    )
    check("a bank has no gross margin", bank["机构"]["毛利率"] == NOT_APPLICABLE)
    check("a bank has no current ratio", bank["机构"]["流动比率"] == NOT_APPLICABLE)
    check("a bank has no controller", bank["主力"]["实际控制人"] == "无实际控制人")
    check("bank cash is the central bank deposit", bank["机构"]["资产负债分项"]["货币资金亿元"] == 5000.0)
    check("bank cash is labelled", bank["机构"]["资产负债分项"]["货币资金口径"] == "存放中央银行款项")
    check("a bank has no receivables", bank["机构"]["资产负债分项"]["应收账款亿元"] == NOT_APPLICABLE)

    broker = portrait(
        {"code": "600030", "survey": {"jbzl": {"sshy": "券商信托"}},
         "balance": [{"REPORT_DATE": "2026-09-30 00:00:00", "MONETARYFUNDS": 1e11,
                      "RECEIVABLES": 2e10, "GOODWILL": 1e9, "LONG_LOAN": 7e6,
                      "BOND_PAYABLE": 2.114e11}]},
        "2026-11-25",
    )
    check("broker receivables are read", broker["机构"]["资产负债分项"]["应收账款亿元"] == 200.0)
    check("broker debt includes bonds", broker["机构"]["资产负债分项"]["有息负债亿元"] == 2114.07)

    check("no controller is not a query word",
          all("无实际控制人" not in str(row["查询"]) for row in fetch_queries(bank)))

    none_left = portrait({"code": "600000", "unlocks": []}, "2026-11-25")
    check("opened page with no future batch", none_left["游资"]["解禁"]["状态"] == "无")
    starred = board_limit("300001", "*ST示例")
    check("st cap is five", starred["涨跌幅上限"] == 5 and starred["风险警示"] == "是")
    star = board_limit("688981", "中芯国际")
    check("star board twenty", star["板块"] == "科创板" and star["涨跌幅上限"] == 20)
    text = format_portrait(sheet)
    for title in ("一、身份档案", "二、生意与报表", "三、催化库", "四、筹码与交易者", "五、价格结构", "六、情景与失效"):
        check(title, title in text)
    check("empty cells stay pending", "待收集" in text and "未填" in text)
    queries = fetch_queries(sheet)
    check("code always asks for quotes and filings", any(row["资料"] == "行情" and row["查询"] == "000725" for row in queries))
    check("named northbound holder becomes a query", any(row["查询"] == "香港中央结算" and row["资料"] == "北向持仓" for row in queries))
    check("industry name is not a query", all(row["查询"] != sheet["身份"]["行业"] for row in queries))
    check("printed list follows the cells", "取数清单" in text and "香港中央结算" in text)
    empty_queries = fetch_queries(empty)
    check("blank holder adds no northbound query", all(row["资料"] != "北向持仓" for row in empty_queries))
    check("blank portrait still asks for its own filings", any(row["资料"] == "公司公告" for row in empty_queries))
    check("position rule is not a new number", "仓位: 沿用硬门和操作令" in text)
    for word in ("开仓", "加仓", "买入", "Buy"):
        check(f"no order word {word}", word not in text)
    if failed:
        print(failed, "failed")
        return 1
    print("ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="印出一只股票的六块画像。不下单。")
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
