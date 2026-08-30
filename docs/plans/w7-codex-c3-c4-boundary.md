# W7 Codex C3/C4 能力边界与 composition adapter 入口

状态：`C3 composition-required · C4 control-surface-observed-but-recovery-unknown` ·
`acceptance/evaluation` · 不代表 Codex 原生或 ZWorkbench 产品通过

本报告记录对固定 Codex `0.139.0` CLI/app-server 的只读能力探针。它不把
“有 resume/interrupt API”扩大解释为完整的 durable workflow，也不重复运行
已经完成的候选无关 C3/C4 fixture。

## 1. 探针身份

| 项目 | 值 |
|---|---|
| 候选 | Codex Harness（`openai/codex`） |
| 固定身份 | [W7 Codex manifest](./w7-codex-candidate-manifest.json) |
| CLI | `/opt/homebrew/bin/codex`，`codex-cli 0.139.0` |
| CLI 探针 | `codex exec --help` |
| app-server 探针 | `codex app-server generate-json-schema --out <temp-dir>` |
| 探针环境 | Darwin 25.5.0 arm64，Node v22.23.1 |
| 外部副作用 | 无；schema 只写入临时目录，未启动 agent 或 Provider |

## 2. C3：调度与幂等

### 观察

`codex exec --help` 暴露一次性非交互执行和 `exec resume`，未发现面向用户的
schedule/cron CRUD、时区、错过触发、schedule_id 或 idempotency_key 合同。
app-server schema 可见 thread/turn/goal/queue 等运行控制请求，但没有被本次
固定版本 schema 证明的 schedule、cron、幂等 claim 或 effect/result ledger
接口。

### 判定

| 能力 | 当前状态 | 解释 |
|---|---|---|
| Codex 原生 scheduler | `unknown/not-evidenced` | 不能把一次性 `exec` 或内部 queue/goal 当作定时任务 |
| 跨触发幂等 | `unknown` | 没有候选可见的 idempotency contract |
| C3 候选状态 | `composition-required` | 需要外部触发器 + 单一 durable schedule/effect/result owner |

这不等于 Codex 明确“不支持调度”；它表示固定版本入口没有足够证据。W7
不得用 W6 外部 deterministic trigger 的 `15/15 pass` 改写 Codex C3。若接入
薄 composition adapter，必须把 schedule 与幂等 ledger 归属到一个 owner，并
证明没有第二个 scheduler 或第二份副作用账。

## 3. C4：中断、恢复与副作用重试

### 观察

固定版本 app-server schema 包含：

- `thread/resume`：可以按 thread id、history 或 path 恢复；
- `turn/interrupt`：可以中断 turn；
- `thread/fork`、`thread/rollback`：可以建立分支或回滚控制路径；
- `thread/status/changed`、`turn/completed` 等状态/事件通知。

但同一 schema 的 `ThreadResumeResponse` 描述明确指出，恢复结果中的 ThreadItems
是有损的，command executions 等全部 agent interactions 并不会完整持久化。
因此这些 API 只证明“控制面有恢复/中断动作”，不证明：

- 工具执行前后、commit 前后的 durable checkpoint 完整保存；
- 外部副作用已经落账或可以安全 reconcile；
- resume 不会再次执行已落地的不可重放副作用；
- retry 次数有界且按 side-effect class 决定；
- Provider、工具、文件系统和环境快照能支撑 replay。

### 判定

| 能力 | 当前状态 | 解释 |
|---|---|---|
| interrupt/resume control surface | `observed` | 仅表示 schema/API 存在 |
| durable agent state | `unknown` | ThreadItems 有损，不能承载完整副作用账 |
| C4 safe retry/reconcile | `unknown` | 必须由外层 ledger 与真实中断注入验证 |
| C4 候选状态 | `unknown`，可走 `composition-required` | 不能由 API 发现直接记 pass |

## 4. 最小 composition adapter 设计（下一步验证，不是产品设计）

若继续验证 Codex，adapter 只保留一个外部 durable owner：

1. 外部触发器生成 `schedule_id`、logical time、`idempotency_key`，并创建唯一
   `run_id`；每次触发都留下 attempt 记录。
2. adapter 创建/恢复 Codex thread，保存 `thread_id`、`turn_id`、Codex artifact
   identity、Prompt/Tool schema、Provider 和 sandbox 身份。
3. Codex 的 tool call 必须经过 W7 已通过的 C2 adapter；副作用 ledger、
   result ledger 和状态 checkpoint 由 adapter 持有，不依赖有损 ThreadItems。
4. 在工具前、工具后未提交、已提交未进入下一步、Provider/tool timeout 和
   process interrupt 注入故障；恢复时先 reconcile effect ledger，再决定
   retry、resume 或 safe-stop。
5. 只有当 C3 的同 key delivery 为 1、C4 的状态丢失/危险副作用重复为 0、
   retry 上界为 1 且所有原因可解释时，才可将结果记为
   `pass-with-composition`；否则保留 `unknown`。

该 adapter 不拥有第二份 agent loop、权限模型或观测后端。若必须引入
Temporal/LangGraph，需另做 CBAM：比较它们减少的 durable/schedule/retry 适配
工作与新增常驻服务、备份、升级、排障、迁移和退出成本；在比较完成前不引入。

## 5. ATAM / CBAM 结论

- `R-C3-01`：Codex 一次性执行入口与工作台定时语义之间存在缺口；责任暂归
  外部 schedule/idempotency adapter，不能隐式归给 Codex。
- `R-C4-01`：Codex resume API 与完整副作用恢复之间存在有损事件边界；需要
  adapter 自持 ledger，且在候选真实入口上做故障注入。
- `SP-C4-01`：`thread_id`/`turn_id`/rollout artifact 与外部 `run_id`、effect
  ledger 的关联；关联缺失时必须 fail-closed。
- `TP-C3/C4-01`：轻量单 owner adapter 与 Temporal/LangGraph 的 durable 能力
  对比；当前只能说 composition-required，不能说外部工作流组件值得引入。

## 6. 当前放行

本轮能力探针完成，但 `1-3` 不完成：

- C3 原生能力：`composition-required`；
- C4 控制面：`observed`，完整恢复：`unknown`；
- W6 C3/C4 fixture 证据继续保持候选无关；
- 下一步是运行一个只包住 Codex真实入口的薄 composition adapter，或在无法
  安全关联状态/副作用时输出 `stop`，不得生成“Codex C3/C4 通过”。
