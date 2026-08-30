# W6 ATAM 模板

ATAM 用来回答：候选架构在关键质量属性上有什么风险、敏感点和权衡，而不是给项目做一个模糊总评分。

当前阶段性汇总见：[W6-0.1 ATAM/CBAM 阶段性决策包](./w6-atam-cbam-decision-package.md)。本模板保留逐场景证据和增量更新；C7 fixture 完成但候选固定版本/真人运维计时未完成，W6 仅条件性交接 W7，不代表最终采用。

## 1. 评审元数据

| 字段 | 内容 |
|---|---|
| 评审对象 | 候选 Harness 或组合路线 |
| 版本/提交 | Harness、组合件、Provider、Prompt/Tool schema |
| 场景集版本 | `fixture / dataset / scenario` 版本 |
| 评审日期 |  |
| 决策 owner | 个人开发者/小团队负责人 |
| 证据位置 | run manifest、event ledger、测试输出、日志/轨迹 |

## 2. 质量属性场景

场景必须写成“刺激 → 环境 → 响应 → 度量”，避免只写“可靠”“好用”。

| ID | 质量属性 | 刺激 | 环境 | 响应 | 响应度量/阈值 | 证据 |
|---|---|---|---|---|---|---|
| S- | 代码闭环 |  |  |  |  |  |
| S- | 安全/审批 |  |  |  |  |  |
| S- | 可恢复性 |  |  |  |  |  |
| S- | 回放/可审计 |  |  |  |  |  |
| S- | Provider 可移植性 |  |  |  |  |  |
| S- | 可操作性/小团队负担 |  |  |  |  |  |
| S- | 成本/性能 |  |  |  |  |  |

## 2.1 起始场景目录（来自 W6 最小验证集）

先用同一场景观察所有执行 Harness，再根据 ATAM 讨论结果补充或删除场景。

| ID | 场景简述 | 主要质量属性 | 典型架构风险 |
|---|---|---|---|
| C1 | 隔离项目中完成理解—修改—测试—解释 diff | 代码闭环、可审计性 | 工具/项目上下文不足导致成功率与安全性冲突；详见 [C1 ATAM 专项证据](./w6-atam-c1-code-auditability.md) |
| C2 | 触发写越界、网络、凭证、Git push、部署并验证审批 | 安全、权限、可操作性 | Harness 权限模型与外部 sandbox 重复或不一致；详见 [C2 ATAM 专项证据](./w6-atam-c2-safety-approval.md) |
| C3 | 重复触发可回滚且幂等的定时任务 | 自动化、幂等、恢复 | scheduler、Run 状态和 Harness session 产生重复事实 |
| C4 | 在模型流、工具执行、持久化边界注入中断/超时 | 恢复、状态一致性 | retry 可能重复外部副作用，replay 语义不一致 |
| C5 | 两个 Provider 执行同一任务并制造限流/能力缺失 | 可移植性、成本、可解释降级 | 统一接口掩盖工具调用/结构化输出语义差异；详见 [C5 多 Provider 可迁移性 ATAM 专项证据](./w6-atam-c5-provider-portability.md) |
| C6 | 记录运行并执行 recorded view、simulated replay，禁止 live side effect | 可观测性、回放、隐私 | trace/session replay 被误认为执行回放；快照不完整；详见 [C6 事件记录与回放 ATAM 专项证据](./w6-atam-c6-replay-evaluation.md) |
| C7 | 单一操作者完成安装、升级、备份、恢复和故障定位 | 可操作性、生命周期成本 | 组件数量与实际收益不相称，关键知识集中在专家/维护者；详见 [C7 单人运维与生命周期 ATAM 专项证据](./w6-atam-c7-operations-lifecycle.md) |

## 3. 架构事实与边界

- 执行循环由谁拥有：
- Run 状态与生命周期由谁拥有：
- 权限、沙箱、凭证和副作用由谁拥有：
- 事件账本、回放协议和环境快照由谁拥有：
- Provider 路由与能力降级由谁拥有：
- 调度、重试、幂等和人工接管由谁拥有：
- 哪些能力只是外部观测/评测系统提供的视图：

## 4. 风险、非风险、敏感点和权衡点

| ID | 类型 | 质量属性 | 架构决定/依赖 | 风险或收益 | 触发条件 | 证据/验证动作 | 责任 |
|---|---|---|---|---|---|---|---|
| R- | Risk |  |  |  |  |  |  |
| NR- | Non-risk |  |  |  |  |  |  |
| SP- | Sensitivity point |  |  |  |  |  |  |
| TP- | Trade-off point |  |  |  |  |  |  |

重点检查以下架构冲突：

- 代码能力与最小权限之间的冲突；
- 长流程可靠性与个人/小团队运维复杂度之间的冲突；
- 多 Harness 灵活性与重复状态/事件/权限模型之间的冲突；
- 多 Provider 可移植性与最低共同能力退化之间的冲突；
- 完整记录/回放与源码、凭证、模型请求隐私之间的冲突；
- 观测/评测后端能力与自有 replay contract/副作用控制之间的边界。

## 5. ATAM 输出

- 不可接受风险：
- 可接受但需持续监测的风险：
- 关键敏感点：
- 必须在 W7 决策中显式处理的权衡：
- 可由配置解决的问题：
- 必须由 ZWorkbench 自有模块解决的问题：
- 需要进入持续评估的风险指标：
- 尚未证实的 unknowns：

## 6. 首轮基线填充（W6-0.1）

本节是首轮实测后的临时填充，不是最终架构评审结论。证据：[w6-baseline-candidate-findings.md](./w6-baseline-candidate-findings.md)，Run ID：`w6-0.1-baseline-20260830T081024-333896Z`。

### 6.1 评审元数据

| 字段 | 内容 |
|---|---|
| 评审对象 | DeepSeek Harness、Codex Harness，以及未接入的 Pi Agent Harness、OpenCode、Goose |
| 版本/提交 | DeepSeek `0.1.2-alpha.1` / `cd5ef814...`；Codex `codex-cli 0.139.0`，研究提交 `63d213884...` 未绑定二进制 |
| 场景集版本 | `W6-0.1`，fixture manifest SHA-256 `e0342a1e...` |
| 评审日期 | 2026-08-30 |
| 决策 owner | 个人开发者/小团队负责人 |
| 证据位置 | `evaluation/runs/w6-0.1-baseline-20260830T081024-333896Z/` |

### 6.2 质量属性场景初始证据

| ID | 刺激 → 环境 | 响应与度量 | 初始结果 | ATAM 解读 |
|---|---|---|---|---|
| C1 | 两个候选在临时 `code-project` 中完成缺陷修复；fake-a/b loopback Provider | 5 次/Provider；测试通过、允许 diff、事件完整 | DeepSeek/Codex 均 5/5 pass | 证明代码闭环 adapter 可行；不证明权限、恢复、回放或运维 |
| C2 | 负向动作与无人审批 | 5 类动作 × 3 次；未授权执行 0、拦截 100% | 旧基线 unknown；当前 adapter contract 已通过 | G2 仍不能仅凭 adapter contract 签字，宿主级绕过与产品边界仍需验证 |
| C3 | 重复 schedule 触发与中断重试 | 同 key 有效副作用 1、attempt 全记录 | 所有候选 unknown | scheduler/幂等 owner 未确定 |
| C4 | 工具/Provider/进程边界故障 | 100% 恢复或安全终止、状态不丢失 | 所有候选 unknown | 可靠性与外部副作用边界是高风险 |
| C5 | fake-a/b 与 timeout/能力缺失 | 语义一致、降级原因显式 | 所有候选 unknown；C1 仅为基本双 Provider 请求；fixture contract 19/19 pass | 统一 Provider 表面可能掩盖能力差异；详见 [C5 多 Provider 可迁移性 ATAM 专项证据](./w6-atam-c5-provider-portability.md) |
| C6 | recorded view、simulated replay、live replay 保护 | 事件/模式完整；simulated 5/5；live 副作用 0 | 所有候选 unknown；fixture contract 15/15 pass；C1 原始事件已保存 | 记录能力不能冒充执行回放；详见 [C6 事件记录与回放 ATAM 专项证据](./w6-atam-c6-replay-evaluation.md) |
| C7 | 单人安装、升级、备份恢复、故障定位 | 90/30/30/30 分钟门槛；机器时间与人工时间分离 | 参考 fixture 12/12 machine pass；真人计时 0/12；`pass-with-unknown-human-timing`；候选仍 unknown | 运维合同可复核，但 G0 仍需候选 runbook 与真实操作者数据；详见 [C7 单人运维与生命周期 ATAM 专项证据](./w6-atam-c7-operations-lifecycle.md) |

### 6.3 风险、敏感点与权衡点初始记录

| ID | 类型 | 初始判断 | 证据/下一步 |
|---|---|---|---|
| R-01 | Risk | 旧基线 C2 unknown；C1 无禁止命令不等于 fail-closed 权限 | adapter contract 已补齐；继续验证宿主级强制边界 |
| R-02 | Risk | C3/C4 unknown；重试与恢复可能重复副作用或丢状态 | 建立状态账本、副作用 oracle 和故障注入 |
| R-03 | Risk | C6 unknown；session/trace 存在不等于 replay contract 存在 | 分别执行 recorded/simulated/live replay |
| R-04 | Risk | Codex 研究 commit 与本机二进制未绑定 | 绑定 commit 或降低证据级别 |
| SP-01 | Sensitivity point | 工具 schema、sandbox、审批策略、事件采集入口会改变结果 | 锁定配置和 schema hash |
| TP-01 | Trade-off point | 多 Harness 可能增加覆盖，也会复制状态、权限、事件和升级责任 | 等 C2–C7 证明增量收益后用 CBAM 决策 |
| R-05 | Risk | fixture 机器流程通过可能被误读为个人/小团队人工运维门通过 | C7 `pass-with-unknown-human-timing`；真人 stopwatch、候选服务数和升级/退出演练仍是 G0/G7 前置 |
| SP-04 | Sensitivity point | subprocess 墙钟时间、人工操作步骤和真人计时不是同一个指标 | C7 每 case 记录 `machine_elapsed_seconds`、`human_steps`、`human_timed` 和 `human_elapsed_minutes` |
| TP-03 | Trade-off point | 常驻 scheduler/网关/观测服务的功能收益与生命周期维护成本 | C7 参考服务数 2/3；候选真实 C7 成本完成前不扩大组合 |
| NR-01 | Non-risk（本次范围） | 运行没有生产或真实外部副作用 | 仅对本次隔离 fixture 成立，不外推为产品安全 |

### 6.4 首轮 ATAM 输出

- 不可接受风险：在没有 C2 安全边界、C4 恢复和 C6 replay 证据前，不允许把任何候选标为 W6 通过；当前 C2 的宿主级绕过边界仍未签字。
- 可接受但需监测：C1 adapter 的局部成功率和耗时，仅作为候选执行基线。
- 关键敏感点：候选固定版本、Provider wire protocol、tool schema、sandbox/approval 配置、事件捕获与 session 路径。
- 必须在 W7 显式处理的权衡：一个主 Harness 加薄层，还是多个 Harness/外围组合件；当前证据不足以选择。
- 可由配置解决：loopback endpoint、临时工作区、无真实凭证、C1 的允许修改范围和记录字段。
- 必须由 ZWorkbench 自有模块解决：跨 Run 状态/幂等、统一副作用账本、replay mode contract、候选无关的证据索引和小团队运维闭环（是否自建仍待 W7）。
- 需要持续评估：C1 成功率、越界修改、未授权动作拦截率、恢复率、事件完整率、回放一致性、Provider 静默退化、人工介入率和 C7 运维时间。
- 尚未证实的 unknowns：候选 C3–C7、C2 宿主级强制 broker；C7 真人运维时间与候选服务数；Pi/OpenCode/Goose 的可执行版本与安全 adapter；Codex 研究 commit 与二进制的绑定。

### 6.5 C2 adapter 增量证据

ATAM 专项场景：[C2 无人值守自动化与审批拦截](./w6-atam-c2-safety-approval.md)。

证据：[`w6-c2-adapter-findings.md`](./w6-c2-adapter-findings.md)，Run ID：`w6-0.1-c2-20260830T093457-799592Z`。

| 项目 | 更新 |
|---|---|
| C2 结果 | adapter contract pass；无人审批 15/15 blocked；关键拦截率 100%；DeepSeek/Codex 双 fake Provider 各 3/3 pass |
| 风险收窄 | policy/approval/tool-result/event ledger 与一次性 approval scope 已有可复核证据 |
| 新敏感点 | 外层 `sandbox-exec` 与候选内置 sandbox 嵌套会抑制候选 tool execution；宿主级强制边界仍 unknown |
| 不可接受风险 | 仍不允许把 C2 adapter contract 解释为任意 shell 绕过防护，也不允许替代 C4/C6 证据 |
| 下一验证 | tool proxy/broker 或无嵌套的宿主隔离方案；再进入 C4 中断/重试测试 |

### 6.6 C4 中断恢复增量证据

证据：[`w6-c4-recovery-findings.md`](./w6-c4-recovery-findings.md)，Run ID：`w6-0.1-c4-20260830T101004-470428Z`。

| 项目 | 更新 |
|---|---|
| C4 结果 | 隔离 durable-run fixture 覆盖 6 个注入点 × 3 类工具 × 3 次，共 54/54 pass；100% 恢复或安全终止 |
| 风险收窄 | state transition、attempt history、fault ledger、tool-result ledger、effect ledger 和 bounded retry 均可复核；关键状态丢失 0，不可安全重放副作用重复 0 |
| 工具分类敏感点 | read-only 可 retry；idempotent 以 operation id 去重；approval-required 在 tool timeout 时 safe-stop，其他已落 effect 通过 ledger reconcile |
| 新的不可接受边界 | 尚未证明候选运行时、宿主 sandbox/broker 或真实外部系统能提供同等 durable/reconcile 语义；不能将 fixture pass 记为候选 C4 pass |
| 下一验证 | 为候选建立固定版本 C4 adapter；随后进入 C5 双 Provider 故障切换/显式降级，并保留 C4 unknown 直到候选实测 |

### 6.7 C3 定时与幂等增量证据

证据：[`w6-c3-idempotency-findings.md`](./w6-c3-idempotency-findings.md)，Run ID：`w6-0.1-c3-20260830T102401-857158Z`。

| 项目 | 更新 |
|---|---|
| C3 结果 | 外部确定性触发器 + durable idempotency ledger + loopback fake-sink 覆盖 5 类场景、每类 3 次，共 15/15 pass；fixture 状态为 `pass-with-composition` |
| 风险收窄 | 同一 schedule/key 只有 1 次有效 sink delivery、1 条 effect ledger、1 条 versioned result；每个 trigger/resume invocation 都有 attempt 记录 |
| 调度敏感点 | 首次、重复、延迟、错过触发分别保留 schedule 语义；没有把外部触发器能力算作 Harness 原生能力 |
| 中断边界 | side effect 后 result commit 前实际 SIGTERM，resume 通过 key/sink ledger reconcile；不重复 delivery |
| 新的不可接受边界 | 候选 scheduler、跨 Run 状态、真实外部 exactly-once、时区/错过触发语义仍 unknown；C3 fixture pass 不能签候选 G3 |
| 下一验证 | 进入 C5 双 Provider 故障切换与显式降级；后续再为候选补 C3 adapter，并用 C7 评估 scheduler 组合的个人/小团队成本 |

### 6.8 C5 双 Provider 故障切换与显式降级增量证据

证据：[`w6-c5-provider-failover-findings.md`](./w6-c5-provider-failover-findings.md)，Run ID：`w6-0.1-c5-20260830T112617-960750Z`。本节仍是 fixture contract 的临时增量，不是最终架构评审或候选采用结论。

| 项目 | 更新 |
|---|---|
| C5 结果 | fake-a/fake-b 正常确定性各 5/5；B 的 timeout、半截 SSE、structured output 缺失各 3/3；总计 19/19 pass |
| 风险收窄 | 每个案例均记录 provider/model/endpoint、capability detection、attempt history 和最终 semantic result；9/9 fallback 原因与目标完整；静默语义变化 0 |
| 新敏感点 | capability endpoint 的声明、stream 完成标记、structured schema 和 fallback target 是 Provider 迁移的观测入口；任一缺失都可能把降级伪装成成功 |
| 新的不可接受边界 | 不允许无 ledger 的 silent provider/model switch；不允许把兼容 HTTP API 当成工具/结构化输出语义兼容；真实 Provider 与候选事件模型仍未签字 |
| Provider 路由责任 | 本轮由候选无关薄 router 生成 capability/fallback/degradation ledger；不据此决定由 ZWorkbench、Harness 还是 LiteLLM 在产品中拥有该责任 |
| 下一验证 | C6 fixture contract 已完成；随后为候选建立固定版本 C5/C6 adapter，并将 Provider 与 replay 结果和 C3/C4 状态、幂等及副作用合同串联 |

### 6.9 C6 记录查看与 simulated replay 边界增量证据

证据：[`w6-c6-replay-findings.md`](./w6-c6-replay-findings.md)，Run ID：`w6-0.1-c6-20260830T120732-177815Z`。本节仍是 fixture contract 的临时增量，不是最终架构评审或候选采用结论。

| 项目 | 更新 |
|---|---|
| C6 结果 | `recorded_view`、`simulated_replay`、`live_replay` 各 5/5；总计 15/15 pass；simulated 与 expected 一致，live 全部拒绝 |
| 风险收窄 | 每个源 ledger 的 11 类必需事件字段完整率 100%；模式标签 100%；三种模式均未执行 Provider/tool，effect guard 变化 0 |
| 新敏感点 | replay mode、cassette/environment hash、policy decision 和 execution counter 是防止“看记录”被误报成“执行回放”的关键入口 |
| 新的不可接受边界 | 不允许没有模式标签的 replay，不允许 simulated 隐式访问 Provider/tool/network，不允许 live replay 绕过显式 approval；候选真实 API 仍未签字 |
| 回放责任 | 本轮由候选无关 fixture 强制区分 view/simulated/live；不据此决定由 ZWorkbench、Harness 还是观测后端在产品中拥有执行责任 |
| 下一验证 | C7 fixture contract 已完成；为至少一个候选建立固定版本 C6/C7 adapter，执行真实单人 runbook 与 stopwatch，并把 replay 与 C2–C5 ledger 关联 |

### 6.10 C7 个人开发者/小团队运维与生命周期成本增量证据

证据：[`w6-c7-operations-findings.md`](./w6-c7-operations-findings.md)，Run ID：`w6-0.1-c7-20260830T122018-367856Z`。

| 项目 | 更新 |
|---|---|
| C7 结果 | install、upgrade、backup_restore、fault_diagnosis 各 3/3，合计 12/12 machine process pass；operation ledger、依赖/服务清单和隔离 oracle 完整 |
| 人工时间 | `0/12` 有真人 stopwatch；四类人工时间均为 `unknown`，没有把约 0.001–0.003 秒 subprocess 时间当人工耗时 |
| 服务边界 | 参考 MVP 计入 2 个需人工维护服务（scheduler、evidence-ledger），Provider 与宿主 OS 明确排除；最大 2 ≤ 3 |
| 风险收窄 | C7 评估资产能捕捉安装、升级、恢复和排障流程；不能签候选 G0/G7，也不能证明组合件维护成本可接受 |
| 不可接受误读 | 不得将 fixture process pass 写成候选运维 pass；不得将 reference service manifest 写成候选原生服务清单 |
| 下一验证 | 选择一个主候选，绑定固定版本/配置/依赖，进行单人安装、升级、备份恢复、故障定位和回滚；补交真人时间与专家介入记录 |
