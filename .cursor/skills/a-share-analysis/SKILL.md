---
name: a-share-analysis
description: "A股分析按模式取数，规则分层读取。项目在仓库根目录，不在本 skill 目录。先读 desk.md，再按「这一轮读什么」打开 rules/01-data.md 到 rules/06-output.md，未点名的层不读进对话。计算用 python -m astock.close_inputs、info_diff、intraday_brief、intraday_screen、sector_drive、overseas_feed、us_sectors。大盘预判和交易日 10:00、12:50、14:00 的盘中分析都跑 info_diff、intraday_brief、intraday_screen。成分日线和前十大由脚本按规则算完，站上均线的名字全部印出。权重、四条路径、行为分和硬门仍以对应层的同名节为准。Use when the user asks for A股分析、盘前/盘中/收盘/实时分析、行为分、板块看涨、大盘四态、对冲、托住、国家队、汇金、缠论、笔、中枢、背驰、买卖点、资料面、新华社、发改委、央视财经、中国财富、明天预测、预测对照、今日关注、公司公告、巨潮、中小票、持仓结构、前十大股东、国有资金。"
---

# A股分析

本文件只负责把对话送进仓库根目录。项目不在 `.cursor/skills/`。

1. 先读 `desk.md`，按「这一轮读什么」做完。表里点名的节要打开，没点名的层不读进对话。
2. 规则只在 `rules/`。改判断改对应层，不要把六层写回本文件。
3. 任何模式先读 `rules/02-rules.md` 的「硬门」。没读完不写结论。
4. 先跑 `python -m astock route --at <北京时间> --ask <原话>`。取数窗口才采集。分析窗口只读已经印出的快照，缺了写未跑或未挂，不补抓，也不问要不要取数。模块只出数，不改权重，不下单。
5. 台账是 `runtime/info-ledger.md`，股东缓存是 `runtime/cache/holders.json`。记录全文不读进对话。
6. 权重数字仍以 Canvas 为准。终分和初分才读 `desk.md` 里那三块 canvas。

| 会话里要跑的 | 命令 |
| --- | --- |
| 收盘输入 | `python -m astock.close_inputs` |
| 资料面增量 | `python -m astock.info_diff` |
| 盘中路径 | `python -m astock.intraday_brief` |
| 均线与前十大 | `python -m astock.intraday_screen` |
| 发力板块、发力个股 | `python -m astock.sector_drive` |
| 外围市场资讯 | `python -m astock.overseas_feed` |
| 美股行业 | `python -m astock.us_sectors` |
| 这一轮哪个窗口 | `python -m astock route --at <北京时间> --ask <原话>` |
| 热层和归档 | `python -m astock lake` |
| 事实一句校验 | `python -m astock sentence` |
