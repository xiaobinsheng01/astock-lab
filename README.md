# astock-lab

A 股行情分析交易台。尺子、算盘、当日底稿、会话钟分开，仓库根目录就能看完，不把项目塞进 `.cursor/skills/`。

权重数字仍以 Canvas 为准。本仓库不复制一份会漂的分数表。计算器只印数，不下单，不接证券账户。

## 四样东西

| 位置 | 是什么 | 谁改 |
| --- | --- | --- |
| `rules/` | 尺子。资料、规则、账户、判定、执行、产出、操作令、个股画像八层 | 改判断只改对应层 |
| `astock/` | 算盘。行情、涨停、股东、新闻列表。标准库，无第三方依赖 | 改取数和分类 |
| `runtime/` | 当日底稿。`info-ledger.md`、`cache/holders.json` | 跑起来才写，不进 git |
| `desk.md` | 会话钟。这一轮读哪一层、跑哪条命令、写成五行还是六行 | 改时点，不改权重 |

下层没齐，上层停写。任何模式先读 `rules/02-rules.md` 的「硬门」。

## 八层

| 层 | 文件 | 内容 |
| --- | --- | --- |
| 1 资料 | `rules/01-data.md` | 渠道、时点、资料面增量、外围 |
| 2 规则 | `rules/02-rules.md` | 大盘四态、W6、板块状态、缠论、硬门 |
| 3 账户 | `rules/03-account.md` | 行为分状态、持仓、前十大两格 |
| 4 判定 | `rules/04-judgment.md` | 路径、对冲、托住、发力、今日关注 |
| 5 执行 | `rules/05-execution.md` | 终分、初分、盘中、定时 |
| 6 产出 | `rules/06-output.md` | 收盘五行或盘中六行 |
| 7 操作令 | `rules/07-operation.md` | 总上限、外盘档、退潮、板块和操作句。不改 W1–W8 |
| 8 个股画像 | `rules/08-portrait.md` | 身份、生意与报表、催化库、筹码、价格结构、情景。不改硬门 |

## 命令

在仓库根目录执行。

```bash
python -m astock
python -m astock.close_inputs
python -m astock.close_inputs --fast
python -m astock.info_diff
python -m astock.intraday_brief --low 3590.80 --high 3686.17
python -m astock.intraday_screen
python -m astock.sector_drive
python -m astock.overseas_feed
python -m astock.news_desk --day 2026-11-24 --no-write
python -m astock.us_sectors
python -m astock.csi300
python -m astock.dual50
python -m astock.yaogu --monitor
python -m astock.route --at "2026-11-10 10:00" --ask "盘中"
python -m astock.lake hot --today 2026-11-10
python -m astock.fundamental 000725 --as-of 2026-11-25
```

短名与上面的模块一一对应：`close`、`news`、`desk`、`brief`、`screen`、`drive`、`overseas`、`us`、`yaogu`、`route`、`lake`、`sentence`、`a50`、`cctv`、`cfbond`、`cninfo`、`cash`、`csi300`、`dual50`、`portrait`。例如 `python -m astock close --fast`。`desk` 是市场资讯，不进 W1–W8。`portrait` 印一只股票的六块画像。没有来源的格子写待收集。

取数和分析分成两个窗口。`route` 打印这一轮读什么、跑什么。分析也跑 `跑` 里的命令。资料湖在 `runtime/lake/`，不进 git。

离线核对：

```bash
python -m unittest discover -s tests
python -m astock.close_inputs --self-check
python -m astock.sector_drive --self-check
python -m astock.us_sectors --self-check
```

## 对话

用 Cursor 打开本仓库时，`.cursor/skills/a-share-analysis/SKILL.md` 只把分析对话指到根目录的 `desk.md`。规则不要写回 skill。
