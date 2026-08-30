# W6-0.1 持续评估控制面首轮证据

状态：`pass` · `acceptance/evaluation` · 不代表候选采用或产品可发布

## 1. 目的与边界

本轮验证 `1-4-3-2：定义版本漂移触发、自动回归与暂停回滚证据`。它验证的是
评估控制面，而不是 DeepSeek Harness、Pi Agent Harness、Codex Harness、OpenCode
或 Goose 的真实 adapter。

runner 每个控制周期都运行 W6-0.1 隔离 fixture self-test，再把 synthetic control
summary 送入只读 `check_regression.py`。候选未被调用，未使用真实凭证、生产数据或
外部网络；生成的 synthetic status 不能写回候选证据矩阵。

## 2. 运行信息

- Runner：`w6-continuous-evaluator/v1`
- Fixture：`W6-0.1` / `w6-0.1`
- Run：`evaluation/runs/w6-0.1-continuous-20260830T124122-090590Z/`
- Summary：`evaluation/runs/w6-0.1-continuous-20260830T124122-090590Z/summary.json`
- 控制身份：`control-harness-v1`，Provider 为 loopback fake-a，sandbox 为
  `fixture-local-v1` / `loopback-only`

## 3. 结果

| 控制场景 | 结果 | 证据 |
|---|---|---|
| stable/no drift | `pass`，`allow` | `cycles/stable-no-drift/regression-gate.json` |
| 13 个身份维度逐项漂移 | 13/13 触发 `drift_triggered=true`，均执行 fixture self-test | `summary.json` 的 `drift_matrix` |
| fixture source hash 漂移 | `fail`，`pause` | `cycles/drift-fixture_source/regression-gate.json`、`pause-decision.json` |
| 硬失败（Codex C2） | `fail`，`pause` | `cycles/hard-failure-pauses/regression-gate.json`、`pause-decision.json` |
| 关键 unknown（Codex C7） | `pending`，`pause` | `cycles/unknown-pauses/regression-gate.json`、`pause-decision.json` |
| 回滚到 v1 后重跑 | `pass`，独立重新门禁 | `cycles/rollback-rerun-v1/rollback-decision.json`、`regression-gate.json` |

Summary 中 7 项 assertions 全部为 `passed=true`，最终状态为 `pass`。其中
`fixture_source` 的 hard failure 是有意设计：冻结版本的 fixture hash 变化不能
仅凭回归结果放行，必须先重新冻结/审计新 fixture 版本。

## 4. 已确认的决策

1. 漂移维度必须在结构化 `evaluation_identity` 中表达，并输出可定位的字段路径。
2. 漂移触发的是一次新的隔离回归，不是自动把旧结论复制到新版本。
3. `fail` 与关键 `pending` 都执行 `pause-upgrade-and-composition`；unknown 不被
   当作通过，也不通过修改阈值消失。
4. 回滚必须指向已保存的 last-known-good identity，记录 from/to、原因、目标 summary
   和新门禁结果；回滚后仍需重新门禁，不能凭回滚动作本身放行。
5. 该控制面只能说明 W6 评估协议可复核；W7 仍需绑定至少一个候选固定版本 adapter，
   并补真实候选 C2–C7 与 C7 真人运维计时。

## 5. 后续限制

本轮 synthetic control summary 没有替代真实候选运行。进入 W7 后，候选 adapter 的
run manifest 必须填充相同 `evaluation_identity` 维度；任何字段缺失、候选版本未固定、
回放 cassette 或 sandbox 不匹配，都只能保持 `pending`，不能进入采用排序。
