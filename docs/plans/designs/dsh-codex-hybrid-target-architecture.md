# ZWorkbench 目标系统架构：DSH 主 Harness + Codex Coding Worker

状态：`target-state / approved-for-implementation-planning` · 路线：Product execution · 日期：2026-09-03

本文描述 ZWorkbench 下一阶段应该落地的目标架构，不是当前代码仓库的现状盘点，也不是 DSH、Codex 或任何 Provider 的生产安全承诺。当前仓库已有的 Codex-only local_read_only_run、CompositionOwner 和评测资产是实现起点与回退基线；它们不能被解释为目标混合架构已经完成。

## One-page overview

### Decision

Decision: approve 进入目标架构的实现规划；生产采用 defer。

采用的目标组合是：

> DSH 作为主 Harness，负责顶层 Agent loop、插件组合、任务路由和个性化运行时实验；Codex
> 作为 Coding Worker，负责高质量代码理解、修改、测试和代码任务执行；ZWorkbench
> CompositionOwner 继续作为唯一 durable owner，负责运行状态、权限、副作用、回放、备份和退出。

本决策批准的是目标架构和最小纵向切片，不批准真实写操作、真实 Provider 默认接入、完整插件市场或生产发布。未关闭的 C2/C4/C7 硬门属于 blocking；不影响只读实验、但影响扩展规模的事项属于 non-blocking。

### Summary

ZWorkbench 不从零重写 Agent loop，也不把 DSH 和 Codex 的内部状态直接拼接。DSH 通过受控的 Coding Worker bridge 调用进程外 Codex；所有父子运行、工具请求、Provider 尝试、文件变更和副作用都通过 ZWorkbench 的统一 owner contract 关联和审计。这样保留 DSH 快速试错、插件化定制的上限，同时保留 Codex 在代码任务上的成熟执行能力和可回退性。

### Platforms and scope

目标环境是个人开发者或小团队使用的本地优先工作台：

- DSH：固定版本、固定 commit、固定插件清单和依赖锁定的主 Harness；
- Codex：固定版本的 app-server/CLI Coding Worker，初始沿用已验证的 0.139.0 作为回退基线，混合接入时必须重新绑定实际 artifact；
- ZWorkbench：本地 Control Plane、SQLite CompositionOwner、Worker Supervisor、Provider Adapter、Evidence/Replay Store；
- 项目：每个 Run 使用显式 workspace，代码 Worker 默认使用隔离 worktree；
- Provider：开发和评测默认 loopback/fake Provider；真实 Provider 是显式、隔离、按需的外部验证；
- 常驻人工维护服务：目标不超过 3 个；Codex Worker 为按 Run 启动的子进程，不作为第二个常驻平台服务计数，但其生命周期必须纳入 owner。

明确排除：

- 一开始就兼容整个 DSH 插件生态；
- 一开始就引入第二个长期运行时、Temporal/LangGraph/LiteLLM 或独立观测平台；
- DSH 与 Codex 各自维护一份跨 Run 的 canonical state；
- 真实写入、Git push、部署、Webhook、远程工作区和不可逆外部副作用；
- 以插件 README、接口存在或单次真实 Provider 成功请求替代端到端验收。

### Ownership and tracking

| 责任面 | 唯一 owner | 目标边界 |
|---|---|---|
| 顶层对话、意图理解、运行时插件组合 | DSH 主 Harness | 可以改变 Agent loop 的组织方式，但不能绕过 ZWorkbench policy/effect seam |
| 代码理解、代码修改、测试执行 | Codex Coding Worker | 只接受 Worker contract；不拥有父 Run、调度、审批或跨 Run durable truth |
| Run、Attempt、Event、Effect、Result、Replay metadata | ZWorkbench CompositionOwner | 唯一 durable source of truth；SQLite 为第一阶段实现 |
| 调度、重试预算、恢复和 safe-stop | ZWorkbench Control Plane + CompositionOwner | DSH session-local 机制只能提供建议或投影，不能成为唯一调度事实 |
| 权限、审批、凭证引用和副作用提交 | ZWorkbench Policy/Effect Owner + Host boundary | 未知边界必须 deny/safe-stop；模型和插件不能自行提交副作用 |
| Provider profile、选择、fallback、降级原因 | ZWorkbench Provider Owner | 每次选择和切换必须可解释、可记录，禁止 silent switch |
| 事件、日志、cassette、评测结果 | ZWorkbench Evidence/Replay Owner | Harness 日志只能作为输入或投影，不能自动成为 replay truth |
| DSH 插件 ABI、manifest、生命周期 | DSH Plugin Host + ZWorkbench Plugin Registry | 固定版本、allowlist、依赖与退出记录；插件不能直接写 owner DB |
| 真实 Provider 账户和远端资源 | 账户 owner / Provider | ZWorkbench 只记录脱敏 identity 和责任边界，不承诺删除远端任务、Webhook 或备份 |

## Problem and goals

### User/job and target outcome

ZWorkbench 要成为个人开发者或小团队的个人工作台，支持：

1. 完成代码和通用任务；
2. 自动任务与定时任务；
3. 集成个人开发项目；
4. 观测、回放、评测、调试和排障；
5. 多家 LLM Provider；
6. 尽可能强的代码开发能力；
7. 在新模型、新工具和新 Agent 技术出现时，可以快速试错和替换局部能力。

目标状态不是拥有最多功能的单体 Agent，而是一个有清晰控制面的可组合工作台：运行时可以快速变化，但 durable state、权限、副作用、证据和退出责任不能随插件组合而漂移。

### Why this architecture

前期研究形成了三个有约束的判断：

- DSH 的主要优势是运行时可重组：插件可以参与 Agent loop、上下文、路由、记忆、配置和生命周期实验；其代价是 alpha ABI、插件依赖、事件顺序、状态 ownership 和升级风险；
- Codex 的主要优势是成熟的代码 Agent 执行能力和可使用的 app-server/CLI/外部集成面；其官方扩展边界更适合 Skills、Plugins、MCP、Hooks 和外部 adapter，不宜假设可以任意替换内部 Agent loop；
- ZWorkbench 已经需要独立的 CompositionOwner 来补充跨 Run 的状态、幂等、副作用、回放和 backup/restore 语义；这一责任不应重新交给 DSH 或 Codex。

因此，目标架构将“快速改变运行时”和“稳定持有事实”拆成不同层：

~~~text
                  个性化运行时 / 新能力实验
                               │
                               ▼
                   ┌─────────────────────┐
                   │ DSH 主 Harness       │
                   │ Agent loop / plugins │
                   │ session / routing    │
                   └──────────┬──────────┘
                              │ Coding Worker contract
                              ▼
                   ┌─────────────────────┐
                   │ Codex Coding Worker  │
                   │ code / test / diff   │
                   │ app-server / CLI     │
                   └──────────┬──────────┘
                              │ controlled effects
                              ▼
┌──────────────────────────────────────────────────────────┐
│ ZWorkbench Control Plane                                 │
│ CompositionOwner · Policy/Approval · Provider · Evidence │
│ Scheduler · Worker Supervisor · Workspace/Artifact       │
└──────────────────────────────────────────────────────────┘
                              │
              local workspace / isolated worktree / Provider
~~~

### Goals

- 让 DSH 成为可试错、可替换、可扩展的主运行时；
- 复用 Codex 的代码 Agent 能力，而不是重新实现代码执行引擎；
- 保持一个唯一的 durable owner；
- 统一父任务、子 Worker、Provider、工具、artifact 和 effect 的身份关联；
- 让插件和 Worker 通过窄而深的 contract 扩展，不直接共享内部数据库；
- 在不改变主线的情况下，逐步加入 scheduler、memory、Provider、观测和代码写入；
- 允许某个插件或 Worker 独立禁用、回滚和退出；
- 满足个人开发者或小团队的部署、排障、升级和维护约束。

### Non-goals

- 不在本设计中证明 DSH 的 sandbox 或 Codex native approval 已达到生产级；
- 不实现通用多租户平台、团队权限系统或 SaaS 控制面；
- 不把 DSH 的所有插件都纳入默认安装；
- 不把 DSH、Codex、Pi 或其他 Harness 的 session 文件直接互相解释；
- 不在没有真实需求和验收证据时引入常驻 gateway、消息队列或外部数据库；
- 不以 Provider 数量或 GitHub 插件数量作为架构成功标准。

### Assumptions and constraints

- 个人开发者或小团队是首要用户，单一操作者必须能够完成安装、升级、备份、恢复和排障；
- 本地优先、case/workspace 隔离、最小权限和 fail-closed 优先于功能数量；
- DSH 处于快速演进阶段，所有插件和 DSH core 必须绑定版本、commit、依赖和 artifact digest；
- Codex 是可替换的 Worker，不是 ZWorkbench 的 canonical state owner；
- pass-with-composition 只证明 owner + adapter 组合合同，不升级为 Harness native pass；
- 任意未知的权限、effect、Provider、事件或进程状态都不能被当作成功；
- 第一阶段保留 Codex-only 路径作为回退，不做不可逆迁移。

### Success definition

目标架构达到可以进入受控个人试点的条件，需要同时满足：

- 至少一条 DSH → Codex Worker → owner 的只读代码任务闭环；
- 父子身份关联完整，关键事件、结果和 artifact 可查询；
- Worker 取消、超时、崩溃和父任务 safe-stop 后不存在孤儿进程；
- 任何未授权 effect 为 0，同一 idempotency key 的重复物理 effect 为 0；
- replay 不会重新启动 Worker、Provider 或工具；
- Provider 选择、失败分类、fallback 和降级原因可审计；
- 插件可以禁用、卸载或回滚，不破坏 owner canonical state；
- 首次安装不超过 90 分钟，升级/backup/restore/预制故障定位各不超过 30 分钟；
- 常驻人工维护服务不超过 3 个，不需要额外专家；
- C2/C4/C7 的关键未知仍保持 HOLD，不会被只读实验结果掩盖。

## Design

### 1. 分层与模块

#### 1.1 ZWorkbench Entry/Control Plane

Control Plane 是用户和两个 Harness 之间的产品控制面，职责包括：

- 接收用户任务并创建顶层 run_id；
- 选择 DSH profile 和允许的插件清单；
- 执行 preflight，绑定 workspace、Provider profile、policy 和环境 identity；
- 启动、停止、恢复和观察 DSH 主进程；
- 向 DSH 注入本次 Run 的 capability context，而不是注入全局权限；
- 管理 Worker、artifact、diff、测试结果和退出状态；
- 提供 recorded view、simulated replay、export、backup/restore 和诊断入口。

Control Plane 不复制 DSH 的 Agent loop，也不直接生成模型文本；它只负责产品级编排、事实持有和安全边界。

#### 1.2 DSH Main Harness

DSH 是主 Harness，面向未来个性化和快速试错。它负责：

- 顶层 Agent loop 和用户交互；
- session、上下文拼装和任务拆解；
- 插件 profile 的组合、启用、禁用和实验 feature flag；
- 将通用任务、代码任务、记忆任务、Provider 选择建议路由到相应能力；
- 将 DSH 原生事件和插件事件通过 event adapter 送入 ZWorkbench；
- 请求 Coding Worker，而不是自行复制一套代码执行产品；
- 将 Worker 的结构化结果解释给用户，并保留原始 artifact 引用。

DSH 可以拥有 session-local 的临时状态，但不能成为以下跨 Run 事实的唯一 owner：

- run 生命周期；
- effect claim/commit/reconcile；
- approval token；
- Provider fallback/degradation ledger；
- replay mode 和 replay safety；
- backup/restore manifest；
- 退出和资源撤销清单。

#### 1.3 DSH Plugin Host / Plugin Registry

插件是 DSH 的主要个性化扩展面。ZWorkbench 需要在 DSH 原生插件机制外增加一个受控注册层，至少记录：

| 字段 | 作用 |
|---|---|
| plugin_id / plugin_version | 稳定识别和升级回滚 |
| dsh_target / abi_version | 防止 alpha 版本静默加载失效 |
| source commit / package digest | 建立 provenance |
| declared capabilities | 说明插件能请求什么 |
| requested permissions | 文件、网络、凭证、子进程、UI 等权限 |
| dependency lock | 固定依赖树和安装来源 |
| lifecycle hooks | install、enable、disable、dispose、migrate、rollback |
| owner-state policy | 明确插件只能读 projection，还是可以申请 owner mutation |
| license/NOTICE references | 支持退出和发布审计 |

插件必须通过 Host Capability Facade 访问 ZWorkbench 能力。默认禁止：

- 直接打开 CompositionOwner SQLite；
- 直接修改 owner 的 event/effect/result 表；
- 自行启动未声明的网络、shell 或远程连接；
- 以 full access 声明覆盖宿主 policy；
- 未经 owner 关联地执行 Provider 请求或外部 effect。

首批插件采用 allowlist、固定版本、一次加入一个的策略。dsh-context、dsh-memoir、dsh-routing-suite、dsh-config-migrate 可以作为候选扩展，但存在候选不等于已进入默认 bundle；每一个都必须经过独立 E1–E6 和小团队成本门槛。

#### 1.4 DSH–Codex Coding Worker Bridge

这是目标架构的核心新 seam。它把 Codex 暴露成 DSH 可调用的代码能力，而不是让 DSH 直接依赖 Codex 内部实现。

Bridge 的职责：

- 接受 DSH 的结构化 coding request；
- 将父 Run、workspace、policy、Provider profile 和预算绑定到 child Run；
- 启动固定 Codex app-server/CLI，优先采用显式 argv/env 和进程外隔离；
- 完成握手，确认 Codex release、schema、adapter 和 capability identity；
- 转发经过允许列表的 request/event/result；
- 对工具请求调用 ZWorkbench policy/effect seam；
- 监控 heartbeat、超时、取消、退出码和进程树；
- 将 diff、测试结果、日志和模型结果写为带 digest 的 artifact；
- 在完成、失败、未知或 safe-stop 时向 owner 提交结构化状态。

Bridge 不拥有：

- 顶层会话；
- 任务调度；
- approval token 的最终语义；
- Provider fallback/degradation 的最终决定；
- owner database；
- 真实 workspace 的不可逆合并。

初始传输优先选择 Codex 已有的 app-server/CLI 受控接口；如果未来增加 ACP 或其他协议，它们只是 transport/interop seam，不能成为第二套 state/effect/permission truth。

#### 1.5 Codex Coding Worker

Codex Worker 专注代码任务：

- 读取工作区和项目上下文；
- 分析代码、提出修改；
- 在隔离 worktree 或受控 workspace 中执行代码工具；
- 运行测试、静态检查和构建；
- 返回结构化 diff、测试摘要、诊断和建议；
- 响应 cancel、timeout 和 shutdown。

Worker 的默认输出是可审查 artifact，而不是直接提交到用户主分支。目标分阶段支持：

1. read_only_analysis：只读分析和测试探针；
2. isolated_edit：隔离 worktree 中产生 diff；
3. approved_apply：经过 owner approval、effect claim、可恢复提交后才允许应用；
4. commit/push/deploy：另开安全和退出门，不属于首个混合切片。

Codex 内部 thread/turn/rollout 可以作为 evidence，但必须通过 adapter 投影到 owner 的 canonical identity；不能直接把 CODEX_HOME 或 Codex session 文件当作工作台状态。

#### 1.6 CompositionOwner

CompositionOwner 是整个混合架构的稳定核心。它不执行模型、shell 或 Provider，而是记录并约束执行的生命周期：

~~~text
run
  → attempt
    → dsh session/turn
      → worker run
        → codex thread/turn
          → event / provider attempt / tool request
            → effect claim → complete | uncertain | reconcile | safe-stop
~~~

Canonical identity 至少包括：

~~~text
run_id
parent_run_id
attempt_id
dsh_session_id
dsh_turn_id
worker_run_id
codex_thread_id
codex_turn_id
event_id
effect_id
artifact_id
provider_identity
replay_mode
policy_digest
environment_digest
~~~

部分 Harness 不暴露的字段必须显式记录为 unknown，不能填入猜测值。关键 identity 无法关联时，Run 不能完成，必须进入 failed 或 safe_stopped。

Owner 继续提供以下语义：

- 唯一 Run 生命周期；
- approval-required effect 的一次性授权；
- idempotency key 去重；
- uncertain effect reconcile；
- bounded retry；
- Provider attempt/fallback/degradation ledger；
- event/result/artifact metadata；
- recorded_view、simulated_replay、live_replay 模式隔离；
- backup/restore 和 state digest；
- safe-stop 和退出清单。

#### 1.7 Provider Owner / Adapter

Provider 适配需要分为三个层次：

1. ProviderProfile：Provider、model、endpoint、region、能力和认证引用；
2. ProviderAdapter：把请求和响应映射到统一事件结构；
3. ProviderPolicy/Router：选择、失败分类、retry、fallback、degradation 和预算。

DSH 可以提出希望使用某 Provider 的路由意图，最终选择必须经 ZWorkbench policy，并写入：

~~~text
provider_id
model
endpoint
capability_snapshot
attempt_id
failure_class
fallback_target
degradation_reason
~~~

禁止把 Provider retry 直接叫作 failover，也禁止因为响应中的模型别名变化就推断发生了切换。真实 API key 只由本地环境或凭证工具注入；owner、日志、backup、replay cassette 和插件输出只保留引用或 fingerprint。

#### 1.8 Workspace / Artifact Manager

Workspace Manager 负责项目边界，不承担 Agent loop：

- 验证 workspace 位于允许的项目根或 case root；
- 为 Coding Worker 创建和销毁隔离 worktree；
- 计算 workspace、依赖、工具链和 diff digest；
- 保存 patch、测试结果、诊断、日志和环境清单；
- 将 apply/merge/commit 变成显式 effect；
- 在未批准或状态未知时拒绝合并。

首阶段不直接修改用户的真实主工作区。即使 Codex 生成了正确 diff，也必须将生成 diff和应用 diff作为两个不同的状态和权限动作。

#### 1.9 Evidence / Replay / Evaluation

Evidence Store 以 append-only event ledger 和 artifact manifest 为基础，统一记录 DSH、插件、Bridge、Codex、Provider 和 Owner 的事件。

三种模式必须严格分离：

| 模式 | 行为 | 外部执行 |
|---|---|---:|
| recorded_view | 查看已保存事件、结果和状态投影 | 0 |
| simulated_replay | 使用封存 cassette/fixture 重演逻辑，不启动真实 Worker/Provider/tool | 0 |
| live_replay | 重新连接真实 Worker/Provider/工具 | 默认拒绝，需独立批准 |

回放至少要绑定 DSH profile、插件清单、Codex artifact、Provider identity、tool schema、policy digest、workspace/environment digest、owner schema 和 cassette identity。缺少任何关键字段时保持 unknown，不称为可复现。

#### 1.10 Scheduler / Automation

自动任务由 ZWorkbench durable scheduler 持有：

- schedule、trigger、missed trigger、pause/resume 和 idempotency key 存入 owner；
- DSH 可以为任务提供计划建议或执行策略，但不能依赖一个常驻 live session 才能触发；
- scheduler 只启动经过 preflight 的 parent Run；
- Worker 和 Provider retry 受 owner 的 attempt budget 约束；
- 未知 effect、失联 Worker、权限状态不明时停止而不是自动重跑。

第一阶段可以只实现手动 trigger，但数据模型从一开始预留 durable trigger，不把未来 scheduler 偷偷塞进 DSH session。

### 2. 端到端运行流

#### 2.1 只读 Coding Run

~~~text
用户提交代码任务
  → Control Plane 创建 parent run_id
  → preflight workspace / DSH profile / plugin allowlist / Provider profile
  → 启动 DSH session，绑定 parent_run_id
  → DSH 判断任务属于 coding
  → dsh-codex-coding-worker 创建 child run
  → Worker Supervisor 启动固定 Codex
  → Codex handshake：release/schema/thread/turn
  → Codex 读取隔离 workspace、运行测试、生成 diff/artifact
  → 每个 event/tool/provider 请求关联 owner
  → owner 检查 policy；只读动作继续，未知动作 safe-stop
  → Worker 返回结果并退出
  → owner 写入 semantic result 和 artifact manifest
  → DSH 汇总结果，parent run completed
  → 用户查看结果、diff、测试和 recorded view
~~~

#### 2.2 中断和恢复

~~~text
cancel/timeout/process loss
  → Control Plane 标记 parent/child recovering
  → Supervisor 先停止 DSH/Worker 进程树
  → owner 查询最后一个 event/effect checkpoint
  → 已完成 effect：记录 receipt，不重复执行
  → 未执行 effect：按 owner 预算允许一次 retry
  → 无法判断 effect：unknown + safe-stop，等待人工 reconcile
  → 可恢复的 DSH/Codex session：使用已记录 identity 尝试 resume
  → 无法关联 identity：停止，不伪造完成
~~~

#### 2.3 Provider 故障

~~~text
Provider request
  → ProviderPolicy capability check
  → primary attempt
  → classify timeout / stream interruption / capability missing / rate limit
  → retry or fallback decision recorded
  → if fallback: record target + reason + degradation
  → if all routes unavailable: no new route selection, safe-stop or explicit failure
  → DSH receives semantic result + provider ledger, never silent model change
~~~

#### 2.4 插件生命周期

~~~text
discover
  → source/commit/license/dependency verification
  → manifest + capability/permission review
  → install in isolated profile
  → enable with feature flag
  → health/dispose/leak checks
  → one-scenario evaluation
  → promote / keep experimental / disable / rollback / uninstall
~~~

插件配置迁移和 CompositionOwner backup/restore 是两个不同动作。插件可以导出自己的 profile state，但不能声称已经备份了 ZWorkbench 的 run/effect/replay state。

### 3. 状态模型与不变量

#### 3.1 Parent/child state

Parent Run 的完成条件包括：

- DSH session/turn 状态可解释；
- 所有 child Worker 已完成、失败或安全停止；
- 所有关键 event 和 artifact identity 已关联；
- 没有 unresolved effect；
- semantic result 已由 owner 写入。

Child Worker 的 completed 只表示 Codex Worker 完成其 contract，不表示 Parent Run 已完成，也不表示 diff 已应用。

#### 3.2 Effect 不变量

- 未知 effect class 直接 deny，并将 parent/child 标为 safe-stop；
- approval-required 必须有精确 operation、resource、idempotency key 和一次性 token；
- 同一 idempotency key 的已完成 effect 不再次产生物理动作；
- uncertain 先 reconcile，不能盲目 retry；
- 未批准的 live replay 不得执行 Worker、Provider 或外部工具；
- Worker 不能通过输出“成功”绕过 effect ledger。

#### 3.3 Plugin 不变量

- 插件权限声明不能扩大宿主 policy；
- 插件 dispose 后 RPC、工具、UI、style 和后台任务都必须归零或有可解释的残留；
- 插件状态只能通过 versioned migration 迁移；
- 插件卸载不能删除 owner canonical state；
- 插件故障不能让 DSH 静默改变 Provider、工具或重试语义。

### 4. 扩展面设计

目标架构保留四类扩展面，每类都有独立 owner：

| 扩展面 | 适合放什么 | 不允许放什么 |
|---|---|---|
| DSH Plugin | Agent loop、上下文、记忆、任务路由、UI、会话策略 | 直接改 owner DB、绕过 policy、隐藏 Provider switch |
| Coding Worker | 代码理解、修改、测试、构建、lint、diff | 顶层 scheduler、账户管理、跨 Run state |
| Provider Adapter | API 协议、能力声明、失败分类、fallback | 工具权限、workspace 写入、回放执行 |
| ZWorkbench Control Extension | scheduler、owner projection、评测、诊断、退出 | 复制 DSH/Codex 内部 loop |

扩展 API 的设计原则是少量入口 + 深层语义：

- submit_run
- request_worker
- report_event
- request_capability
- claim_effect
- complete_or_reconcile_effect
- record_artifact
- request_replay
- disable_or_safe_stop

未来可以增加实现，但不应让每个插件直接接触 SQLite 表、Provider client 或 OS 进程。

### 5. 安全与信任边界

~~~text
不可信 Prompt / Model output
          ↓
DSH 主 Harness + 第三方插件
          ↓ 受控 capability facade
ZWorkbench policy / owner / supervisor
          ↓ 显式 claim + approval
Codex Worker process
          ↓ host sandbox / worktree / credential reference
本地项目 / Provider / 外部 effect
~~~

需要分别验证的安全层：

- L1：ZWorkbench policy/adapter 是否在动作前拒绝；
- L2：DSH/Codex 的原生 approval/request/response 是否可观察且能关联；
- L3：OS/host sandbox、进程树、网络和凭证边界是否实际强制。

L1 通过不能替代 L2/L3。任何一层不可观察，都不能进入真实写操作。特别是：

- DSH 插件的 full-access 声明不是安全证明；
- path anonymizer 或日志脱敏不是 sandbox；
- Codex Worker 被 DSH 启动不代表 DSH 已接管 Codex 的所有子进程权限；
- Provider API 兼容不代表数据、账单、retention、Webhook 或远端退出责任由 ZWorkbench 拥有。

### 6. 部署与运维形态

首个目标部署是单机、单用户、按 Run 启动 Worker：

~~~text
常驻/主进程：
  1. ZWorkbench Control Plane + CompositionOwner
  2. DSH 主 Harness（可由 Control Plane 管理）
  3. 可选 scheduler（若不内嵌在 Control Plane）

按 Run 临时进程：
  - Codex Coding Worker
  - fake/real Provider client 或受控 adapter
  - 外部工具 helper（只在声明和批准后存在）
~~~

目标不是追求进程越少越好，而是让每个进程都有明确 owner、生命周期和退出动作。常驻服务超过 3、引入 Redis/Postgres/对象存储或增加第二长期运行时，都必须重新进行 CBAM。

诊断入口必须能从一个 run_id 导出：

- DSH profile/plugin identity；
- parent/child run 和 session/thread/turn 关联；
- Worker argv/env 的脱敏摘要；
- event timeline；
- Provider attempts/fallback/degradation；
- artifact/diff/test digest；
- effect/approval/reconcile 状态；
- process exit/cancel/timeout 原因；
- owner snapshot、backup identity 和 replay mode。

### 7. Alternatives / 方案比较

| 方案 | 优势 | 主要代价 | 决策 |
|---|---|---|---|
| Codex 主 Harness + owner | 当前证据最多，代码任务路径短，维护面小 | 运行时深度定制主要依赖外部 adapter；插件实验上限较低 | 保留为回退和第一阶段基线 |
| DSH 主 Harness + Codex Worker | DSH 定制上限高；Codex 保留代码能力；Worker 可替换 | 两个 loop、父子状态、进程树、权限和回放需要统一 | 选为目标架构 |
| DSH + Codex 进程内深度嵌入 | 低传输开销，调用表面可能更直接 | 强耦合、ABI/权限污染、崩溃和升级影响面大；当前未证明可行 | 不作为第一实现 |
| DSH + Codex + Pi 等多个 Worker 同时落地 | 选择空间最大 | 多个 adapter、状态、Provider、评测和退出矩阵；小团队成本高 | 后置 |
| 从零自建 Agent loop | 控制权最大 | 重复实现工具、代码能力、安全、状态、回放和生态 | 排除 |

选择 DSH + Codex Worker，不是因为它功能数量最多，而是因为它在运行时创新和代码能力复用之间提供了更好的长期结构；代价是必须把父子关系和 ownership 作为第一批基础设施实现。

## Metrics and experiments

### Success and regression metrics

| 指标 | 当前 baseline | 单位/采集方法 | 目标/阈值 | owner |
|---|---|---|---|---|
| 父子身份关联 | Codex-only 有 run/thread/turn 关联；DSH→Codex 未测 | 固定只读 fixture 检查 owner ledger | 必需字段完整率 100% | adapter/owner |
| 未授权副作用 | 首阶段目标为 0 | effect guard + host probe | 0 | policy/host |
| 重复物理副作用 | owner fixture 目标为 0 | 同 key 重复触发三次 | 额外副作用 0 | composition owner |
| 孤儿 Worker 进程 | 混合架构未测 | cancel/kill/timeout 后扫描进程树 | 0 | worker supervisor |
| 状态丢失 | owner-backed fixture 目标为 0 | 六个故障注入点后恢复/stop 检查 | 0 | composition owner |
| Provider switch 可解释性 | Codex-only 外部 router 已有记录；DSH Worker 未测 | 检查 attempt、target、reason、degradation ledger | 记录率 100%；silent switch 0 | Provider owner |
| replay 外部执行 | simulated replay fixture 目标为 0 | provider/tool/process tripwire | 0 | replay owner |
| 只读语义一致性 | Codex C1 fixture 为已知基线 | 同一任务比较 semantic result、diff、test | 共同 fixture 语义一致率 100% | evaluation owner |
| 首次安装 | Codex 有人工计时；混合架构未测 | fresh isolated install stopwatch | ≤90 分钟 | operations owner |
| 升级/恢复/诊断 | 混合架构未测 | 人工 stopwatch + machine evidence | 各 ≤30 分钟 | operations owner |
| 常驻服务 | 当前目标上限 3 | service manifest + fresh install | ≤3 | maintainer |

机器耗时与人工运维分钟数分开记录；任何性能收益都不能抵消安全、恢复、退出硬门。

指标记录统一包含 baseline、unit、method、target/threshold 和 owner；若 baseline 尚未测量，明确写为未测量，不用估算值代替。

### Minimum experiments

| 实验 | 内容 | 通过后解锁 |
|---|---|---|
| H1 Bootstrap | 固定 DSH profile 启动一次 parent Run，并加载 allowlisted coding bridge | 可以进入混合架构运行测试 |
| H2 Worker handshake | DSH→Bridge→Codex 完成版本、schema、session/thread/turn 握手 | 可以验证父子 identity contract |
| H3 Read-only coding | Codex 在隔离 worktree 读取代码、运行测试、生成 diff，不应用修改 | 可以验证最小产品纵向切片 |
| H4 Lifecycle | cancel、timeout、child crash、parent stop、restart，确认无孤儿进程和状态丢失 | 可以进入恢复/副作用实验 |
| H5 Evidence/replay | 记录 DSH、Worker、Provider、artifact 和 owner 事件；recorded/simulated/live 模式隔离 | 可以进入评测和调试使用 |
| H6 Plugin lifecycle | 一个 DSH plugin 安装、启用、dispose、禁用、回滚、卸载 | 可以开始单插件实验 |
| H7 Provider | 两个 loopback Provider 的选择、失败分类、fallback、全冷却停止和 ledger | 可以讨论多 Provider 产品化 |
| H8 Reversible write | 隔离 worktree 的 approved apply、幂等、恢复、rollback | 可以讨论真实本地写入 |

H1–H6 是首个混合只读切片；H7–H8 不能被首切片默认带入。

## Rollout, recovery, and lifecycle

### Rollout stages

#### Stage 0：冻结目标合同

- 固定 DSH core、profile、plugin manifest、source commit 和依赖；
- 固定 Codex Worker artifact、app-server schema 和启动参数；
- 固定 parent/child identity、Worker、Provider、artifact 和 effect contract；
- 将当前 Codex-only local_read_only_run 标记为 fallback baseline；
- 更新路线图，新增混合架构产品执行节点；DSH E4/E5 挑战评估作为旁路线，不阻塞只读切片。

#### Stage 1：混合只读实验

- 使用 case-local workspace、fake Provider 和独立 DSH profile；
- 每次只加载最小 coding bridge，不加载全量插件市场；
- Codex Worker 只读或隔离 worktree；
- 完成 H1–H5，生成全新的 evidence 目录；
- 任何 correlation、policy、dispose、process 或 replay unknown 都保持 stop。

#### Stage 2：单插件实验

- 每次只增加一个 allowlisted DSH plugin；
- plugin state 与 owner state 分离；
- 重跑受影响的 C1–C7/E1–E6；
- 只保留产生明确、可重复、非重复收益的插件；
- 插件收益不足或维护成本超阈值时直接 disable/rollback。

#### Stage 3：受控本地写入

- 先完成 L2/L3 approval、host boundary、effect reconcile 和 rollback；
- Worker 只在隔离 worktree 中申请 apply；
- owner 记录 approval、claim、commit、receipt 和 rollback；
- 真实主工作区、Git push、部署和远端 effect 另开 gate。

#### Stage 4：受控个人试点

- 固定一名操作者和有限项目；
- 启用少量经过验证的插件；
- 开启人工触发，自动任务先保持显式 opt-in；
- 持续执行版本、schema、插件、Provider、policy 和 fixture 变化后的回归；
- 未满足 C7、NOTICE、商业、Provider 远端和退出责任时，不扩大到团队或生产分发。

### Pause and rollback triggers

立即暂停混合路线或回退 Codex-only 的条件：

- parent/child identity 无法完整关联；
- DSH 或插件绕过 owner/policy，产生未授权 effect；
- Worker 取消/崩溃后存在孤儿进程；
- effect 状态不确定却自动重试；
- Provider 静默切换或 fallback reason 缺失；
- replay 重新访问 Worker、Provider 或工具；
- 插件 dispose 后资源泄漏，或卸载删除 owner canonical state；
- DSH/Codex/plugin/artifact provenance 无法固定；
- C7 人工时间、服务数、升级/恢复或退出超过门槛；
- 真实远端资源、Webhook、备份、retention 或账户责任超出已确认边界。

回滚动作：

1. 停止新的 scheduler trigger 和 DSH plugin enable；
2. 禁止 live replay、真实写入和危险工具；
3. 停止并确认 DSH/Codex 全进程树；
4. 对 unresolved effect 做 reconcile；不能判断时 safe-stop；
5. 保留 run、event、artifact、diagnosis 和版本 identity；
6. 恢复最后签核的 Codex-only adapter/profile；
7. 不删除证据，不把失败的混合状态导入 Codex-only canonical state。

### Migration, deprecation, and cleanup

- DSH session、插件存储、Codex session 和 owner state 分开备份和恢复；
- 跨 Harness 迁移只允许通过 versioned canonical export/import，不直接拷贝内部数据库；
- 更换 DSH 或 Codex Worker 时，先在 case-local 新 profile 建立独立 identity，再导入允许的 owner metadata；
- 停用插件前导出 plugin manifest、版本、依赖、license、配置摘要和评估结论；
- 删除本地 profile/cache/export 不代表删除 Provider 侧数据、任务、Webhook 或备份；
- 停用 Codex Worker 时，先冻结 coding triggers，确认所有 child Run 已完成或 safe-stop，再删除 Worker adapter；
- 如果混合架构长期无非重复收益，保留 CompositionOwner schema 和证据，删除 DSH bridge、profile 和插件依赖，回退至 Codex-only。

## Principle considerations

### Performance

混合架构会增加 DSH→Bridge→Codex 的进程和协议开销，也可能减少重复实现 Agent loop 的开发时间。本设计不预先声称 latency、token、吞吐、内存或功耗优势。实施时对固定机器、固定 fixture、固定 Provider 和固定模型分别测量：

- DSH 启动和 Worker handshake wall time；
- 首个 token、总运行时间和测试时间；
- Provider 请求数、retry/fallback 次数和 token；
- owner DB 增长和 artifact 大小；
- Worker 进程数、内存峰值和退出时间。

性能回归只与 Codex-only 同形状基线比较；性能提升不能覆盖安全、状态和退出硬门。

### Simplicity and accessibility

对用户而言，目标是仍然只有一个工作台入口，不要求用户理解 DSH/Codex 的所有内部协议。复杂度应由 Control Plane 转化为可读状态：planning、coding、waiting approval、recovering、safe-stopped、completed。

对维护者而言，双 Harness 会增加版本矩阵和排障路径，因此：

- 默认只启用一个 Coding Worker；
- 每个 Run 都显示 parent/child 关系；
- 日志同时提供人类可读摘要和脱敏 JSON；
- 插件实验采用 feature flag 和一键 disable；
- 不把 DSH 插件市场的实时发现作为启动依赖。

### Security and privacy

主要威胁包括模型生成命令、恶意或有缺陷的 DSH 插件、Codex 子进程、workspace 越界、凭证泄漏、Provider 请求、重复 effect、replay 误执行和远端资源遗留。

安全原则：

- 最小 capability，按 Run 注入，默认不继承全局状态；
- API key 只通过本地凭证路径注入，不进 prompt、argv、日志、owner、backup 或 artifact；
- DSH plugin 和 Codex Worker 都不能直接写 CompositionOwner；
- 代码修改默认产出隔离 diff，不直接应用到真实主工作区；
- 所有 effect 经过 request→policy→decision→claim→commit/reconcile；
- 未知状态只能 stop，不用“最终文本成功”补齐证据；
- Provider 远端数据、任务、Webhook、备份和 retention 单独记录责任 owner；
- 插件、Worker、Provider、policy 或 schema 变化触发受影响回归。

### Lifecycle cost

目标架构的主要长期成本不是启动一个 Codex 子进程，而是维护：

- DSH core/plugin ABI 兼容矩阵；
- DSH↔Codex bridge 协议；
- 两层进程生命周期和故障诊断；
- 父子事件和状态映射；
- Provider 路由、费用和降级语义；
- 插件安装、升级、备份、回滚和退出；
- 真实 Provider 和远端责任清单。

因此将快速试错限制在 DSH 插件和 profile 层；将 durable state、权限和 effect 的创新限制在 ZWorkbench 自有 contract 层，避免每次实验都引入一套新的事实源。

## Testing and validation

### Target-state validation matrix

| 层 | 目标场景 | 关键观察 | 通过条件 |
|---|---|---|---|
| H1 | DSH cold start + pinned profile | core/plugin/artifact identity | provenance 完整，插件清单固定 |
| H2 | DSH 调用 Codex Worker | parent/child/session/thread/turn | identity 关联率 100% |
| H3 | read-only coding | 代码读取、测试、diff、result | 语义结果完整，真实 effect 0 |
| H4 | cancel/timeout/crash/restart | 进程树、状态和 effect checkpoint | 孤儿进程 0，状态丢失 0 |
| H5 | provider failure/fallback | attempt、reason、target、degradation | 记录率 100%，silent switch 0 |
| H6 | recorded/simulated/live replay | process/network/tool counters | simulated/live 未批准执行 0 |
| H7 | plugin install/disable/rollback | dispose、依赖、owner state | 无泄漏，owner state 不损坏 |
| H8 | isolated edit/apply | diff、approval、claim、reconcile | 未授权 effect 0，重复 effect 0 |
| H9 | install/upgrade/backup/restore/exit | 人工时间、服务数、provenance | 安装 ≤90 分钟；其他各 ≤30 分钟；服务 ≤3 |

### Test artifact rules

- 每个 case 使用新的 case-local root、DSH_HOME、owner DB、workspace 和 evidence root；
- 每次运行记录 DSH/Codex/plugin/provider/policy/fixture/artifact identity；
- 大型历史 evaluation/runs 只保留本地证据，不作为默认提交内容；
- 所有结果区分 native、plugin-composed、outer-composed 和 owner-backed；
- unknown 保持 unknown，不转换为 negative capability，也不作为 pass；
- 真实 Provider 只通过独立 staging 流程执行，不进入默认 fixture；
- 首次混合切片通过前，不实现不可逆写入和远端 effect。

## Open decisions

| Question | Evidence needed | Owner | Due/exit condition |
|---|---|---|---|
| DSH 主 Harness 的固定版本和启动入口是什么？ | pinned checkout/package/binary、依赖和 schema digest | Harness owner | H1 通过 |
| DSH plugin 与 ZWorkbench 的最小 host facade 如何定义？ | 一个插件的 capability/permission/dispose 实测 | plugin owner | H7 通过 |
| Codex Worker 采用 app-server、CLI 还是二者兼容？ | handshake、cancel、事件和退出码的实测 | Worker owner | H2/H4 通过 |
| DSH 与 ZWorkbench 谁负责最终 Provider selection？ | primary/fallback/degradation ledger 的端到端证据 | Provider owner | H5 通过 |
| DSH session 如何与 owner 的 parent Run 关联？ | session/turn identity 是否稳定暴露 | adapter owner | H2 关键字段 100% |
| Codex diff 如何从隔离 worktree 应用到真实项目？ | approval、effect claim、reconcile、rollback 矩阵 | workspace/policy owner | H8 通过 |
| 首批需要哪些自动任务语义？ | 冷启动、错过触发、暂停、幂等和恢复用例 | product/owner | C3/C4 目标门通过 |
| 哪些 DSH 插件进入默认 profile？ | 单插件收益、维护成本、license、退出和 E1–E6 evidence | product owner | 每个插件单独决策 |
| 真实 Provider 的数据和远端资源如何退出？ | Provider/account inventory、retention、删除责任和记录 | account owner | 真实 Provider 才打开 |

## Review record

| Reviewer | Date | Concern | Response or decision | Remaining risk |
|---|---|---|---|---|
| Human + Codex design draft | 2026-09-03 | DSH 是否作为主 Harness、Codex 是否保留代码能力 | 目标架构采用 DSH 主 Harness + Codex Coding Worker；Codex-only 保留为回退基线 | 混合 seam 尚未实现 |
| Architecture review | 2026-09-03 | 两个 Harness 是否会产生多个状态中心 | 由 ZWorkbench CompositionOwner 持有唯一 durable truth；DSH/Codex state 只能作为 projection/evidence | owner correlation 需 H2 实测 |
| Security review | 2026-09-03 | 插件和 Worker 是否能绕过权限 | 统一经过 Host Capability Facade、Policy、Effect Claim 和 Host boundary；未知即 stop | L2/L3 native/host 强制边界尚未签核 |
| Operations review | 2026-09-03 | 个人开发者能否维护混合架构 | 首阶段无外部基础设施、Worker 按 Run 启动、服务上限 3、保留回退路径 | E9 人工安装/升级/退出尚未实测 |

## Evidence pointers

- [W8 双向缺口与能力吸收技术决策评审](../w8-deepseek-vs-codex-gap-analysis.md)
- [W8 受控个人试点产品边界与最小纵向切片](../w8-controlled-pilot-scope-and-vertical-slice.md)
- [W7 CompositionOwner 设计](../w7-composition-owner-design.md)
- [W8 DeepSeek 插件生态研究](../research/w8-deepseek-plugin-ecosystem-findings.md)
- [W8 DeepSeek plugin-aware E3–E6 findings](../w8-deepseek-plugin-aware-e3-e6-findings.md)
- [ZWorkbench CompositionOwner 实现](../../../src/zworkbench/composition.py)
- [Codex adapter 实现](../../../src/zworkbench/codex_adapter.py)
