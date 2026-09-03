# ZWorkbench Agent Instructions

ZWorkbench 是面向个人开发者或小团队的本地优先个人工作台。目标架构是：

> DSH 主 Harness + Codex Coding Worker + ZWorkbench CompositionOwner。

本文件是仓库级长期规则和导航入口。它描述 Agent 每次工作都要遵守的执行方式、事实源和硬性边界；易变的版本、评测结果、详细接口和运行命令放在被指向的文档与代码中。

## 1. Decision spine

### Target architecture

- DSH 是主 Harness：负责顶层 Agent loop、会话、插件组合、上下文、任务路由和个性化运行时实验。
- Codex 是 Coding Worker：负责代码理解、修改、测试、构建和可审查 diff；首期以进程外 Worker 接入。
- ZWorkbench Control Plane 负责产品级编排、Worker 监督、Workspace/Artifact、Provider、Evidence/Replay 和退出。
- CompositionOwner 是唯一 durable source of truth：负责 run、attempt、event、effect、result、approval、replay metadata、backup/restore 和 safe-stop。
- DSH session、插件存储、Codex session/rollout、Provider 日志和观测投影都只能作为输入或 evidence，不能成为第二个 canonical owner。

当前代码和用户入口仍可能是 Codex-only 的 local_read_only_run。它是可运行回退基线，不代表目标混合架构已经实现。目标架构设计见 [dsh-codex-hybrid-target-architecture.md](docs/plans/designs/dsh-codex-hybrid-target-architecture.md)。

### Decision hierarchy

发生冲突时，按以下顺序处理：

1. 用户当前明确的范围和安全授权；
2. 本文件的长期硬约束；
3. [ZJ-CONTEXT.md](ZJ-CONTEXT.md) 的领域词汇和共享语义；
4. [docs/plans/designs/](docs/plans/designs/) 中已确认的目标设计；
5. roadmap JSON 的事实源和已记录决策；
6. 代码、配置、测试和运行产物；
7. 旧报告、临时评测目录和对话中的未落盘判断。

代码和环境是真实状态；本文件只补充环境不直接表达的长期规则，不复制易变的版本和命令。

## 2. Execution protocol

每个任务按以下顺序执行，完成一个阶段后再进入下一阶段。

### Step 1 — Scope gate

先判断工作属于哪一类：

- Product execution：用户要求实现、修改、交付或发布 ZWorkbench；可以在明确范围内修改产品代码。
- Acceptance/evaluation：任务是评测 Harness、插件、fixture、研究或 legacy 能力；默认只修改评测资产和证据，不修改产品代码。
- Mixed/unclear：先把产品实现和评测验证拆成两个范围；在范围明确前不修改共享代码、依赖或生产配置。

任何 roadmap 节点开始前，先确认它的路线角色。评测通过不等于产品能力已实现；source capability、plugin-composed、outer-composed 和 owner-backed 证据必须分开标记。

### Step 2 — Navigate before editing

先读取本文件，再根据下方导航索引找到最小相关材料：

1. 检查 git status，保留用户已有改动，不覆盖、不重置、不清理无关文件；
2. 查看 README、相关设计/路线图和现有测试；
3. 确定修改边界、事实源、受影响的验证和回滚方式；
4. 若方向性决策尚未落盘，先通过 roadmap CLI 记录决策并 render 视图；
5. 只有完成 scope、owner、failure behavior 和 acceptance threshold 的检查后才编辑代码。

路线图的 JSON 是事实源，Markdown 是生成视图。禁止手工编辑 roadmap JSON 或其生成的 roadmap Markdown；使用 zj-roadmap-driven 的 roadmap_cli.py 执行 decide、update 和 render。

### Step 3 — Implement a narrow seam

优先复用已有模块和上游能力，以一个可验证的深接口完成一条 tracer-bullet：

1. 先写行为合同和失败语义；
2. 先让一个最小测试或 fixture 变红；
3. 实现最小改动；
4. 在真实边界处校验输入、线协议、持久化数据、子进程消息和 Provider 响应；
5. 保持状态、权限和副作用的唯一 owner；
6. 为失败、取消、恢复、回滚和退出保留可复核证据。

新的能力放在明确的 DSH plugin、Worker、Provider Adapter 或 ZWorkbench Control Extension seam 上。不要通过隐式全局状态、猴子补丁或复制另一套 Agent loop 来扩展。

### Step 4 — Verify and close

完成标准不是“代码能跑”，而是：

- 相关测试、fixture 或评测命令通过；
- 失败路径和默认拒绝路径已验证；
- 受影响的文档、导航和 roadmap 状态已同步；
- 版本、依赖、权限、Provider、artifact 和 evidence identity 可复核；
- git diff --check 通过；
- 没有凭证、API key、生产数据或大型历史 runs 被加入变更；
- 未完成事项仍显式标为 pending、unknown、HOLD 或 blocked；
- 用户未要求时不 commit、不 push、不发布。

## 3. Navigation index

| 任务 | 先读 |
|---|---|
| 方案准备阶段、当前目标态和文档分类 | [docs 文档地图](docs/README.md)；[开发前基线](docs/plans/development-baseline.md) |
| 理解目标架构和模块 ownership | [目标架构设计](docs/plans/designs/dsh-codex-hybrid-target-architecture.md) |
| 理解领域词汇、unknown 和 replay 语义 | [ZJ-CONTEXT.md](ZJ-CONTEXT.md) |
| 查看路线、当前焦点和已落盘决策 | [roadmap JSON](docs/plans/personal-workbench-w8-roadmap.json)；使用 roadmap CLI 的 tree、focus、decisions、path、render |
| 了解当前用户入口和 Codex-only 回退基线 | [README.md](README.md)；[local_read_only CLI 设计](docs/plans/w8-1-7-local-read-only-cli.md) |
| 修改 durable state、approval、effect、reconcile、backup/restore | [composition.py](src/zworkbench/composition.py)；[CompositionOwner 设计](docs/plans/w7-composition-owner-design.md) |
| 修改 Codex app-server/CLI 接入 | [codex_adapter.py](src/zworkbench/codex_adapter.py)；[local_run.py](src/zworkbench/local_run.py) |
| 开发 DSH 主 Harness 或插件 facade | [目标架构设计](docs/plans/designs/dsh-codex-hybrid-target-architecture.md)；[DSH 插件生态研究](docs/plans/research/w8-deepseek-plugin-ecosystem-findings.md) |
| 开发 DSH–Codex Worker bridge | 目标架构的 Worker/Bridge 章节；codex_adapter.py；对应 Worker contract 和 H1–H5 验证 |
| Provider profile、路由、retry、fallback、降级 | 目标架构 Provider 章节；[DeepSeek E4 Provider findings](docs/plans/w8-deepseek-e4-provider-failover-v2-findings.md)；[真实 Provider staging](docs/references/optional-real-provider-staging.md) |
| scheduler、幂等和中断恢复 | 目标架构 Scheduler/状态章节；[W6 C3](docs/plans/w6-c3-idempotency-findings.md)；[W6 C4](docs/plans/w6-c4-recovery-findings.md) |
| 记录、诊断和回放 | 目标架构 Evidence/Replay 章节；[W6 C6](docs/plans/w6-c6-replay-findings.md) |
| 评测 fixture、阈值和证据 | [W6 evaluation matrix](docs/plans/w6-evaluation-matrix.md)；[fixtures](evaluation/fixtures/)；[evaluation runners](evaluation/runner/) |
| 安装、升级、许可证和退出 | [W6 C7](docs/plans/w6-c7-operations-findings.md)；[optional Provider exit inventory](docs/references/optional-provider-exit-inventory.md) |
| Python 包入口和命令 | [pyproject.toml](pyproject.toml)；[README.md](README.md)；代码中的 --help 输出是命令事实源 |

### Source map

~~~text
src/zworkbench/
  composition.py       durable CompositionOwner
  codex_adapter.py     Codex app-server/CLI adapter
  local_run.py         local_read_only_run orchestration and preflight
  cli.py               installed user-facing CLI
  composition_cli.py   owner snapshot/backup/restore CLI

tests/
  behavior and regression tests for owner, adapter, orchestration and CLI

evaluation/
  fixtures/             isolated, versioned test inputs and fake services
  runner/                reproducible evaluation entry points
  evidence/              generated evidence; normally local-only
  runs/                  historical/generated runs; never bulk-commit

docs/plans/
  designs/              target and technical design documents
  research/             cited research and sealed ledgers
  personal-workbench-*  roadmap facts and generated view
  w6/w7/w8-*            scoped decisions, contracts and findings
~~~

## 4. Long-lived hard constraints

这些规则是架构不变量。除非用户明确改变产品目标并完成新的设计评审，否则不能为了方便、性能或“先跑起来”绕过。

### Ownership and state

- 只允许一个 ZWorkbench durable owner。所有跨 Run 的 run、attempt、event、effect、result、approval、replay metadata、backup/restore 和 exit ledger 必须归 CompositionOwner。
- DSH session、DSH plugin state、Codex thread/turn/rollout、Provider router state 和 observability projection 不能被升级为第二个事实源。
- 插件配置迁移、Harness session 导入和 CompositionOwner backup/restore 是不同合同，必须分别验证和分别记录。
- 关键身份至少维持 run_id → parent/child run → dsh session/turn → worker run → codex thread/turn → event/effect/artifact 的可查询关系。字段不暴露时记录 unknown，不猜测填值。
- 状态不确定、effect 未 reconcile 或关键 identity 缺失时，状态是 unknown/safe-stopped，不是成功。

### DSH plugin rules

- DSH plugin 是可组合能力，不是绕过宿主的特权层。每个插件必须有固定 source/version/commit/digest、声明的 capability、permission、依赖和生命周期。
- 插件的 install、enable、disable、dispose、migrate、rollback 都必须有可观察结果；dispose 后注册的 RPC、工具、UI、样式、监听器和后台任务必须归零或有明确残留 owner。
- 所有插件贡献通过显式 registration/effect，并保留 disposer；禁止隐式全局注册、静默覆盖和未声明的后台任务。
- 插件通过 Host Capability Facade 访问文件、Provider、owner、子进程和外部服务；禁止直接写 CompositionOwner SQLite、直接改事件/效果/结果表或以 full-access 声明覆盖宿主 policy。
- 插件引入的新 model-visible input 必须进入可重建的 session/event 记录；没有记录的输入不能参与可复现回放或评测。
- DSH waterfall/listener 等可组合处理器必须显式委托下一个处理器；只有声明的终止决策才可以短路。
- 配置变化的部署选择必须是显式、可校验的 Config；安全不变量、协议字段和外部规范不能变成可随意调节的插件常量。
- 配置或依赖错误在最早可以判断的位置 fail loud；不静默跳过缺失插件、缺失依赖或不兼容 ABI。
- 不把插件目录、GitHub stars、README 自述或市场条目数量当作兼容、质量、安全或 C1–C7 通过证据。

### Codex Worker rules

- Codex 是 Coding Worker，不是 ZWorkbench 的主状态 owner，也不是 DSH 的隐式内核替换。首期通过显式 app-server/CLI bridge 进程外接入。
- Worker 启动必须绑定固定 executable/artifact、schema、argv/env 摘要、workspace/worktree、policy digest、Provider profile 和 child run identity。
- Worker 的输入、事件、请求、结果、退出码、取消、超时和崩溃都要通过 bridge 关联到 parent/child run；未知或无法解析的 wire message fail-closed。
- Worker 默认只读或在隔离 worktree 中生成可审查 diff。生成 diff 与应用 diff 是两个不同动作；应用必须经过 owner policy、approval、effect claim、receipt 和可恢复流程。
- 父任务停止时必须停止并核对整个 DSH/Codex 子进程树；不得留下孤儿 Worker。Worker 已完成不代表 parent run 已完成，也不代表 diff 已应用。
- DSH retry、Worker retry 和 Provider retry 必须有明确 owner 和预算；禁止多层无界 retry 或把 retry 误称为 failover。
- 不把 Codex session 文件、rollout trace 或 app-server API 的存在直接解释成 durable scheduler、safe replay、exactly-once effect 或生产安全证明。

### Policy, effects and security

- 所有可能产生副作用的动作都经过 request → policy → decision → claim → execute → complete/reconcile；模型、插件、Worker 和 Provider 都不能跳过 owner。
- 未知工具类别、未知 effect class、未知审批结果、越界 workspace、未声明网络/凭证/子进程或不可观察的 host boundary 必须 deny/safe-stop。
- approval-required 使用精确 operation、action、resource、idempotency key 和一次性授权；token 只保存必要的不可逆表示。
- 外部结果不确定时先 reconcile；不能把“没有看到结果”解释为“没有发生”；无法判断时不自动 retry。
- 真实主工作区、Git push、部署、Webhook、远端写入和不可逆操作必须单独开 gate。第一混合切片使用 case-local workspace、fake/loopback Provider 和隔离 worktree。
- API key、token、cookie、生产数据和敏感 Provider 响应不得进入 prompt、命令行参数、事件、日志、owner、backup、cassette、artifact 或 git。真实凭证只能经本地凭证路径或隐藏输入注入。
- Provider identity 不能静默替换。每次 retry/fallback/degradation 都记录 provider、model、endpoint、capability、attempt、failure class、target 和 reason。
- 适配器层的 deny 不能冒充 OS/host sandbox；L1 policy、L2 Harness approval、L3 host enforcement 要分别验证。

### Replay and evidence

- recorded_view 只查看已保存事实；simulated_replay 只消费封存 cassette/fixture；live_replay 默认拒绝。三者不能共用一个隐式执行入口。
- recorded view 不叫 replay；session resume 不自动等于 deterministic replay；源码/API 存在不等于运行时行为已经验证。
- replay 和评测必须绑定 Harness/plugin/Worker/Provider/tool/policy/workspace/environment/owner schema/cassette identity；缺关键字段则保留 unknown。
- evidence 必须区分 native、plugin-composed、outer-composed 和 owner-backed。组合件通过不能提升为某个 Harness 原生通过。
- 大型历史 evaluation/runs 和机器生成 evidence 默认不提交。需要提交时只选择最小、可复核、与变更直接相关的摘要或 fixture；不要批量加入整个历史目录。
- 评测结果不能替代产品测试；产品代码变更要有产品级行为测试，评测代码变更要有 fixture/runner 的可重复验证。

### Version, dependency and lifecycle

- DSH core、plugin、Codex Worker、app-server/ACP schema、Provider profile、policy、tool schema、owner schema 和 fixture 发生变化时，重新运行受影响的验证，不继承旧 evidence。
- 版本和依赖必须可回溯到 source commit/package/binary digest；不能把实时插件市场或未锁定远端 registry 作为启动时的隐式依赖。
- 优先采用真正删除自有代码和测试的维护依赖；引入依赖前评估安装、升级、license/NOTICE、漏洞、退出和维护责任。
- 运行时资源必须可关闭、可恢复、可诊断；常驻人工维护服务目标不超过 3 个。按 Run 的 Worker/helper 也必须有明确退出路径。
- 任何升级、迁移、备份、恢复或卸载都先在 case-local 或隔离环境验证；备份必须区分 owner canonical state、plugin/config state、session state 和远端资源。
- 本地退出不等于 Provider 侧退出。远端数据、任务、Webhook、备份、retention、账单和账户撤销由账户 owner/Provider 单独负责并记录。

## 5. Change routing

| 变更 | 必须保持的边界 | 最小验证 |
|---|---|---|
| 新 DSH plugin | manifest、版本/依赖 pin、capability/permission、dispose、owner state 分离 | install/enable/disable/rollback + 资源泄漏检查 |
| DSH–Codex bridge | parent/child identity、wire protocol、进程树、cancel、timeout、safe-stop | H1 Bootstrap、H2 Handshake、H3 Read-only coding、H4 Lifecycle |
| CompositionOwner | transaction、idempotency、approval、uncertain/reconcile、backup digest | owner 单测 + C3/C4/C6 受影响 fixture |
| Provider adapter/router | capability、attempt、failure class、fallback target/reason、全冷却行为 | 双 loopback Provider；fallback reason 记录率 100%；silent switch 0 |
| Workspace/diff/apply | case/worktree 隔离，diff 与 apply 分离，approval/effect receipt | 未授权 effect 0；重复 effect 0；rollback 可复核 |
| Scheduler/automation | durable trigger、missed trigger、pause/resume、幂等、retry budget | 冷启动/重复 trigger/进程重启/C3/C4 |
| Replay/evidence | mode 隔离、事件完整性、脱敏、artifact identity | recorded/simulated/live counters；未批准外部执行 0 |
| CLI/user entry | preflight、可读错误、JSON 脱敏、退出清理 | CLI tests + case-local smoke + --help |
| 评测 fixture/研究文档 | 与产品实现分开，固定 source/evidence/status，unknown 不升级 | runner、summary、evidence provenance 和对应阈值 |
| roadmap/docs | 事实源唯一，决策可追溯，生成视图同步 | roadmap CLI validate + render；文档链接检查 |

## 6. Definition of done

一个产品变更只有在以下条件全部满足时才算完成：

- 需求、范围、owner、状态转换、错误语义和停止条件已明确；
- 代码位于正确的 extension seam，没有新增第二个 Agent loop 或 durable owner；
- 正常路径、失败路径、取消/恢复路径和安全负向路径有对应测试；
- 新增的 DSH/Codex/Provider 边界有版本、schema、权限和身份记录；
- 相关 docs、AGENTS 导航、roadmap decision/status 已同步；
- 运行产物脱敏，凭证和生产数据未落盘；
- 受影响的 C1–C7/H1–H8 验证已运行并报告实际命令与结果；
- git diff --check 通过，工作树中无无关文件被覆盖；
- 未经用户明确要求，不执行 commit、push、发布、远端删除或不可逆迁移。

如果任何关键项只能得到 unknown，完成状态必须是 unknown/stop 或 HOLD，并写明下一证据、owner 和回滚路径。
