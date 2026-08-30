# W7 Codex C3/C4 隔离验证结果

状态：`C3 pass-with-composition` · `C4 recovery-controls-pass / approval-boundary-unknown` ·
`acceptance/evaluation` · 不代表 Codex 原生或 ZWorkbench 产品通过

本轮完成固定 Codex Harness `0.139.0` 的真实 app-server 入口验证。验证资产是
外部 composition adapter 和 case-local fixture，不是 ZWorkbench 产品实现；所有
Provider、workspace 和副作用都限制在隔离运行目录。

## 1. 固定边界

| 项目 | 固定值 |
|---|---|
| 候选 | Codex Harness（`openai/codex`） |
| CLI | `/opt/homebrew/bin/codex`，`codex-cli 0.139.0` |
| 入口 | `app-server` over `stdio://` |
| Provider | `w7-fake-codex`，loopback `127.0.0.1:11434` |
| workspace | 每 case 独立临时目录，Codex `workspace-write` |
| adapter | `w7-codex-c3-c4-composition-adapter/v1` |
| durable owner | 外部 adapter；持有 schedule、attempt、state、effect、result ledger |
| 关键关联 | `schedule_id`、`idempotency_key`、`run_id`、`thread_id`、`turn_id` |
| 外部副作用 | 仅 case-local `effect-sink.py`，按 `operation_id` 去重 |

真实 Codex JSON-RPC 路径至少经过 `initialize`、`thread/start`、`turn/start`；恢复
场景还经过 `thread/resume`、`turn/interrupt`，没有调用真实 Provider、真实凭证、
真实项目或外部系统。

## 2. C3 结果：通过但依赖 composition

证据：
[`summary.json`](../../evaluation/runs/w7-codex-c3-c4-20260830T162343-560708Z/summary.json)

| 检查 | 结果 |
|---|---:|
| 触发语义 | `first`、同 key duplicate、delayed、interrupted/retry、missed |
| 每类重复 | `3` |
| cases | `15/15 pass` |
| 同 key 有效副作用 | `1` |
| 重复 trigger 产生额外副作用 | `0` |
| 关联字段缺失 | `0` |
| durable result 缺失 | `0` |

结论是 `pass-with-composition`，责任属于外部单一 durable owner。该结果证明
adapter 能把外部调度/幂等与 Codex thread/turn 关联起来，不证明 Codex 原生提供
schedule、cron、时区、错过触发或 idempotency contract。`native_scheduler` 在本轮
仍为 `not measured`。

## 3. C4 结果：恢复控制通过，审批边界未知

证据：
[`summary.json`](../../evaluation/runs/w7-codex-c3-c4-20260830T162236-375354Z/summary.json)

矩阵是 `4` 个故障点 × `3` 类工具 × `3` 次重复，共 `36` 个隔离 case：

| 检查 | 结果 |
|---|---:|
| `turn_interrupt`、`provider_timeout`、`tool_timeout`、`process_interrupt` | 均已注入并记录 |
| recovery control pass | `36/36` |
| cases overall pass | `24/36` |
| cases unknown | `12/36` |
| cases fail | `0/36` |
| 状态丢失 | `0` |
| 不安全副作用重复 | `0` |
| 每 case 最大 retry | `1` |
| 每 case 最大 physical effect | `1` |
| reconcile 或 safe-stop 证据 | `36/36` |
| approval-required 原生 request | `0/12` |

`read-only` 与 `idempotent` 的 `24/24` case 通过。`approval-required` 的 `12/12`
case 均保留了 `thread_id`/`turn_id`，完成了 reconcile 或 bounded retry，且没有
重复副作用，但没有收到
`item/commandExecution/requestApproval`。评估器因此将它们标为
`unknown`，并为每个 case 写入 `codex.approval.request.missing`；不会把它们算作
恢复失败，也不会把它们算作 Codex 原生审批通过。

这里的结论是一个固定配置下的边界观察：`workspace-write` + `approvalPolicy=on-request`
下的 case-local 命令没有触发原生 approval request。它不等价于“Codex 在所有
命令/环境中都没有审批能力”，也不等价于“Codex 原生审批安全可用”。

## 4. ATAM 解释

| 风险/敏感点 | 结果 | 责任边界 |
|---|---|---|
| `R-C3-01`：触发重复导致重复运行 | 风险在 fixture 中收窄；同 key 仅一次有效 effect | 外部 schedule/idempotency owner |
| `R-C4-01`：中断后 resume 重复不可逆副作用 | 本轮观察为 `0` 次重复；依赖先 reconcile 外部 ledger | 外部 effect/result ledger |
| `R-C4-02`：状态恢复依赖有损 ThreadItems | 未把 ThreadItems 当作唯一账本；以外部 state/ledger 决策 | composition adapter |
| `SP-C4-01`：跨对象关联缺失 | `36/36` recovery case 关键 ID 可关联 | adapter schema 与 evaluator |
| `SP-C2/C4-01`：审批 owner 不清晰 | Codex 原生审批证据仍 unknown；不得由 C2 fixture 回填 | 候选原生 surface + 外部 C2 owner 待显式组合 |

因此 W7 不放行“Codex 原生 durable workflow 已通过”。当前可放行的窄结论是：
一个外部 durable owner 可以在隔离 fixture 中补足 Codex 的 C3/C4 关联、幂等、
恢复、reconcile 和 bounded retry seam。

## 5. CBAM 影响

本轮支持“一个主 Harness + 必要薄层”的待验证路线：C3/C4 只需要一个外部
owner，当前没有证据表明第二 Harness、Temporal、LangGraph 或独立 scheduler 能
带来非重复收益。

新增成本和未决责任包括：

- adapter 必须维护 Codex thread/turn、外部 run 和 effect/result ledger 的 schema；
- Codex 升级、sandbox 或 tool surface 改变时必须重跑 C3/C4；
- 原生 approval 与外部 C2 fail-closed adapter 的 owner 不能重叠或留空；
- durable ledger 的备份、迁移、查询和退出成本尚未进入 C7 真人运维证据。

因此本轮不引入第二 Harness、Temporal/LangGraph 或 LiteLLM；它们只能在候选
C5/C6/C7 和个人开发者/小团队生命周期成本证据齐全后重新做 CBAM。

## 6. 放行与下一节点

- C3：`pass-with-composition`，可以作为 Codex 后续 C5/C6 adapter 的输入边界。
- C4：`recovery-controls-pass`，但整体 `unknown/stop`，不能签署候选 C4 通过。
- Codex 原生 approval：本轮 `unknown`；不能由 W6 C2 或本轮 sink 证据替代。
- 产品实现：本轮没有修改 ZWorkbench 产品代码，不进入发布或采用。

要消除 C4 的关键 unknown，下一次只能走以下两条可审计路径之一：

1. 将 W6 C2 fail-closed adapter 作为明确的外部 approval owner 接入 Codex tool
   path，单独建立 composition-owned approval fixture；或
2. 找到在固定 Codex 版本上稳定触发原生 approval request 的隔离工具/环境组合，
   再重复相同 fault matrix。

在完成其中一条之前，路线继续进入后续 C5/C6 时必须携带 C4 的
`approval-boundary-unknown` 标记，不得把 `24/36` 改写成 `36/36`。

## 7. 资产索引

- [`run_codex_c3_c4.py`](../../evaluation/runner/run_codex_c3_c4.py)
- [`w7-codex-c3-c4 fixture`](../../evaluation/fixtures/w7-codex-c3-c4/README.md)
- [`C2 findings`](./w7-codex-c2-findings.md)
- [`C3/C4 boundary`](./w7-codex-c3-c4-boundary.md)
- [`W7 roadmap`](./personal-workbench-w7-roadmap.md)
