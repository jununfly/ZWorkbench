# W6-0.1 C3 定时、重复触发与幂等证据

状态：fixture contract 首轮通过（`pass-with-composition`）· `acceptance/evaluation` · 不是 ZWorkbench 产品实现，也不是候选 Harness 已具备 scheduler/幂等能力的证明

本报告记录 C3 的首轮确定性验证。外部触发器、durable idempotency ledger 与 loopback fake-sink 被作为一个明确的组合件验证：它证明跨触发 Run 的幂等合同，但不把外部触发器的能力冒充成 Harness 原生 scheduler。

## 1. 运行身份与边界

| 项目 | 值 |
|---|---|
| Run ID | `w6-0.1-c3-20260830T102401-857158Z` |
| 运行时间 | `2026-08-30T10:24:01.857158+00:00` – `2026-08-30T10:24:04.043551+00:00` |
| Fixture | [`evaluation/fixtures/w6-0.1`](../../evaluation/fixtures/w6-0.1) |
| Fixture 版本 | `W6-0.1` |
| Fixture manifest SHA-256 | `e0342a1e...2b9cf6` |
| Fixture source SHA-256 | `b428a4f6...2554ae` |
| 状态机 | [`c3-idempotency.py`](../../evaluation/fixtures/w6-0.1/c3-idempotency.py) |
| 状态机 SHA-256 | `7bf50000...971139` |
| Runner | [`run_c3.py`](../../evaluation/runner/run_c3.py) |
| Runner 版本 | `w6-c3-runner/v1` |
| 正式证据 | [`summary.json`](../../evaluation/runs/w6-0.1-c3-20260830T102401-857158Z/summary.json) |

运行不访问真实 Provider、真实凭证或外部消息。fake-sink 只监听 loopback，并把收到的本地测试 payload 写入当前 case 目录；所有状态、attempt、schedule、result 和 effect ledger 同样保存在 case 目录。

## 2. 覆盖范围与结果

| 场景 | 触发语义 | 重复次数 | 结果 |
|---|---|---:|---|
| `first_trigger` | 首次触发 | 3 | 3/3 pass |
| `same_key_duplicate` | 同一 logical trigger 的相同 key 重复到达 | 3 | 3/3 pass |
| `delayed_trigger` | 同一 logical trigger 延迟到达 | 3 | 3/3 pass |
| `interrupted_retry` | side effect 已到达后进程中断，恢复并再次收到重复触发 | 3 | 3/3 pass |
| `missed_trigger` | 错过一次触发后按 `run-once-late` 补投递 | 3 | 3/3 pass |

总计 `15/15` case pass。所有案例使用：

```text
schedule_id      = daily-summary-v1
logical time     = 2026-08-30T00:00:00Z
idempotency_key  = daily-summary-v1:2026-08-30T00:00:00Z
result_version   = daily-summary-v1:2026-08-30
```

聚合门槛：

- 同一 key 的有效副作用计数始终为 `1`；
- loopback fake-sink 每个 case 只收到 `1` 条 payload；
- 每个 case 只产生 `1` 条 effect ledger 和 `1` 条 versioned result；
- 每一次触发或恢复 invocation 都有 started/terminal attempt 记录；
- 相同 key 重复触发均留下 `idempotency.duplicate`，没有第二次 sink delivery；
- 中断案例初始进程返回 `-15`，resume 返回 `0`，effect ledger 通过 sink observation reconcile；
- missed trigger 记录 `missed=true` 与 `delivery_semantics=run-once-late`；
- fixture contract 为 `pass-with-composition`，因为 scheduler 是外部确定性触发器。

## 3. 关键证据结构

完整证据位于 [`evaluation/runs/w6-0.1-c3-20260830T102401-857158Z/`](../../evaluation/runs/w6-0.1-c3-20260830T102401-857158Z/)。每个 case 目录保存：

```text
cases/<scenario>/repeat-<nn>/
├── case-manifest.json
├── invocation-<nn>-result.json
├── state.json
├── events.jsonl
├── schedule.jsonl
├── attempts.jsonl
├── faults.jsonl
├── effects.jsonl
├── results.jsonl
└── fake-sink.jsonl
```

`state.json` 保存 schedule、key、result version、effect 状态和 sink delivery count；`attempts.jsonl` 保存每次触发/恢复的 started 与 terminal 记录；`effects.jsonl` 与 `results.jsonl` 保证一个 key 只提交一个有效结果；`fake-sink.jsonl` 是副作用 oracle。

中断案例的语义是：先持久化 `in_progress` claim，完成一次 loopback delivery，在 result commit 前注入 SIGTERM；resume 通过 sink 中同一 key 的记录完成 reconcile，而不是再次 delivery。恢复后追加的 duplicate trigger 仍被去重。

## 4. 候选状态与边界

DeepSeek Harness、Pi Agent Harness、Codex Harness、OpenCode、Goose 在本批次均为 `unknown`。当前没有候选专属、固定源码/版本的 C3 adapter，且本批次没有启动任何候选。因此不能据此断言：

- 候选是否拥有可用的原生 scheduler 或 cron CRUD；
- 候选 scheduler 的错过触发、暂停、重试和时区语义；
- 候选 session/Run 是否跨进程共享同一 idempotency ledger；
- 候选工具调用或真实外部系统是否支持相同 operation key；
- 候选升级、并发和多实例下是否仍保持 exactly-once/at-most-once 边界。

候选若没有原生 scheduler，C3 应记为 `pass-with-composition`，但前提是外部 scheduler、幂等层与 Harness 之间没有重复的状态/权限/事件事实，并能保留本报告中的证据字段。

## 5. ATAM/CBAM 增量观察

### ATAM

| 项目 | C3 前 | 本批次更新 | 仍未解决 |
|---|---|---|---|
| R-02：重复触发产生重复副作用 | C3 unknown | 统一 key + effect ledger + sink oracle 在 15/15 case 保持 1 次 delivery | 候选和真实外部系统的幂等契约仍 unknown |
| SP-03：schedule 与 Run 状态 owner | 尚未实测 | external trigger、schedule ledger、attempt ledger 的边界已明确 | 需决定候选原生 scheduler 与自有调度层谁拥有 schedule 状态 |
| TP-03：原生 scheduler vs 外部组合 | 无数据 | 外部确定性触发器可低成本覆盖合同，且不增加常驻服务 | C7 尚未测部署/备份/排障；候选原生能力收益未实测 |
| R-05：错过触发的时间语义 | unknown | `run-once-late` 已有明确 fixture 语义与证据 | 时区、夏令时、重复投递窗口和业务补偿策略仍待产品决策 |

### CBAM

| 选项 | 本批次观察到的收益 | 增量成本/风险 | 姿态 |
|---|---|---|---|
| 外部 scheduler + 薄 idempotency 层 | 可独立验证 schedule/attempt/key/effect，不要求 Harness 提供全部调度能力 | 需维护触发器、状态存储、幂等协议和跨边界关联 | 保留为个人/小团队候选组合，等待 C7 成本验证 |
| Harness 原生 scheduler | 理论上减少组合件和跨进程集成 | 原生语义、权限、备份、恢复和版本绑定仍未测 | 不因“有 scheduler”而优先采用 |
| Temporal/LangGraph | 可能提供 schedule、durable state 和 retry | 常驻服务、部署、迁移、排障成本未测；Agent side effect 仍需自有 idempotency contract | 保持候选，需用 C7 与 C4 的增量数据判断 |
| 第二个 Harness | 本批次没有 C3 增量收益 | 增加 scheduler/session/权限/事件矩阵 | 不引入拼盘 |

本批次证明的是组合边界和幂等合同，不是 W7 最终采用决定。下一步按路线图进入 C5 双 Provider 故障切换与显式降级；C3 候选实测可在后续 adapter 完成后补充。
