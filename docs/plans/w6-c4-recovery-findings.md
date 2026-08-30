# W6-0.1 C4 中断、超时、恢复与副作用重试证据

状态：fixture contract 首轮通过 · `acceptance/evaluation` · 不是 ZWorkbench 产品实现，也不是候选 Harness 已具备 C4 能力的证明

本报告记录 C4 的首轮确定性验证。它验证的是一个隔离的 durable-run 状态机和评估 runner 是否满足 W6-0.1 的恢复合同；候选只有在接入候选专属、固定版本 adapter 后，才能把 C4 从 `unknown` 更新为候选实测结果。

## 1. 运行身份与边界

| 项目 | 值 |
|---|---|
| Run ID | `w6-0.1-c4-20260830T101004-470428Z` |
| 运行时间 | `2026-08-30T10:06:51.532469+00:00` – `2026-08-30T10:06:53.783945+00:00` |
| Fixture | [`evaluation/fixtures/w6-0.1`](../../evaluation/fixtures/w6-0.1) |
| Fixture 版本 | `W6-0.1` |
| Fixture manifest SHA-256 | `e0342a1e...2b9cf6` |
| Fixture source SHA-256 | `7f8c42cf...9f2d33b` |
| 状态机 | [`c4-state-machine.py`](../../evaluation/fixtures/w6-0.1/c4-state-machine.py) |
| 状态机 SHA-256 | `016af506...5d36cdd0` |
| Runner | [`run_c4.py`](../../evaluation/runner/run_c4.py) |
| Runner 版本 | `w6-c4-runner/v1` |
| 正式证据 | [`summary.json`](../../evaluation/runs/w6-0.1-c4-20260830T101004-470428Z/summary.json) |

所有“副作用”都只是 case 目录中的本地 ledger 记录；没有真实 Provider、真实凭证、外网、Git push、部署或不可逆外部写入。进程中断用真实子进程 `SIGTERM` 注入，runner 随后对同一 run 目录执行 resume。

## 2. 覆盖范围与门槛

6 个固定注入点分别为：

1. 工具执行前；
2. 工具完成但状态提交前；
3. 状态提交后、下一步前；
4. Provider timeout；
5. tool timeout；
6. 进程中断。

每个注入点覆盖 `read-only`、`idempotent`、`approval-required` 三种工具类别，每种重复 3 次。因此总计 `6 × 3 × 3 = 54` 个案例；每个注入点 9 个观测，达到“每注入点至少 3 次”的 W6-0.1 要求。

| 门槛 | 结果 |
|---|---:|
| 案例通过 | `54/54` |
| 恢复或安全终止 | `54/54`（100%） |
| 关键状态丢失 | `0` |
| 不可安全重放副作用重复 | `0` |
| 无界 retry 案例 | `0` |
| 故障注入 ledger | `54/54` 每案例恰好 1 条 |
| 状态转移顺序 | `54/54` 合法 |
| fixture contract | `pass` |

## 3. 恢复语义实测

| 注入点 | read-only | idempotent | approval-required |
|---|---|---|---|
| `before_tool` | 从 Provider checkpoint resume，工具执行 1 次 | 同上，唯一 effect 1 | 同上，已批准动作执行 1 次 |
| `after_tool_before_commit` | 从 tool-result ledger reconcile | 从 result/effect ledger reconcile，不重执行 | 从 effect ledger reconcile，不重执行不可重放动作 |
| `committed_before_next_step` | 直接从 committed checkpoint 进入下一步 | 不重复 effect | 不重复已批准动作 |
| `provider_timeout` | Provider 有界 retry 1 次，随后完成 | 同上 | 同上 |
| `tool_timeout` | 工具 retry 1 次后完成 | retry 1 次；第二次由 operation key 去重，logical effect 仍为 1 | `safe_stopped`，保留未知结果，不自动 retry |
| `process_interrupt` | 实际 SIGTERM 后对 read-only 做一次 replay-safe retry | 从 effect ledger reconcile，不重执行 | 从 effect ledger reconcile，不重执行 |

聚合观测与固定语义一致：

- `before_tool`、`after_tool_before_commit`、`committed_before_next_step`：每类均为 `provider_attempts=1`、`tool_attempts=1`、`retry_count=0`；
- `provider_timeout`：每类均为 `provider_attempts=2`、`retry_count=1`；
- `tool_timeout`：read-only/idempotent 为 `tool_attempts=2`、`retry_count=1`，approval-required 为 `tool_attempts=1`、`retry_count=0`、`safe_stopped`；
- `process_interrupt`：初始子进程返回 `-15`，resume 返回 `0`；read-only 做一次有界 retry，idempotent 和 approval-required 均通过 effect ledger reconcile；
- idempotent 与 approval-required 每个案例均只有 1 条 effect ledger 记录、1 次物理 effect apply；read-only 为 0 条；
- 每个案例都保留 `state.json`、`events.jsonl`、`transitions.jsonl`、`faults.jsonl`、`attempts.jsonl`、`tool-results.jsonl`、`effects.jsonl`、初始/恢复命令结果和 case manifest。

## 4. 可复核证据结构

完整证据位于 [`evaluation/runs/w6-0.1-c4-20260830T101004-470428Z/`](../../evaluation/runs/w6-0.1-c4-20260830T101004-470428Z/)。`summary.json` 保存冻结 fixture 身份、阈值、54 个案例的逐例断言、聚合指标和候选 unknown 账本；每个 case 目录可以独立检查：

```text
cases/<fault>/<tool-class>/repeat-<nn>/
├── case-manifest.json
├── initial-result.json
├── resume-result.json
├── state.json
├── events.jsonl
├── transitions.jsonl
├── faults.jsonl
├── attempts.jsonl
├── tool-results.jsonl
└── effects.jsonl
```

状态机只允许以下状态链：

```text
ready → provider_succeeded → tool_started → committed → completed
                                      └──────────────→ safe_stopped
```

恢复时只从 durable checkpoint 或 ledger 进行 reconcile；工具类别和 operation id 绑定在 state 与 effect ledger 中，避免把“重试成功”误报为“副作用执行了两次”。

## 5. 候选状态与边界

DeepSeek Harness、Pi Agent Harness、Codex Harness、OpenCode、Goose 在本批次均为 `unknown`，原因相同：当前没有候选专属、固定源码/版本的 C4 adapter；fixture contract 通过不能转化为候选通过。C2 adapter 的证据也不能替代 C4 的候选接入。

因此本批次没有 W7 采用排序，也没有证明任一候选具备生产级 durable state、恢复、重试或副作用协调能力。尤其未验证：

- 候选自身运行时能否在真实 tool/provider/process 边界保存同等 ledger；
- 宿主 sandbox、tool proxy/broker 与恢复层组合后是否仍保持 fail-closed；
- 多进程/并发 run、真实外部系统的幂等协议和人工接管流程；
- 候选版本漂移、升级/回滚后 ledger schema 的兼容性。

## 6. ATAM/CBAM 增量观察

### ATAM

| 项目 | C4 前 | 本批次更新 | 仍未解决 |
|---|---|---|---|
| R-02：重试重复副作用或丢状态 | C3/C4 unknown | 隔离状态机合同 54/54 通过；副作用 ledger 和 safe-stop 语义可复核 | 仅降低 fixture/协议设计风险；候选、宿主隔离和真实外部副作用仍 unknown |
| SP-02：恢复边界与工具类别 | 尚未实测 | 三类工具类别、6 注入点和 retry 上界形成敏感点证据 | 需对每个候选确认工具分类是否可信、是否可强制 |
| TP-02：自有 durable 层 vs 引入编排器 | 尚无 C4 数据 | 轻量状态机的证据账本成本可量化，且不需常驻服务 | 不能据此否定 Temporal/LangGraph；需 C3/C7 比较其增量收益和运维成本 |

### CBAM

| 选项 | 本批次观察到的收益 | 增量成本/风险 | 姿态 |
|---|---|---|---|
| 一个主 Harness + 薄 durable/recovery adapter | 可用统一状态、attempt、fault、effect ledger 验证 C4 合同 | 每个候选仍需 adapter；需锁定状态 schema、工具类别和 operation id | 保留为待候选接入验证的主路线 |
| 第二个 Harness | 本批次没有新增候选 C4 证据 | 继续扩大恢复、权限、Provider 和升级矩阵 | 不因 fixture 通过而引入拼盘 |
| Temporal/LangGraph | 理论上可能提供 durable workflow/retry | 本批次无常驻服务、迁移、排障和小团队成本数据 | 保持候选，等待 C3/C7 |
| 仅从零自建 Agent loop | 本批次无收益 | 需要同时承担 loop、状态、权限、事件和 replay 的长期维护 | 不作为当前 C4 行动 |

本次评估实现了 acceptance artifact，不代表 ZWorkbench 应立即实现同样的产品模块。C4 合同通过后，路线图下一步进入 C5 双 Provider 故障切换与显式降级；候选 C4 仍需在安全 adapter 和固定版本边界下单独实测。
