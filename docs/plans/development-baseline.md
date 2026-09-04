# ZWorkbench 开发前基线

状态：`knowledge-baseline / target-state-approved / H1-H3 bounded bridge verified`<br>
日期：2026-09-04<br>
适用对象：个人开发者或小团队

本文是方案调研与准备阶段的收口摘要。它把“已经决定的目标”“当前代码真实状态”“仍然未知的验收门”和“正式开发的进入顺序”放在同一页，避免把历史评测结果误当成产品实现，也避免为了补齐已有 Harness 能力而从零重写全部运行时。

## 1. 现役目标决策

采用目标架构：

```text
DSH 主 Harness
  └─ Codex Coding Worker（进程外 bridge）
       └─ ZWorkbench CompositionOwner（唯一 durable source of truth）
```

目标职责如下：

| 层 | 负责 | 不负责 |
|---|---|---|
| DSH 主 Harness | 顶层 Agent loop、session、上下文、插件组合、任务拆解和个性化实验 | 跨 Run durable state、最终 effect、approval、Provider fallback ledger、replay safety |
| Codex Coding Worker | 代码理解、修改、测试、构建、lint、diff 和代码任务诊断 | parent Run、调度、最终权限、跨 Run state、真实主分支提交 |
| ZWorkbench Control Plane | 用户入口、preflight、父子运行编排、Worker 监督、workspace/artifact、Provider、Evidence/Replay 和退出 | 复制任一 Harness 的 Agent loop |
| CompositionOwner | run、attempt、event、effect、result、approval、reconcile、backup/restore、replay metadata 和 safe-stop | 执行 shell、模型请求或外部副作用 |
| Host / Provider / 账户 owner | OS 强制边界、凭证注入、远端数据/任务/Webhook/备份/retention/账单和账户退出 | 不把这些责任静默推回 ZWorkbench |

唯一 ownership 不变量：DSH session、插件 state、Codex thread/turn/rollout、Provider router state 和观测投影都只能是输入、缓存或 evidence，不能成为第二个 canonical owner。

## 2. 当前实现与目标态的分界

| 面 | 当前仓库真实状态 | 目标态要求 |
|---|---|---|
| 用户入口 | 已有可安装的 `zworkbench run` | 仍保留单一工作台入口，由 DSH 驱动顶层任务 |
| Harness | 实际运行路径是 Codex-only `local_read_only_run` | DSH 作为主 Harness，Codex 通过显式 Worker contract 接入 |
| durable state | 已有本地 SQLite CompositionOwner | 继续唯一持有 parent/child run、effect、result、replay 和 backup truth |
| Provider | 第一切片默认 fake/loopback；真实 Provider 仅有按需 staging 证据 | Provider profile、能力、attempt、fallback、降级原因由 ZWorkbench owner 记录 |
| Workspace/effect | 第一切片只读；真实写入和 host/native approval 仍 HOLD | 先隔离 worktree 生成 diff，再经 policy/approval/claim/reconcile 才能 apply |
| Replay | 已有 recorded view 和 cassette-only simulated replay 合同 | recorded/simulated/live 三种模式必须是不同入口，live 默认拒绝 |
| DSH bridge | H1–H2 owner-backed/fixture 与 H3 bounded read-only coding 已验证；H4–H5 pending | 继续验证生命周期和 evidence/replay；H3 的真实 runtime 范围仅为 Codex + loopback Provider |
| Scheduler | 未作为第一切片产品能力实现 | 后续由 ZWorkbench durable owner 持有 schedule/trigger/missed trigger/幂等 |
| 插件 | 已有隔离的 DSH plugin 研究和 adapter fixture，不代表默认 bundle 已采用 | allowlist、固定 source/version/commit/digest、权限声明和 dispose/rollback |

因此，当前代码可以作为安全回退和对照基线，但不能在 README、评测报告或 Agent 判断中被描述成目标混合架构已完成。

## 3. 已完成的准备工作

### 3.1 研究地图

- W2 核实了 DeepSeek Harness、Pi Agent 和 Codex 的对象身份、扩展面和成熟度边界。
- W3 将候选按层拆开：OpenHands/OpenCode/Goose 是执行型候选，SWE-agent/Aider 更像代码专长执行器，LangGraph/Temporal/LiteLLM/Langfuse/Phoenix/Inspect AI/OpenTelemetry 不是同层级的“全能基座”。
- W4 确认观测和评测后端可以复用为查询、实验和评分基础设施，但不能凭自身提供安全执行、确定性回放、副作用隔离、环境快照或 artifact lock。
- W6 固化了面向个人开发者/小团队的 C1–C7 fixture、阈值、ATAM 模板、CBAM 成本账和自动化持续评估协议。
- W7 完成了 Codex `0.139.0` 的组合式能力验证、CompositionOwner 第一切片、C7 人工操作记录和 NOTICE/退出边界审计；未闭合项仍保留为 unknown/HOLD。
- W8 完成了 `local_read_only_run` 产品入口和 DeepSeek 公平挑战；插件生态证明“有供给”，但没有单一插件被证明能关闭 E4 的 durable fallback/degradation ledger 与全冷却 fail-closed 门。

### 3.2 已落盘的决策

1. 不从零重写 Agent loop；优先复用 DSH 的插件化运行时和 Codex 的代码 Worker 能力。
2. 不把 DSH 与 Codex 内部 session/database 直接拼成一个事实源；用进程外 bridge 和结构化 parent/child contract 连接。
3. 不一开始引入全量插件市场、第二长期运行时、Temporal/LangGraph/LiteLLM、独立观测平台、常驻 gateway 或消息队列。
4. 先做一个最小混合只读切片；每次只加入一个 allowlisted plugin；每项增量必须经过 ATAM/CBAM 和受影响的回归门。
5. 真实 Provider、真实凭证、真实主工作区、Git push、部署、Webhook 和远端资源退出都是独立 gate，不是第一切片的隐含依赖。

## 4. 仍然有效的硬门

下列规则不是“以后再补的质量优化”，而是目标架构的放行条件：

- CompositionOwner 是唯一 durable owner；关键 identity 不能关联时保持 `unknown` / `safe-stop`。
- 所有 effect 经过 `request → policy → decision → claim → execute → complete/reconcile`；未知 effect 不执行，外部结果不确定时先 reconcile。
- Provider 不允许静默切换；每次 attempt、failure class、fallback target、degradation reason 和 provider/model identity 都要记录。
- Worker 的取消、超时、崩溃和 parent stop 必须能清理完整进程树；无孤儿 Worker。
- 生成 diff 与应用 diff 是两个动作；默认使用只读 workspace 或隔离 worktree，应用需要显式 approval 和可恢复 receipt。
- `recorded_view` 只读保存事实；`simulated_replay` 只消费封存 fixture/cassette；`live_replay` 默认拒绝。
- 插件固定 source/version/commit/digest，声明 capability/permission，且 install、enable、disable、dispose、migrate、rollback 可观察；卸载不能破坏 owner state。
- key/token/cookie/生产数据和原始 Provider 响应不进入 prompt、argv、日志、owner、backup、cassette、artifact 或 git。
- 常驻人工维护服务目标不超过 3 个；新增长期服务、第二 Harness 或外部基础设施必须重新做 CBAM。
- 版本、schema、插件、Provider、policy、fixture 或服务拓扑变化时，受影响验证必须重新运行，不能继承旧证据。

## 5. 正式开发的进入顺序

这里的顺序是开发入口，不是当前任务中立即实现的代码清单。

### Stage 0：冻结混合边界

固定 DSH core/profile、最小插件 allowlist、Codex Worker artifact、app-server/CLI schema、依赖、Provider profile、policy digest、owner schema 和 fixture identity。定义 bridge 的 parent/child run、事件 envelope、错误分类、取消、超时、退出码和未知消息语义。

完成条件：合同和 identity 字段可审查；没有第二 owner；Codex-only 回退链和回滚动作可执行；所有未决项被标成 pending/unknown/HOLD。

### Stage 1：H1–H5 混合只读切片

1. H1 Bootstrap：启动固定 DSH profile 和一个 allowlisted coding bridge。
2. H2 Handshake：完成 DSH → bridge → Codex 的版本、schema、session/thread/turn 握手。
3. H3 Read-only coding：在 case-local workspace 或隔离 worktree 中读取代码、运行测试、生成可审查 diff，不应用修改。
4. H4 Lifecycle：验证 cancel、timeout、child crash、parent stop、restart、进程树和状态恢复。
5. H5 Evidence/replay：记录 DSH、插件、Worker、Provider、artifact 和 owner 事件，且 recorded/simulated/live 模式隔离。

H1–H5 的共同硬门是：父子 identity 完整率 100%、未授权 effect 为 0、孤儿 Worker 为 0、关键状态丢失为 0、replay 不启动外部执行、未知 wire/capability/effect 立即 safe-stop。

### Stage 2：单插件与 Provider 实验

先做 H6 插件生命周期，每次只引入一个插件；再做 H7 双 loopback Provider 的能力协商、失败分类、fallback、降级、全冷却停止和 durable ledger。真实 Ark staging 只能证明单 Provider 连通性和 identity，不能代替 H7。

### Stage 3：可恢复本地写入

只有在 L2 Harness approval、L3 host enforcement、进程树、claim/commit/reconcile、幂等、backup/restore 和 rollback 证据完整后，才讨论隔离 worktree 的 approved apply。真实主工作区、Git push、部署和远端 effect 另开 gate。

### Stage 4：受控个人试点

固定一个操作者和有限项目，启用少量已通过生命周期、成本、许可证和退出审查的插件；持续运行版本/依赖/Provider/policy/fixture 变化后的回归。没有 C7 和远端责任证据时，不扩大到团队共享或生产分发。

## 6. 当前不应继续循环的事项

- DeepSeek E4/E5/E6 的未知项继续作为独立 acceptance/evaluation 记录；它们不再阻塞 H1–H5 混合只读架构实验，但也不能被标成通过。
- 真实 Provider 的 API key 交接、账户数据和远端退出不进入产品 roadmap；需要时使用独立本地 wizard，文档只保留脱敏 summary。
- `1-6-3` 的 host/native approval 仍是写入 gate；不要因为 Codex adapter 的 scripted pass 或已有 owner 证据而重复打开无边界的“全平台安全”循环。
- 新的 DSH 插件只有在明确补充非重复能力、成本可接受、可固定 provenance、可 dispose/rollback 且不夺取 owner 时才进入候选。

## 7. 文档和证据状态

| 事实面 | 状态 | 依据 |
|---|---|---|
| 目标设计 | `changed-and-verified` | [目标架构设计](designs/dsh-codex-hybrid-target-architecture.md) 与 2026-09-03 roadmap decision |
| 当前代码 | `verified-current` | [`README.md`](../../README.md)、`src/zworkbench/`、产品测试 |
| 当前运行态 | `pending / not-applicable` | 本地 CLI 有隔离 smoke；没有部署/live production surface |
| 研究结论 | `verified-current`（以固定来源/commit 为限） | W2–W8 findings 与 research metadata |
| DSH 混合 bridge | `H1–H3 bounded verified / H4–H5 pending` | H1 clean pinned artifact、H2 owner-backed handshake、H3 fixture 与 real-Codex-runtime + loopback Provider 已运行；真实远程 Provider、生命周期和 evidence/replay 仍未通过 |
| 宿主强制写入 | `HOLD / unknown` | `1-6-3` |
| 真实 Provider 远端退出 | `externally-delegated / signoff-open` | C7 remote exit responsibility |
| 机器生成 evidence | `generated-read-only / local evidence` | `evaluation/evidence`、`evaluation/runs` |
| 长期记忆 | `not-applicable` | 本次不写 Codex/其他 Agent 生成记忆 |

本基线完成的是知识收口，不是产品完成。下一次产品开发任务应从 H4 生命周期/恢复的最小
bridge contract 开始，并首先重新读取 [目标架构设计](designs/dsh-codex-hybrid-target-architecture.md) 与本文件。
