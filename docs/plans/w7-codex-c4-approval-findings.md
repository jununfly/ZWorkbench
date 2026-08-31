# W7 Codex C4 组合式 Approval 评估结果

状态：`pass-with-composition` · `acceptance/evaluation` · 不代表 Codex 原生 approval 或 ZWorkbench 产品通过

本轮关闭的是 C4 的“组合式 approval owner”未知，不是把 Codex 原生 approval 能力判定为已通过。验证资产是 case-local composition adapter 和隔离 fixture；没有修改 ZWorkbench 产品代码、全局 `CODEX_HOME`、真实凭证、真实 Provider、生产项目或不可逆外部副作用。

## 1. 固定边界与证据

| 项目 | 固定值 |
|---|---|
| 候选 | Codex Harness（`openai/codex`） |
| CLI | `/opt/homebrew/bin/codex`，`codex-cli 0.139.0` |
| 入口 | `app-server` over `stdio://` |
| Provider | case-local loopback fake Provider |
| workspace / `CODEX_HOME` | 每个 case 独立目录 |
| composition adapter | `zworkbench-w7-codex-c4-approval/v1` |
| 业务 approval owner | case-local `approval-gate.py` |
| 正向副作用 | 仅 `case-effect-target`，按 operation 去重 |
| 正式运行 | [`summary.json`](../../evaluation/runs/w7-codex-c4-approval-20260831T032346-194000Z/summary.json) |

正式运行覆盖 `4` 个故障点 × `3` 类工具 × 每格 `3` 次重复，共 `36` cases：

- 故障：`turn_interrupt`、`provider_timeout`、`tool_timeout`、`process_interrupt`；
- 工具：`read-only`、`idempotent`、`approval-required`；
- approval-required 另加无 token、scope mismatch、token replay 三类负向控制。

## 2. 结果与阈值

| 检查 | 结果 |
|---|---:|
| 总体 | **36/36 pass-with-composition** |
| unknown / fail | `0 / 0` |
| recovery controls | `36/36` |
| 关键 ID 关联完整 | `36/36` |
| 状态丢失 | `0` |
| 危险副作用重复 | `0` |
| 每 case 最大 retry | `1` |
| 每 case 最大 physical effect | `1` |
| 无 token / scope mismatch effect | `0` |
| token replay effect | `0` |
| 原生 Codex approval request | `0/36`，继续记为 `unknown` |

所有正式 case 的最终状态为 `completed`。approval request、decision、effect、tool result 均由同一 `run_id`、`operation_id`、`idempotency_key` 关联；批准 token 只允许一个 action、一个 resource、一次尝试。未知 server request 和非 allowlist 命令在 transport 边界 deny；业务 gate 默认 fail-closed。

## 3. 评估器修正记录

首轮结果为 `24/36`，12 个 approval-required case 因 replay 控制使用了独立 ledger 而被错误标记为失败。修正内容是：

1. replay 控制复用正向 case 的 approval state 与主 ledger；
2. 控制 oracle 只统计本次调用新增的 effect/result 记录，避免把历史正向 effect 混入 replay 结果；
3. `tool_timeout` 在 gate 的有界延迟期间允许 in-flight 命令收敛，再进行 replay 检查；
4. runner 的 `--codex` executable 贯穿初始启动和 process-interrupt 恢复路径。

修正后的正式运行是 `36/36`。两次修正前运行均保留为历史证据，不纳入正式候选结论。

## 4. C4 结论与明确边界

### 可以关闭的阻断项

在固定 Codex `0.139.0` 的真实 `app-server` tool path 上，一个单一的、外部的、case-local composition owner 可以补齐：

- approval request / decision / effect / result 的 durable 关联；
- 无 token、scope mismatch、token replay 的 fail-closed；
- 中断、Provider timeout、tool timeout、process interrupt 后的 reconcile 或 safe-stop；
- one-action / one-resource / one-attempt 的副作用边界；
- bounded retry 与副作用去重。

因此 C4 的组合路径可以标记为 `pass-with-composition`，允许进入 C7 生命周期审计。

### 不能关闭、必须继续携带的未知

- 本轮没有观察到 Codex 原生 `item/commandExecution/requestApproval`；
- `native_approval` 仍为 `unknown/not-required-for-composition`；
- 不得把 W6 C2 scripted adapter 或本轮 gate 的通过回填成 Codex 原生 approval 通过；
- 本轮不证明任意 shell、插件、MCP、子进程、宿主 broker 或未来 tool surface 都经过同一 policy owner；
- 本轮不证明宿主级 sandbox、真实 Provider、真实凭证或生产不可逆副作用安全。

所以 C4 的生产语义是：`recovery-controls-pass + composition approval pass + native approval unknown`，不是无条件 C4 pass。

## 5. ATAM 解释

| 风险 / 敏感点 | 本轮证据 | 责任边界 | 残余风险 |
|---|---|---|---|
| 中断后副作用重复 | 36/36，physical effect ≤1 | composition effect ledger + gate | 生产 ledger 的持久化与迁移未测 |
| 未授权或错 scope 执行 | 三类负向控制均 zero effect | gate policy owner | 真实宿主强制边界未测 |
| token 重放 | 36 个 approval case 均 blocked、zero effect | gate approval state | token 存储、轮换和跨版本策略未测 |
| approval owner 不清晰 | 原生 request 未被提升；单一 gate owner 明确 | Codex transport + 外部 composition owner | 原生 approval 语义仍未知 |
| tool timeout 竞态 | in-flight gate 收敛后 replay 仍被阻断 | adapter reconcile / safe-stop | 生产工具可能无法在 bounded window 内收敛 |

ATAM 结论：C4 的主要未知已从“没有明确 approval owner”收窄为“原生 approval surface 与生产宿主强制边界仍未知”。该未知不能通过解释、C2 复用或 replay default-deny 证据消除。

## 6. CBAM 决策（个人开发者 / 小团队）

当前继续采用“一个主 Harness + 一个必要薄 composition owner”的最小组合：

- 增量收益：关闭 C4 的 approval/recovery seam，且 C3-C6 共用 durable identity、ledger 和单一 owner；
- 增量成本：维护 approval schema、Codex 版本回归、ledger 备份/迁移、故障诊断与退出；
- 当前维护服务计数保持为候选 runtime + 一个 composition owner，仍不引入第二 Harness、Temporal/LangGraph、LiteLLM 或独立观测平台。

任何新增组合件都必须重新证明它降低了明确的 C2-C7 风险，并计入个人开发者/小团队的安装、升级、恢复、排障、服务数、许可证与退出成本；功能数量本身不足以形成 CBAM 通过。

## 7. 路线放行

- `1-7`：可标记 `completed`；结论为 `pass-with-composition`；
- `C4 native approval`：继续 `unknown`，作为采用前提和版本回归项；
- `C7`：仍为下一主线，当前 `unknown/stop`，需完成真实单人安装、升级/回滚、备份恢复、故障诊断计时、许可证/NOTICE/商业边界审查与 source-to-binary provenance；
- 产品实现：尚未开始，本轮只完成验收 fixture、证据和决策边界。

## 8. 资产索引

- [`run_codex_c4_approval.py`](../../evaluation/runner/run_codex_c4_approval.py)
- [`w7-codex-c4-approval fixture`](../../evaluation/fixtures/w7-codex-c4-approval/README.md)
- [`C4 summary.json`](../../evaluation/runs/w7-codex-c4-approval-20260831T032346-194000Z/summary.json)
- [`W7 C3/C4 findings`](./w7-codex-c3-c4-findings.md)
- [`W7 C7 findings`](./w7-codex-c7-findings.md)
- [`W7 roadmap`](./personal-workbench-w7-roadmap.md)
