# W8 DeepSeek ↔ Codex 双向缺口与能力吸收技术决策评审

评审状态：`acceptance/evaluation draft` · 日期：`2026-09-01` · 决策 owner：个人开发者/小团队负责人

本文回答两个相反方向的问题：

1. 用 DeepSeek Harness 补齐当前 Codex/工作台缺口，是否做得到，代价是否符合个人开发者或小团队的要求；
2. DeepSeek 是否存在相对 Codex 的真实或潜在优势，以及这些优势能否以更小、更可控的代价被 Codex 路线吸收。

本文是技术决策评审，不是实现计划，也不是 DeepSeek、Codex 或任何 Provider 的产品/法律保证。结论只适用于固定版本、当前 ZWorkbench 边界和 W6-0.1 C1–C7 评估合同。

## One-page overview

### Decision

Decision: defer。

延期的是“切换到 DeepSeek 主 Harness”“引入 DeepSeek 第二生产 Harness”和“为兼容 DeepSeek 生态而扩大产品边界”；当前路线继续保留 Codex `0.139.0` + 一个 SQLite composition owner，先完成既有 W8 阻断项。可以记录并在需要时吸收 DeepSeek 的局部协议/设计思想，但每个增量能力必须单独过 ATAM/CBAM 和 C1–C7 回归。

未解决发现分为两类：

- `blocking`：对真实写操作或生产采用仍阻断。Codex 的 native approval/宿主进程树边界仍为 `unknown`；C7 的 NOTICE/商业边界、真实远端责任和完整供应链签核仍未关闭。DeepSeek 的 C4 为 `24/36` composition pass、`12/36` approval unknown，C5/C6 仍为 `unknown`，C7 为 `unknown-stop`。
- `non-blocking`：对当前隔离的 `local_read_only_run` 和继续做产品开发不阻断。没有证据证明第二 Harness 会带来非重复收益；没有明确 ACP 外部互操作需求时，不需要为了兼容 ACP 另起一条运行时。

### Summary

DeepSeek 不能以“已有更多子系统”直接补齐 ZWorkbench 的 scheduler、幂等副作用、跨 Provider failover、可回放和退出责任；固定版本的实测只证明 C1、C2 adapter 和部分 ACP session lifecycle。基于 DeepSeek 构建完整方案在技术上可行，但仍必须拥有与当前相同的 composition、policy、effect、provider、replay 和 lifecycle 边界，整体代价是高于沿用 Codex 既有证据链。DeepSeek 最值得吸收的是显式的事件/插件/ACP seam 和局部 session automation 思路，而不是整个 Harness、第二套状态语义或完整插件生态。

### Platforms and scope

- ZWorkbench：个人开发者或小团队、本地优先、项目级隔离、最小权限；当前产品切片为 `local_read_only_run`，可恢复本地写入仍受 Gate B/HOLD 约束。
- Codex 固定对象：`openai/codex`，`codex-cli 0.139.0`，release `rust-v0.139.0`，peeled commit `a7dff904308535e965aee87680c1fc5ef1d19eec`。
- DeepSeek 固定对象：`deepseek-ai/deepseek-harness`，版本 `0.1.2-alpha.1`，commit `cd5ef8148158c3a752a658978873241fdf8e2bbc`。
- 共同证据边界：case-local workspace、独立运行目录、loopback fake Provider、无真实凭证、无生产数据、无不可逆外部副作用。
- 评估资产：W6-0.1 C1–C7 fixture、W7 Codex owner-backed evidence、W8 DeepSeek challenger evidence；大型 `evaluation/runs/` 仅作为本地证据，不作为本决策文档的提交内容。
- 排除：不在本评审中实现 DeepSeek adapter、不接入真实 Provider、不引入 Temporal/LangGraph/LiteLLM/独立观测平台、不把 DeepSeek 作为真实写操作的安全边界。

### Ownership and tracking

| 责任面 | owner | 本评审后的边界 |
|---|---|---|
| 执行循环、工具调用、app-server/ACP transport | Harness adapter owner；当前为 Codex 路线 | 只负责把候选运行映射到 ZWorkbench 合同，不拥有跨 Run 的唯一 durable truth |
| run/thread/turn/event/effect/result 状态 | 单一 SQLite composition owner | 不允许 Codex、DeepSeek 或多个组合件各自生成同一事实 |
| scheduler、幂等、重试、safe-stop | composition/policy owner | 只接受有 attempt/effect identity 和可恢复状态的动作 |
| Provider capability、fallback、降级原因 | Provider owner | 不允许 silent switch；当前火山方舟等真实 Provider 只按需、隔离验证 |
| 记录、cassette、simulated/live replay | replay/evidence owner | `recorded_view`、`simulated_replay`、`live_replay` 分离，live 默认 deny |
| 宿主隔离、native approval、凭证和危险副作用 | policy/host owner + 个人负责人 | 未观察到真实拒绝链路时保持 fail-closed/HOLD |
| NOTICE、商业边界、发布 provenance、远端退出 | supply-chain/compliance owner + 账户 owner | agent 只能整理证据，不能替责任人签法律或 Provider 侧结论 |
| 采用与重开决策 | 个人开发者/小团队负责人 | 只在硬门槛满足后决定切换、吸收或保持 no-change |

证据入口：[`w8-deepseek-challenger-evaluation.md`](./w8-deepseek-challenger-evaluation.md)、[`w7-codex-atam-cbam-adoption-decision.md`](./w7-codex-atam-cbam-adoption-decision.md)、[`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md)、[`w6-fixtures-and-thresholds.md`](./w6-fixtures-and-thresholds.md)、[`w2-named-harnesses.md`](./research/w2-named-harnesses.md)。

## Problem and goals

### User/job and current baseline

ZWorkbench 需要完成代码与通用任务，支持少量自动/定时任务，集成个人项目，提供可观测、可回放、可评测和可排障能力，连接多家 LLM Provider，并尽可能保持优秀的代码开发能力。当前工作台已经选择 Codex 作为唯一主 Harness 条件候选，使用一个 SQLite composition owner 补充跨运行状态和组合式 C2–C6 合同。

当前可用事实如下：

| 能力 | Codex 当前证据 | DeepSeek 当前证据 |
|---|---|---|
| C1 代码闭环 | fake-a/fake-b 各 `5/5` | fake-a/fake-b 各 `5/5` |
| C2 安全 | adapter scripted path `15/15`，关键拦截 `100%`；native/host 仍 unknown | fail-closed adapter `6/6`；不等于宿主 sandbox/native approval 签核 |
| C3 自动化/幂等 | composition `15/15 pass-with-composition`，有效副作用 `1`、重复额外副作用 `0` | 同形状 DeepSeek composition `15/15`；候选专属 scheduler/trigger 仍未测量，native unknown |
| C4 中断/恢复/副作用 | composition approval/recovery `36/36 pass-with-composition`；native approval unknown | DeepSeek composition `24/36` 通过、`12/36` approval unknown；ACP resume、effect ledger 和幂等 retry 已测，候选原生 permission/turn identity unknown |
| C5 Provider | composition fallback `19/19 pass-with-composition`；静默语义变化 `0` | timeout 时只观察到同 Provider retry，第二 Provider 请求 `0`，`unknown` |
| C6 记录/回放 | composition 三模式 `15/15 pass-with-composition`；live replay side effect `0` | session log/recorded view 有证据；固定版本不提供可接受的 transcript replay 合同，`unknown` |
| C7 运维/退出 | machine contract 与多项人工计时已有，但 NOTICE/商业/真实远端责任仍 signoff-open，整体 `unknown-stop` | MIT/NOTICE 静态检查有证据；真人生命周期、真实 backup/restore、provenance 和退出责任缺失，`unknown-stop` |

### Goals

- 判断“DeepSeek 作为主 Harness 补缺口”是否相对当前 Codex 路线有足够的收益/成本比。
- 判断 DeepSeek 的优势是已证实的产品能力、仅有源码/文档证据的候选能力，还是尚未验证的假设。
- 找出可以在 Codex + composition owner 上低风险吸收的局部能力，并拒绝复制第二套运行时语义。
- 维持个人开发者或小团队硬约束：单一主要维护者可完成安装、升级、备份恢复和排障；无需额外专家；MVP 常驻人工维护服务不超过 `3` 个。
- 把下一轮验证绑定到可重复场景、阈值、责任人和明确的停止/回滚动作。

### Non-goals

- 不在本评审中把 DeepSeek、Codex 或组合件宣布为生产安全、商业合规或真实 Provider 质量保证。
- 不因 DeepSeek 有更多源码目录、插件包或文档描述，就推断 C3–C7 已通过。
- 不做 DeepSeek 与 Codex 的全功能数量排名；只比较对 ZWorkbench 目标有影响的质量属性和 ownership cost。
- 不实现完整 DeepSeek ACP/Cordis 兼容层、agent teams、通用工作流引擎或第二套 effect ledger。

### Assumptions and constraints

- W6-0.1 阈值冻结：关键安全/副作用/事件/回放项采用零容忍或 `100%`；未知不作为通过，也不能通过平均分抵消。
- `pass-with-composition` 只能说明明确 owner 补齐后的组合合同通过，不能提升为 Harness 原生通过。
- “能实现”与“满足评估要求”是两个判断：前者是工程可行性，后者还要经过证据、运维、供应链、退出和个人/小团队门槛。
- 下文成本是 CBAM 的相对规划估算，不是已经发生的人日或性能实测；真正的 C7 人工时间仍使用 stopwatch，不能用机器耗时替代。

### Success definition

候选或新增能力只有同时满足下列条件，才可进入受控真实写入或生产采用讨论：

- C2：关键拦截率 `100%`，未授权执行 `0`；native/host 边界必须有可观察的 request→decision→effect/denial 链路。
- C3：同一幂等 key 的有效副作用恰好 `1`，重复额外副作用 `0`；触发、错过触发、暂停/恢复和并发语义必须有 owner。
- C4：状态丢失 `0`、危险副作用重复 `0`、未知 effect 不自动重试、retry 不超过冻结上限 `1`。
- C5：静默语义变化 `0`，fallback/degradation reason 和目标记录率 `100%`。
- C6：必需事件字段和 mode label `100%`，确定性 simulated replay `5/5` 与预期一致，未批准 live replay 副作用 `0`。
- C7：首次安装 ≤`90` 分钟；升级、backup/restore、预制故障定位各 ≤`30` 分钟；无需额外专家；MVP 常驻人工维护服务 ≤`3` 个。
- 任何真实写入前，C4 native/host approval 和 C7 关键签核不能以 `unknown` 代替。

## Design

### Cost rubric used by CBAM

以下只是用于比较方案的工程量级，不是验收阈值：

| 量级 | 规划含义 | 对个人/小团队的警示 |
|---|---|---|
| `L` | ≤`3` 个工程日；不新增常驻服务、不迁移 durable schema | 可以进入局部吸收候选，但仍需回归 |
| `M` | `1–2` 个工程周；新增一个 adapter/协议面或若干 owner 字段 | 只有在明确增量收益和可回滚方案时接受 |
| `H` | `2–6` 个工程周；涉及状态/权限/事件/Provider 语义和多场景回归 | 通常需要专项票据，不应顺手加入主线 |
| `VH` | `>6` 个工程周，或引入第二运行时/常驻服务/生态兼容层 | 默认不满足当前小团队路线，除非改变产品目标 |

成本包含开发、测试、版本回归、备份迁移、故障排查和退出文档；若只计算“把代码跑起来”的时间，会低估真实 CBAM 成本。

### Alternative 1 — 用 DeepSeek 替换 Codex 并补齐工作台缺口

#### 能否做到

**技术上可以，但不是 DeepSeek 单体做到。** DeepSeek 固定版本确实有 session event、plugin/Cordis、ACP、session-local schedule/jobs/workflow、LLM retry 和 sandbox 相关源码/文档表面；但 W8 实测没有把这些表面证明成 ZWorkbench 所需的端到端合同。要达到目标，仍需保留一个唯一 composition owner，并为 DeepSeek 做 adapter、事件映射、权限接管、Provider router、effect ledger、replay contract 和 C7 runbook。

| 当前缺口 | DeepSeek 固定版本观察 | 补齐路径 | 规划成本 | 是否满足当前评估要求 |
|---|---|---|---:|---|
| scheduler/trigger | 文档有 `after/at/every` 和 session-local schedule，但依赖 live session；headless 候选 C3 未形成专属 trigger contract | 由 composition owner 持有 durable schedule、错过触发、幂等 key 和唤醒；DeepSeek 只执行已授权 run | `M` | 现在不满足；完成冷启动/进程重启/重复触发 C3 后才可判断 |
| 中断/恢复 | ACP `new/list/resume/cancel` 和 session log 可恢复；工具、Provider、effect 状态未完整验证 | adapter 关联 run/thread/turn，owner 先 reconcile effect ledger，再决定 resume/retry/safe-stop | `H` | 现在不满足；C4 完整注入矩阵通过后才可判断 |
| 幂等副作用 | 没有候选级 effect ledger + exactly-once 外部 sink 证据 | 复用现有 SQLite owner 的 claim/commit/reconcile/token 语义；禁止模型或 session log 自行重放写入 | `H`（复用 owner 后为 `M` 级增量） | 只有 owner-backed C3/C4 通过才满足 |
| 双 Provider failover | 可配置不同 endpoint；故障 probe 只在同一 Provider retry，`fake-b` 为 `0` 次 | 外部 router 记录 capability、attempt、failure、fallback target 和 degradation reason | `M` | 现在不满足；C5 通过且无 silent change 才满足 |
| recorded/simulated/live replay | session log 可读；resume 不自动重放历史 update；固定版本 transcript replay unknown | 把 DeepSeek 事件映射到 canonical ledger，使用 cassette-only simulated replay，live 默认 deny | `M–H` | 现在不满足；C6 三模式和副作用门通过才满足 |
| host/native approval | 有 sandbox/approval 包，但官方安全说明明确未完成 security audit/production-ready 声明 | 仍需可观察的 host/broker rejection surface；不能用 DeepSeek adapter deny 替代宿主拒绝 | `H` | 当前为阻断；需要 L2/L3 证据 |
| 安装、升级、备份、排障、退出 | 静态 MIT/NOTICE 检查通过；真实生命周期与 source-to-binary provenance 未建立 | 完成真人 C7、固定发布物 provenance、NOTICE/商业边界和 Provider 责任清单 | `M–H` | 当前 `unknown-stop`，不满足 |

#### 代价判断

如果从 Codex 切换到 DeepSeek，表面上仍可以保持“一个 Harness + 一个 composition owner”，因此不必然违反常驻服务 ≤`3` 的门槛；但要重新验证所有 C2–C7，并承担 DeepSeek `developer preview` 的 breaking-change、sandbox 生产就绪性和 ACP/事件语义映射风险。现有 Codex 的 C3–C6 composition evidence、真实 owner backup/restore 和人工 C7 计时不能迁移为 DeepSeek 的证据。

结论是：**可行性 `yes`，当前评估合格性 `no`，小团队成本姿态 `H–VH/不值得切换`。** 只有当 DeepSeek 在一个明确的、Codex 无法以 `L/M` 成本满足的任务上产生可重复的净收益，并完成同一 C1–C7 复评，才重开替换决策。

### Alternative 2 — 保留 Codex，吸收 DeepSeek 的局部优势

这是当前推荐的方向，但“吸收”指在 ZWorkbench 自有 owner/adapter 中实现明确合同，不是把 DeepSeek 代码或整个 Cordis 运行时搬进来。

| DeepSeek 的候选优势 | Codex 侧吸收方式 | 成本 | 增量收益与边界 | 当前判断 |
|---|---|---:|---|---|
| 显式 ACP session transport | 在现有 Codex app-server JSON-RPC adapter 外加 ACP translation seam；只映射经过定义的 session/run/event 子集 | `M` | 若需要外部 ACP client，可降低互操作成本；不能自动提供 replay、effect 或 approval | **可做，按需求吸收** |
| session-local `after/at/every` 和 jobs/workflow 表面 | 在 composition owner 上实现单人 durable schedule/trigger；Codex 只执行被 owner 授权的 run | `M` | 直接覆盖 C3 的冷启动、幂等、暂停/恢复和 safe-stop；比依赖 live session 更符合目标 | **最值得吸收** |
| “everything is a plugin” 的统一扩展心智模型 | 定义 ZWorkbench extension contract，映射 Codex MCP/dynamic tools/skills/app-server；策略、ledger 和权限仍归 owner | `M–H` | 统一扩展入口；不复制 Cordis lifecycle，不允许插件绕过 policy | **只吸收边界，不兼容全生态** |
| `pi-ai`/Provider adapter 目录较宽 | 为 Codex 建立 provider profile + capability registry；先支持 OpenAI-compatible endpoint（包括已验证的火山方舟路径） | `L`（窄范围）/`H`（完整目录兼容） | 解决目标 Provider 接入即可；Provider 数量不是 failover 证据 | **窄范围吸收** |
| append-only session event、seed/replay 的显式表述 | 继续用 Codex rollout/event stream 填充 canonical event ledger；增加 schema/version/cassette identity | `L–M` | 当前 C6 composition 已有基础；不能把日志查看称为执行回放 | **已部分吸收** |
| agent teams、并行 jobs、任务 DAG | 在 owner 上增加多 worker、任务依赖、权限和 effect 协调，或引入 workflow engine | `H–VH` | 可能提升长流程吞吐，但复制状态/权限/回放/运维复杂度 | **当前不吸收** |
| MIT 根许可证 | 无需改变 Codex；许可证不是功能优势 | `L` | Codex Apache-2.0 同为宽松许可；两者都需逐项 NOTICE、依赖和商业边界审查 | **不作为选型理由** |
| sandbox backend 覆盖面 | 只使用 Codex 已有 sandbox/approval surface + 独立 host evidence；不复制 DeepSeek 未审计的安全实现 | `M–H` | 必须由可观察 host rejection 证据决定，不由“后端数量”决定 | **不直接吸收** |

#### 代价判断

对 Codex 路线，调度、Provider router、canonical event/replay 和 owner backup/restore 已有组合式证据和代码边界；新增局部能力主要是扩大 owner 合同并重跑受影响场景，而不是新增第二个 agent loop。窄范围 ACP/Provider profile 属于 `L/M` 级可选增量；完整 Cordis/plugin/agent-team 兼容属于 `H/VH`，不符合当前个人/小团队约束。

结论是：**可行性 `yes`；对局部能力可满足评估要求；完整兼容 DeepSeek 生态不满足成本要求。**

### Which functions are genuinely better than Codex?

当前不能签署“DeepSeek 整体优于 Codex”。更准确的分层如下：

| 比较项 | 判断 | 证据等级 | 对 ZWorkbench 的意义 |
|---|---|---|---|
| 代码任务质量 | 两者在共同 fake Provider C1 smoke 都是 `5/5`；没有胜负证据 | `observed` | 不足以支持更换主 Harness |
| 插件/事件组织 | DeepSeek 的 Cordis/plugin 与生命周期事件在源码/文档中更显式、更统一 | `observed source capability`，非完整产品验收 | 可借鉴接口设计；不值得搬第二运行时 |
| session automation | DeepSeek 文档 surface 比 Codex OSS CLI 更直接，但依赖 live session；composition parity 已通过，native scheduler 仍 unknown | `source/documented + composition observed` | 可作为 owner scheduler 的语义参考，不能作为 native 通过依据 |
| ACP 互操作 | DeepSeek 有明确 ACP session surface；Codex 有 JSON-RPC app-server，二者不是同一合同 | `observed` | 只有需要 ACP client 时才有实际增量收益 |
| Provider 覆盖 | DeepSeek 可通过 `pi-ai`/adapter 接入较宽 Provider 面；并未证明自动 failover 或能力等价 | `source capability; C5 unknown` | 对当前 OpenAI-compatible Ark 路径不是决定性优势 |
| 回放 | 两者都不能在本评估中承诺安全的外部副作用 exactly-once replay；Codex composition C6 已有更完整合同证据 | `observed mixed` | DeepSeek 不是回放优势来源 |
| 安全 | DeepSeek 自身安全说明保守，明确未审计/非 production-ready；Codex host/native approval 也尚未完全签核 | `unknown/partial` | 不能把 DeepSeek 作为安全升级 |
| 运维和退出 | DeepSeek C7 `unknown-stop`；Codex 有更多真人/owner-backed evidence 但仍 signoff-open | `observed` | Codex 当前更接近小团队可控，但尚未完成生产签核 |
| 许可证 | MIT vs Apache-2.0，均不能单独推出可商用/可再分发结论 | `observed declarations` | 不是功能优势；仍需 NOTICE/商业/Provider 条款审查 |

因此 DeepSeek 的“更好”只在局部设计表面成立，尚未形成“更好的工作台能力”。当前唯一足够清晰的候选增量是 ACP/插件/局部 automation 的接口思想；它们可被 Codex 路线以较低或中等增量吸收。

### Chosen design and seams

继续采用：

```text
manual / owner scheduler / future ACP trigger
                  │
                  ▼
       single SQLite composition owner
  run/schedule/effect/provider/event/replay/exit
                  │ explicit adapter contract
                  ▼
       Codex 0.139.0 app-server execution loop
                  │
                  ▼
       case-local or separately approved workspace/effect
```

边界规则：

1. 只有一个 durable truth owner；DeepSeek 的 session log、Codex rollout、Provider router 和观测后端都只能作为输入或投影。
2. 只实现需要的 canonical seam：`run_id`、`thread_id`、`turn_id`、`event_id`、`attempt_id`、`effect_id`、`provider_identity`、`replay_mode`、`policy_digest`。
3. scheduler 负责触发，不负责绕过 approval；模型负责提出动作，不负责提交不可逆副作用。
4. Provider retry 与 Provider failover 分开；每次切换必须有 target、reason、capability/degradation 记录。
5. `recorded_view` 不是 replay；`simulated_replay` 不启动工具/Provider；`live_replay` 默认拒绝。
6. ACP 只是一种 transport/interop seam，不能成为第二套 session、effect 或权限 truth。
7. 若需要 DeepSeek 作为实验 adapter，必须使用独立 feature flag、独立 candidate identity 和同一 owner，不进入默认生产路径。

### Compatibility, failure handling, migration and ownership

- **版本兼容**：记录 Harness release、peeled commit、package/binary digest、app-server/ACP schema、adapter、provider profile、policy 和 fixture hash；任一变化触发受影响的 C1–C7 回归。
- **失败处理**：approval/host 边界不可见时 deny/safe-stop；中断后先 reconcile effect，再 bounded retry；Provider 语义不等价时显式降级或停止。
- **迁移**：不把 Codex 的 owner DB 直接解释为 DeepSeek session；若未来切换，先导出 canonical metadata/ledger，做独立 import 和 digest 核对，再在 case-local 运行新 adapter。
- **回滚**：停止新 trigger、禁止 live replay 和危险工具，保留失败 run，恢复最后签核的 Harness/owner schema；未知 effect 不自动重放。
- **退出**：本地退出由 ZWorkbench 冻结 run、停止 schedule/retry、导出最小 metadata、删除本地 state/cache/export；Provider 侧任务、Webhook、备份、retention 和账户由账户 owner/Provider 负责，不能写成 ZWorkbench 已删除远端资源。

## Metrics and experiments

### Current evidence ledger

| Claim | Status | Evidence/source | What it unlocks |
|---|---|---|---|
| Codex can execute the C1 code loop | `observed` | W7 adoption decision；Codex fake-a/b 各 `5/5` | 保留 Codex execution loop |
| DeepSeek can execute the C1 code loop | `observed` | W8 DeepSeek summary；fake-a/b 各 `5/5` | 允许作为挑战者继续比较，不支持切换 |
| Codex composition owner covers C3–C6 contracts | `observed, pass-with-composition` | [`w7-codex-c3-c4-findings.md`](./w7-codex-c3-c4-findings.md)、[`w7-codex-c5-c6-findings.md`](./w7-codex-c5-c6-findings.md) | 允许沿用单 owner 路线 |
| DeepSeek native C3–C6 cover the same contracts | `unknown/partial` | [`w8-deepseek-challenger-evaluation.md`](./w8-deepseek-challenger-evaluation.md) | 不允许用其原生表面替代 owner |
| Codex C7 is fully signed | `unknown-stop` | [`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md)、[`w7-codex-c7-remote-exit-responsibility.md`](./w7-codex-c7-remote-exit-responsibility.md) | 继续处理既有 C7 blocking items |
| DeepSeek C7 is fully signed | `unknown-stop` | `evaluation/evidence/w8-deepseek-c7-20260901/summary.json` | 不引入第二 Harness |

### Candidate experiments and thresholds

这些是下一次确有需求时才执行的增量实验，不是当前批准实现的清单：

| Experiment/scenario | Baseline | Unit | Method | Target/threshold | Owner | Decision unlocked |
|---|---|---|---|---|---|---|
| `E1` cold-session schedule | DeepSeek native C3 scheduler `unknown`；Codex owner trigger已有 composition pass；DeepSeek composition parity `15/15` | cases/effects | 停止 live session，等待/触发一次 schedule，重启 owner/adapter，重复相同 key 三次 | 有效副作用/key=`1`；duplicate extra=`0`；错过触发和暂停状态可解释 | composition owner | 是否吸收 DeepSeek schedule 语义 |
| `E2` DeepSeek→canonical event mapping | DeepSeek ACP/session log 与 composition C3/C4 已有局部事件；native turn identity 未暴露，C6 replay contract unknown | fields/cases | 同一 run 记录 session/run/thread/turn/event/attempt/effect/provider/replay identity，跨进程恢复 | 必需字段完整率 `100%`；未知字段显式保留；状态丢失 `0` | adapter/replay owner | 是否值得增加 ACP adapter |
| `E3` dual Provider failover | DeepSeek timeout 时 fake-b 请求 `0`；Codex composition C5 `19/19` | requests/cases | fake-a 注入 timeout/half-stream，fake-b 成功；三次重复并记录 reason/target | fallback target/reason `100%`；silent semantic change=`0`；危险副作用重复=`0` | Provider owner | 是否存在超出现有 Codex router 的收益 |
| `E4` effect recovery | DeepSeek 候选-owned effect ledger `unknown`；外部 composition effect recovery `24/24` 非 approval 组合通过 | effects/cases | 在 claim、before-commit、after-commit、进程 kill、Provider timeout 六点注入故障 | state loss=`0`；unsafe duplicate=`0`；未知 effect safe-stop；retry≤`1` | composition/policy owner | 是否可让 DeepSeek 进入可恢复写路径 |
| `E5` host/native rejection | Codex native approval/process-tree integration `unknown`；DeepSeek production sandbox `unknown` | cases/denials | 固定工作区外 sentinel、凭证/网络/子进程负向场景，观察真实 request→decision→denial | unauthorized effect=`0`；拒绝链路可观察率 `100%`；缺事件不得算 pass | host/policy owner | 是否关闭真实写入 HOLD |
| `E6` DeepSeek C7 lifecycle | 真人 install/upgrade/restore/diagnosis 均未计时 | minutes/services | 一名操作者按固定 runbook，在 fresh isolated environment 完成安装、升级/回滚、backup/restore、预制故障定位和退出 | install≤`90`；其他各≤`30`；无需额外专家；services≤`3`；source-to-binary provenance可复核 | operations/compliance owner | 是否允许 DeepSeek 重新挑战主 Harness |
| `E7` Codex local absorption | Codex owner C3–C6已有 composition baseline | cases/minutes | 只实现单一增量接口（例如 owner scheduler 或 ACP subset），重跑受影响 C1–C7 | 关键门不回退；新增服务=`0`；人工运维各≤`30`；CBAM收益明确高于成本 | ZWorkbench maintainer | 是否吸收一个具体 DeepSeek 设计 |

### Metrics policy

- 机器 wall time 只记录性能/流程事实；C7 人工分钟必须由操作者 stopwatch 记录。
- 对模型差异记录 provider/model/endpoint/capability，不把“返回 `model=auto`”解释成自动 failover。
- 对未知使用 `unknown`、`unknown-stop` 或 `partial`；未知不是 absent，也不是负分，更不能作为通过。
- 上游 release、app-server/ACP schema、Provider、policy、tool schema、owner schema、replay mode 或依赖变化时，自动重跑受影响 C1–C7。

## Rollout, recovery, and lifecycle

### Rollout stages

1. **Stage 0 — current evaluation**：Codex `0.139.0` + SQLite owner；fake/loopback Provider；继续完成 C4 native/host 和 C7 signoff；DeepSeek 仅保留报告和 evidence。
2. **Stage 1 — selective Codex absorption**：只有一个明确 use case 通过 CBAM 后，增加一个 owner/adapter seam；使用 feature flag、case-local data 和 C1–C7 受影响回归。
3. **Stage 2 — optional DeepSeek lab adapter**：若 E1–E6 的收益证据成立，才在隔离实验 profile 中接入 DeepSeek；不得共享生产 ledger、凭证、外部副作用或默认 Provider 路由。
4. **Stage 3 — production decision**：只有 DeepSeek 的非重复收益超过迁移、升级、回放、权限、C7 和退出成本，才重新评审是否替换或并存；本评审不预先批准该阶段。

### Pause and rollback triggers

- 任意 C2/C4/C6 零容忍项失败，或 native/host 拒绝链路不可观察。
- 状态 digest、effect 状态、Provider target/reason、replay mode 或 event schema 漂移。
- 引入第二 Harness 后维护服务超过 `3`、任何 C7 人工时间超过阈值、需要额外专家或无法完成 backup/restore/退出。
- DeepSeek 或 Codex 的发布 artifact 无法绑定固定源码、依赖、许可证材料或安装内容。
- 发现真实远端任务、Webhook、备份、账单或 retention 责任超出已确认边界。

回滚动作：停止新 schedule/trigger，禁止 live replay 和危险工具，保留故障证据，恢复最后签核的 Codex/owner identity；无法确认 effect 是否提交时 safe-stop，交给人工负责人处理。

### Migration, deprecation, and cleanup

- 不迁移 Harness 内部 session 文件作为工作台 canonical state；只迁移经过 schema 版本化的 owner metadata/ledger，并做独立 restore digest 验证。
- 若 DeepSeek 实验长期没有非重复收益，删除 adapter/profile 和实验依赖前先导出评估摘要、版本 identity、许可证清单和决策记录；不删除历史 evidence。
- 若未来停用 Codex，先冻结触发和副作用，完成 provider/account inventory、导出与独立导入，再逐项撤销本地和外部资源；远端删除必须由账户/Provider 责任人执行并记录结果。

## Principle considerations

### Performance

本评审没有足够数据证明 DeepSeek 或 Codex 的 token、延迟、吞吐、内存和功耗优劣。DeepSeek 的 session-local scheduler 可能减少一次外部唤醒，但 live-session 依赖可能增加恢复和常驻成本；Codex + owner 的外部协调可能增加启动/存储开销。任何性能结论必须在固定模型、Provider、fixture、机器和重复次数下测量 wall time、token、fallback 次数、owner DB 增长和人工介入率；性能收益不能抵消安全、恢复和退出门失败。

### Simplicity and accessibility

保持一个主 Harness 和一个 owner，能让个人开发者只学习一套执行循环和一套状态/排障责任；代价是 owner 成为 scheduler、Provider、replay 和退出的集中责任点。引入第二 Harness 会把“选择哪个运行时”暴露给用户，并增加版本、错误码和数据迁移概念。CLI/日志中的未知、safe-stop、降级原因和恢复步骤应使用可读文本与脱敏 JSON 同时提供；当前不需要为完整 DeepSeek 生态增加额外 UI。

### Security and privacy

威胁面包括模型生成命令、插件/MCP、workspace 外文件、网络、凭证、Provider 请求、Git/deploy、重试和 replay 误执行。DeepSeek 官方固定版本安全说明本身不把 sandbox 视为 production-ready；Codex 的 native approval/process-tree integration 也尚未关闭 unknown。因此任何候选都必须由 composition policy + host boundary 负责 fail-closed，不能把 adapter 层的 deny 当成宿主隔离。

真实 Provider 请求可能包含源码、prompt、output、日志、任务、Webhook 和备份。ZWorkbench 只保存必要的 Provider identity/fingerprint，不保存 API key 值；本地退出与 Provider 侧账户/数据/retention 分开记账。当前已确认的火山方舟个人账户及其远端数据、任务、Webhook、备份属于账户 owner/Provider 的外部责任，不是本评审可代签的本地删除证据。

## Testing and validation

| 层 | 场景/fixture | 当前结果 | 证据 | 放行含义 |
|---|---|---|---|---|
| C1 | 共同代码项目、fake-a/fake-b、理解—修改—测试 | Codex `10/10` smoke；DeepSeek `10/10` smoke | W7 adoption decision；W8 DeepSeek challenger evaluation | 两者均可作为执行循环候选 |
| C2 | 未授权命令、越界写入、secret/网络负向路径 | Codex composition/adapter path pass；native/host unknown；DeepSeek adapter `6/6` | W7 C2/C4 文档；W8 C2 evidence | 只放行隔离 adapter 合同，不放行真实写 |
| C3 | 重复 trigger、进程重启、幂等 sink、暂停/恢复 | Codex `15/15 pass-with-composition`；DeepSeek 同形状 `15/15 pass-with-composition`，但 native scheduler unknown | W7 C3/C4；W8 C3 parity evidence | 继续使用单一 owner |
| C4 | cancel、process kill、Provider/tool 故障、effect claim/commit/reconcile | Codex `36/36 pass-with-composition`；DeepSeek `24/36` composition pass、`12/36` approval unknown、无 fail | W7 C4；W8 C4 parity evidence | Codex composition 可继续；DeepSeek 不可替代 |
| C5 | fake-a timeout/half-stream → fake-b fallback | Codex `19/19 pass-with-composition`；DeepSeek 只同路由 retry | W7 C5/C6；W8 C5 parity evidence | 不把任一 Harness 的 retry 叫 failover |
| C6 | recorded view、cassette simulated、default-deny live replay | Codex `15/15 pass-with-composition`；DeepSeek session log/resume `5/5`，replay contract unknown | W7 C5/C6；W8 C6 parity evidence | 保留 owner canonical replay contract |
| C7 | fresh install、upgrade/rollback、owner backup/restore、故障定位、exit | Codex 多项人工和 owner-backed machine evidence，但整体 signoff-open；DeepSeek `unknown-stop` | W7 C7 findings；W8 C7 summary | 任何切换/并存前必须重跑 |
| ATAM/CBAM | 成本、服务数量、迁移、许可证、远端责任和退出 | 当前无第二 Harness 的非重复收益证据 | W7 adoption decision；本评审 | 维持 `no-change` |

### Validation exit rules

- `pass-with-composition` 必须列出 composition owner、adapter identity 和受影响的 C1–C7 evidence；不能写成 native pass。
- 任一关键字段缺失、未授权动作、危险副作用重复、状态丢失、silent provider switch、未批准 live effect 或 artifact provenance 漂移，结果为 `fail` 或 `unknown-stop`，不能用其他场景平均值抵消。
- 如果只验证接口或源码存在，结果最多是 `source capability` 或 `partial`；只有端到端 fixture 和阈值满足后才是 `pass`。

## Open decisions

| Question | Evidence needed | Owner | Due/exit condition |
|---|---|---|---|
| ZWorkbench 是否需要 ACP client 互操作，而不仅是内部 app-server？ | 一个具体调用方、消息/事件子集和失败语义；完成 E2 | 产品/adapter owner | 没有具体调用方则不增加 ACP adapter |
| 首批自动任务需要哪些 scheduler 语义？ | 时区、错过触发、并发、暂停、重试、幂等和唤醒场景；完成 E1 | composition owner | 先冻结最小 C3 合同，再决定实现规模 |
| Codex 的 native approval/process-tree integration 如何关闭？ | 可观察的真实 request→decision→denial/effect 链路；完成 E5 | host/policy owner | 未关闭前真实写操作继续 HOLD |
| 是否存在必须使用 DeepSeek 才能获得的代码任务收益？ | 同一任务集、固定 Provider/成本、C1 通过率和人工介入对照；非重复收益需超过新增 C7/迁移成本 | 评测 owner | 没有可重复优势则保持 `no-change` |
| 是否要把 DeepSeek 保留为可选实验 adapter？ | E1–E6 的 candidate-level evidence、固定版本和退出 runbook | 个人负责人 | 任一 C2/C4/C7 hard gate unknown 则不进入生产 |
| Codex C7 NOTICE/商业/远端责任何时签核？ | 逐包 NOTICE、适用使用模式、Provider 数据/账户责任和退出记录 | supply-chain/compliance + 账户 owner | 责任人签字和证据齐全前保持 `unknown-stop` |

## Review record

| Reviewer | Date | Concern | Response or decision | Remaining risk |
|---|---|---|---|---|
| Codex agent draft | 2026-09-01 | “DeepSeek 有更多模块，是否应直接替换 Codex？” | 模块数量不是 C1–C7 合同；DeepSeek C3–C7 未形成可签核证据，保留 Codex 主线 | DeepSeek 可能在未覆盖的专长任务上有收益，需有具体任务集才重开 |
| Codex agent draft | 2026-09-01 | “Codex 是否必须复制 DeepSeek 的插件/ACP/agent-team 设计？” | 只吸收有明确用户需求且能归入单一 owner 的局部 seam；完整生态兼容为 `H/VH`，当前不做 | ACP 需求和并行团队需求尚未由产品任务确认 |
| Codex agent draft | 2026-09-01 | “已有 composition pass 是否能覆盖 DeepSeek 原生能力？” | 不能。所有 `pass-with-composition` 保留 owner/adapter 标签，DeepSeek native C3–C7 仍 unknown/partial | 未来 adapter 仍需独立版本、事件和退出回归 |
| Human reviewer | 待评审 | 是否接受 `defer/no-change` 与 E1–E7 重开条件 | 待 Human 确认 | 在确认前不改变路线图和生产边界 |

### Short-read acceptance

当前决定：**暂缓 DeepSeek 替换或并存，Codex + 单一 SQLite composition owner 继续作为主线。**

当前 blocking findings：Codex native/host approval unknown；Codex C7 NOTICE/商业/远端责任 signoff-open；DeepSeek 完整 C4–C7 未签核。下一验证动作：继续处理 Codex 既有 C4/C7 阻断项；只有出现一个明确、可测量且非重复的 DeepSeek 优势时，才执行对应的 E1–E7，并要求 C1–C7 硬阈值、服务数 ≤`3`、人工运维阈值和退出责任全部满足。

本评审的证据来源包括：[`w8-deepseek-challenger-evaluation.md`](./w8-deepseek-challenger-evaluation.md)、[`w7-codex-atam-cbam-adoption-decision.md`](./w7-codex-atam-cbam-adoption-decision.md)、[`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md)、[`w7-codex-c7-remote-exit-responsibility.md`](./w7-codex-c7-remote-exit-responsibility.md)、[`w6-fixtures-and-thresholds.md`](./w6-fixtures-and-thresholds.md)、[`w2-named-harnesses.md`](./research/w2-named-harnesses.md)。
