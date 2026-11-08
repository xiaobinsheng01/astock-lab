# astock-lab

A股分析 skill 的维护仓库。规则、脚本和分层说明在这里改，不放进 claw-code。

用 Cursor 打开本仓库即可。skill 在 `.cursor/skills/a-share-analysis/`，对话里按这个目录加载。

## 分层

`SKILL.md` 只做调度。正文按层打开，未点名的层不读进对话。脚本仍按该轮要求算完。

| 层 | 文件 | 内容 |
| --- | --- | --- |
| 1 资料 | `references/01-data.md` | 渠道、时点、资料面增量、外围 |
| 2 规则 | `references/02-rules.md` | 大盘四态、W6、板块状态、缠论、硬门 |
| 3 账户 | `references/03-account.md` | 行为分状态、持仓、前十大两格 |
| 4 判定 | `references/04-judgment.md` | 路径、对冲、托住、发力、今日关注 |
| 5 执行 | `references/05-execution.md` | 终分、初分、盘中、定时 |
| 6 产出 | `references/06-output.md` | 收盘五行或盘中六行 |

改规则时改对应层，不要把六层再写回一份 `SKILL.md`。权重数字仍以 Canvas 为准，不在调度文件里改。

## 脚本

路径保持 `.cursor/skills/a-share-analysis/scripts/`，与 skill 正文里的命令一致。

```bash
cd .cursor/skills/a-share-analysis/scripts
python3 -m unittest test_overseas_feed.py test_intraday_read.py
```

这两项不访问网络。`info-ledger.md` 和 `cache/` 是运行时记录，不进 git。
