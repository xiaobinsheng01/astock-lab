# 第 9 层 · A股交易员

交易员是一个岗位，不是一个语气。它的活是把已经算好的数写成一整套下一交易日能逐条核对的 claim，并交给记分板。它不改权重、不改硬门、不下单、不另取一套数。

本层只在用户要「交易员怎么看」「按交易员写法写一份」「出一份 claim」时打开。收盘五行、盘中六行仍按 `rules/06-output.md`，不因为读了本层就换产出格式。

## 一、交易员读什么

数据全部来自同轮已经跑完的脚本，不新开取数。缺哪块就写未核，不拿别的数顶替。

| 要写哪一格 | 数据来自 |
| --- | --- |
| 上证方向、主路径 | `python -m astock.close_inputs` 的 `structure`、`session_path`、`four_paths` |
| 行业强弱、板块分类 | `python -m astock.industry`，申万 31 个一级行业的两栏表 |
| 量价四态、均线 | `python -m astock.technique`，行业用 `--industry`，个股用代码 |
| 行为分、板块看涨 | `rules/04-judgment.md`，沿用上一份终分，不重算 W1–W5 |
| 修复、对冲、托住 | `close_inputs` 的 `repair`、`structure` |

交易员不看：波浪的浪级编号、新闻原文、股吧情绪、券商目标价。这几样要写只能写进 `wave` 或 `note`，不进 check。

## 二、六个固定格子

每格一句，写满写不满都照实写。没有核对条件的句子不许出现在结论里。

| 格子 | 写什么 | 用的 check |
| --- | --- | --- |
| `index_path` | 上证收在四条路径哪一段 | `index_zone` |
| `index_dir` | 上证收涨还是收跌 | `index_pct` |
| `sector_strong` | 哪个申万一级行业会强于上证，强几个百分点算中 | `sector_vs_index` |
| `sector_state` | 行业的两栏分类明天是什么 | `industry_pick` |
| `volume` | 量价四态落在哪一格 | 由日线算出，当天写、当天核 |
| `risk` | 哪条风险会触发 | `breadth` 或 `quote_above` |

`volume` 这一格要日线才算得出，取数包里没有就不写。不拿当天涨跌方向冒充量价四态。

## 三、怎么写

先跑：

```
python -m astock.trader slots --as-of <交易日>
```

这份格子清单会印出允许的 check 类型和四条硬规则。按它填，不按自己的习惯填。

再用当轮取数包生成草稿：

```
python -m astock.trader draft --file <取数包.json> --name 上证
```

草稿只做「有数才有 claim」：缺数的格子空着，不给默认方向。模型在这个骨架上确认或改写，不重造核对条件。

写完之后校验：

```
python -m astock.trader check --file <草稿.json>
```

校验通过才写进结论，再交给：

```
python -m astock.forecast predict --file <单条记录.json>
```

草稿和 `forecast` 用同一套准入规则（`trader.check` 内部直接调用 `forecast.validate`），所以校验通过的一定收得下，不通过的一定拒收。两套规则不能分叉。

## 四、三条不许

- **不许猜方向。** 报价没取到，`index_dir` 空着写未核，不写「大概率收涨」。空着的格子比编一个方向诚实。
- **不许把分类写成预测语气。** 板块两栏分类是历史统计，`industry_pick` 核的是明天算出来还是这个分类，不是「明天会涨」。分类改口要说清是哪一天变的、因为什么样本变了。
- **不许把波浪做成 check。** 波浪只写文字，进 `wave` 字段给复盘读，不进验证、不进记分板、不进行为分。这一条和 `rules/04-judgment.md` 的「长周期在哪一段」一致。

## 五、多少格算写完了

- 六格全写：写「交易员六格齐」。
- 五格或更少：写清哪几格空着、缺的是什么数据。不为了凑满去编。
- `index_path`、`index_dir` 两格必须写。这两格写不出来，整份 claim 不交，直接写「交易员未出稿，缺指数区间数据」。

交易员出稿不等于可以开仓。行为分低于 0.4 时，这份 claim 只用于核对，不改硬门、不给可加到、不写买入。

## 六、收盘怎么用这份稿

收盘按 `python -m astock.forecast resolve` 逐条判。判完看 `scoreboard`，按格子名分开看：`上证.index_path` 和 `上证.sector_state` 混在一起算命中率没有意义，只有分开看才知道自己是看指数准还是读板块准。

记分板不改权重、不改硬门、不反向影响任何一格。连续写错不改任何结论，只改这一份稿的可信度。
