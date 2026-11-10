# astock-lab

A 股行情分析交易台。尺子、算盘、当日底稿、会话钟分开，仓库根目录就能看完，不把项目塞进 `.cursor/skills/`。

权重数字仍以 Canvas 为准。本仓库不复制一份会漂的分数表。计算器只印数，不下单，不接证券账户。

## 四样东西

| 位置 | 是什么 | 谁改 |
| --- | --- | --- |
| `rules/` | 尺子。资料、规则、账户、判定、执行、产出六层 | 改判断只改对应层 |
| `astock/` | 算盘。行情、涨停、股东、新闻列表。标准库，无第三方依赖 | 改取数和分类 |
| `runtime/` | 当日底稿。`info-ledger.md`、`cache/holders.json` | 跑起来才写，不进 git |
| `desk.md` | 会话钟。这一轮读哪一层、跑哪条命令、写成五行还是六行 | 改时点，不改权重 |

下层没齐，上层停写。任何模式先读 `rules/02-rules.md` 的「硬门」。

## 六层

| 层 | 文件 | 内容 |
| --- | --- | --- |
| 1 资料 | `rules/01-data.md` | 渠道、时点、资料面增量、外围 |
| 2 规则 | `rules/02-rules.md` | 大盘四态、W6、板块状态、缠论、硬门 |
| 3 账户 | `rules/03-account.md` | 行为分状态、持仓、前十大两格 |
| 4 判定 | `rules/04-judgment.md` | 路径、对冲、托住、发力、今日关注 |
| 5 执行 | `rules/05-execution.md` | 终分、初分、盘中、定时 |
| 6 产出 | `rules/06-output.md` | 收盘五行或盘中六行 |

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
python -m astock.us_sectors
python -m astock yaogu --monitor
python -m astock route --at "2026-11-10 10:00" --ask "盘中"
python -m astock lake hot --today 2026-11-10
```

短名与上面的模块一一对应：`close`、`news`、`brief`、`screen`、`drive`、`overseas`、`us`、`yaogu`、`route`、`lake`、`sentence`、`a50`、`cctv`、`cfbond`、`cninfo`、`cash`。例如 `python -m astock close --fast`。

取数和分析分成两个窗口。`route` 打印这一轮读什么、跑什么。分析窗口不取数。资料湖在 `runtime/lake/`，不进 git。

离线核对：

```bash
python -m unittest tests.test_overseas_feed tests.test_intraday_read tests.test_route tests.test_sentence tests.test_lake tests.test_channels tests.test_yaogu
python -m astock.close_inputs --self-check
python -m astock.sector_drive --self-check
python -m astock.us_sectors --self-check
```

## 对话

用 Cursor 打开本仓库时，`.cursor/skills/a-share-analysis/SKILL.md` 只把分析对话指到根目录的 `desk.md`。规则不要写回 skill。
