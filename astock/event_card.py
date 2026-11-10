"""One card for a timed information row. Three destinations, no score and no order."""

from __future__ import annotations

CITATIONS = ("国家统计局", "统计局", "中国人民银行", "央行", "财政部", "新华社")
OFFICIAL_SOURCES = ("新华社", "国家发展改革委", "发改委", "央视财经频道", "联播", "中国财富网")
WIRE_SOURCES = ("中证网", "中国证券报", "财联社", "财联社电报")
CROSS_ASSET = ("原油", "布伦特", "美元指数", "沪铜")
QUOTE_WORDS = ("现涨", "现报", "开盘上涨", "开盘报")
US_CASH = ("道琼斯", "道指", "纳斯达克", "纳指", "标普")
OTHER_MARKETS = ("富时", "伦敦", "欧洲", "日经", "恒生", "韩国")


def event_destination(source: str, text: str, kind: str = "", official_matched: bool = False) -> str:
    """Return 权重, 观察, or 留档.

    A wire citation enters 权重 only after the official page matches.
    Sector ETFs are 观察. Cash index closes are 权重 through the W3 scale.
    Oil, the dollar and copper stay 留档 until a cross-asset scale exists.
    """
    if kind in {"转载", "评论"}:
        return "留档"
    if kind == "us_sector":
        return "观察"
    if kind == "us_cash":
        return "权重"
    body = text or ""
    if any(word in body for word in CROSS_ASSET) or any(word in body for word in OTHER_MARKETS):
        return "留档"
    if any(word in body for word in US_CASH) and "收盘" in body:
        return "权重"
    if any(word in body for word in QUOTE_WORDS) and "收盘" not in body:
        return "留档"
    cited = any(name in body for name in CITATIONS)
    if cited and source in WIRE_SOURCES:
        return "权重" if official_matched else "留档"
    if source in OFFICIAL_SOURCES:
        return "权重"
    return "留档"
