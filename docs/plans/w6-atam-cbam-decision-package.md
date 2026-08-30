# W6-0.1 ATAM/CBAM 阶段性决策包

状态：阶段性决策包 · `acceptance/evaluation` · W6 最终采用 `not-signed-off`，已形成条件性 W7 交接 · 不是 ZWorkbench 产品实现方案

本文件把 W6 当前证据转换为可复核的架构风险、成本收益和下一步门槛。评估对象是 DeepSeek Harness、Pi Agent Harness、Codex Harness、OpenCode、Goose 及必要组合件；约束对象是个人开发者或小团队。方法组合为 ATAM（质量属性、风险、敏感点、权衡点）+ CBAM（场景收益、风险降低、一次性/持续/迁移成本）+ 自动化持续评估。

## 1. 阶段性结论

当前不做 W7 最终采用，也不宣布任何候选通过。W6 的 signoff disposition 是
`conditional-handoff`：证据合同已经形成，但候选固定版本与真人运维证据尚不足。
暂时保留以下路线假设：

> 一个主 Harness + 必要薄层；薄层只拥有被证据明确要求的跨运行合同和治理边界。

这不是“从零自建整个工作台”的授权，也不是“多个开源项目拼盘”的默认选择。当前应优先证明一个主 Harness 能否被薄安全层、状态/幂等层、Provider contract 和 replay contract 安全包住；第二 Harness、LiteLLM、Temporal/LangGraph、外部观测后端只有在产生非重复的关键收益、且通过个人/小团队成本门槛后才可引入。

阶段性决策的硬边界：

- C1–C6 fixture contract 的通过只能收窄协议和评估设计风险，不能改写候选 C1–C6 状态；没有固定版本候选 adapter 的候选继续为 `unknown`。
- C7 fixture 已完成但真人运维计时和候选固定版本演练仍未完成；在此之前不做最终主 Harness、组合件或多 Harness 排序。
- 任何 Provider/model/endpoint 的切换必须留下 capability、attempt、reason、target 和 semantic result；无 ledger 的静默切换视为硬失败。
- 任何不可逆外部副作用、真实凭证、生产项目和真实 Provider 都不进入本地 W6 可复现基线。

## 2. 证据账本

| 场景 | 当前 artifact | 结果 | 能回答的问题 | 不能回答的问题 |
|---|---|---|---|---|
| C1 代码闭环 | 首轮候选 adapter + `code-project` | DeepSeek/Codex fake-a/b 各 `5/5 pass`；其余候选 unknown | 候选接入和代码任务 oracle 可行 | 不证明权限、恢复、回放、运维或产品可发布 |
| C2 fail-closed | [`w6-c2-adapter-findings.md`](./w6-c2-adapter-findings.md)；Run `w6-0.1-c2-20260830T093457-799592Z` | fixture/adapter 首轮通过；五类危险动作 × 3 次无人审批阻断 | 安全 ledger、审批 scope 和负向 oracle 的合同形状 | 不证明宿主级绕过不可行；候选 C2 仍需边界 adapter |
| C3 调度/幂等 | [`w6-c3-idempotency-findings.md`](./w6-c3-idempotency-findings.md)；Run `w6-0.1-c3-20260830T102401-857158Z` | `15/15 pass-with-composition` | 外部 trigger + key/effect/result ledger 可形成幂等合同 | 不证明 Harness 原生 scheduler、真实 exactly-once 或 C7 成本 |
| C4 恢复/副作用 | [`w6-c4-recovery-findings.md`](./w6-c4-recovery-findings.md)；Run `w6-0.1-c4-20260830T101004-470428Z` | `54/54 pass` | durable state、bounded retry、reconcile、safe-stop 的合同形状 | 不证明候选/宿主/真实外部系统已提供同等语义 |
| C5 Provider 迁移 | [`w6-c5-provider-failover-findings.md`](./w6-c5-provider-failover-findings.md)；Run `w6-0.1-c5-20260830T112617-960750Z` | `19/19 pass`；正常 A/B 各 `5/5`；故障各 `3/3` | capability detection、显式 fallback、语义 oracle 和 loopback evidence 的合同形状 | 不证明候选 Provider adapter、LiteLLM、成本、凭证和生产质量 |
| C6 记录/回放 | [`w6-c6-replay-findings.md`](./w6-c6-replay-findings.md)；Run `w6-0.1-c6-20260830T120732-177815Z` | `15/15 pass`；三种模式各 `5/5` | recorded view、cassette-only simulated replay 和 fail-closed live replay 的合同形状 | 不证明候选 replay API、环境重建、脱敏、存储和 live 安全 |
| C7 生命周期 | [`w6-c7-operations-findings.md`](./w6-c7-operations-findings.md)；Run `w6-0.1-c7-20260830T122018-367856Z` | `12/12` machine process pass；human timing `unknown` | 参考服务数 2、证据格式和测量边界已固定 | 不能凭 fixture runner 时长外推人工运维成本，候选仍 unknown |

### 2.1 证据等级规则

| 等级 | 含义 | W7 用法 |
|---|---|---|
| `measured-candidate` | 候选固定源码/版本、配置、Provider、adapter 和原始证据均绑定 | 可以进入候选门槛判断 |
| `fixture-contract` | 候选无关隔离 fixture 达到合同阈值 | 只用于设计 oracle、收窄协议风险和指导 adapter |
| `pass-with-composition` | 由外部轻量组合件满足合同，非 Harness 原生能力 | 必须单独计算组合成本，不能改写原生能力 |
| `unknown` | 版本、边界或证据缺失 | 关键硬门槛上保持不通过/待验证 |

本批次的 C2–C6 主要是 `fixture-contract`，C3 还带有 `pass-with-composition`；候选总体不能因这些结果改变为 `pass`。

## 3. G0–G7 硬门槛状态

| 门槛 | 当前状态 | 阻断原因 | 放行所需证据 |
|---|---|---|---|
| G0 个人/小团队可操作性 | `unknown` | 只有候选无关 fixture machine process；`0/12` 真人计时 | 候选固定版本单人演练：安装/升级/备份恢复/排障时间、服务数、无需专家介入 |
| G1 代码任务安全闭环 | `partial` | DeepSeek/Codex 有 C1，其他候选未接入 | 每个候选固定版本 adapter；成功率、测试、diff、事件和越界修改 |
| G2 危险操作边界 | `fixture pass / candidate unknown` | 宿主级强制 broker 和 sandbox 嵌套边界未签字 | 候选真实工具入口的 fail-closed 负向测试 |
| G3 失败与恢复 | `fixture pass-with-composition / candidate unknown` | C3/C4 没有候选原生状态和副作用 adapter | 候选固定版本中断/重试/幂等/人工接管证据 |
| G4 可审计性 | `partial` | fixture ledger 完整，候选事件映射未证实 | 关键输入、版本、工具、权限、状态、错误和 artifact 关联完整 |
| G5 回放边界 | `fixture pass / candidate unknown` | 候选 replay API、环境重建和宿主副作用边界未签字 | 候选固定版本三模式 contract、事件/环境/cassette 关联、live fail-closed 证据 |
| G6 Provider 可移植性 | `fixture pass / candidate unknown` | C5 仅是候选无关 router | 候选双 Provider adapter、能力协商、语义一致和成本证据 |
| G7 生命周期与所有权 | `unknown` | C7 仅覆盖参考文件流程；候选许可证、升级/退出和真实维护责任未测 | 版本绑定、许可证边界、回滚、备份兼容和维护责任 |

结论：G0、G7 仍是明显的决策阻断项；G2/G3/G5/G6 虽已有 fixture 证据，但候选层不能签字。阶段性包不提供综合分，避免未知项被平均分掩盖。

## 4. ATAM 视图

### 4.1 质量属性场景

| 场景 | 刺激 → 环境 | 响应与度量 | 当前判断 |
|---|---|---|---|
| 安全 | 未授权写入、凭证、外网、push、deploy；隔离 workspace | 100% 阻断或显式审批，side-effect ledger 可解释 | fixture 已验证；宿主和候选边界仍 unknown |
| 恢复 | Provider/tool/process 在不同 checkpoint 中断 | 恢复或 safe-stop 100%，retry 有界，副作用不重复 | fixture 已验证；候选接入未验证 |
| Provider | B timeout、半截流、能力缺失 | 显式 reason/target，最终语义匹配，静默变化 0 | fixture 已验证；真实 schema/成本未验证 |
| 回放 | 查看记录、模拟 replay、live replay | 模式标签正确，模拟不产生副作用，live 默认禁止 | fixture 15/15 pass；候选接入未验证 |
| 可操作性 | 单人从干净环境完成安装、升级、备份和排障 | 90/30/30/30 分钟门槛，常驻服务 ≤3；机器时间不替代人工时间 | fixture 12/12 machine pass；真人时间 unknown |

### 4.2 风险、敏感点与权衡点

| ID | 类型 | 判断 | 触发条件 | 处理/责任 |
|---|---|---|---|---|
| R-01 | Risk | C1 成功可能掩盖权限、恢复和回放缺口 | 只凭代码任务选择主 Harness | C2–C7 逐项过门；候选状态不外推 |
| R-02 | Risk | 重试或 fallback 造成重复外部副作用或语义漂移 | Provider/tool 失败、跨进程 resume、重复 trigger | 统一 attempt/effect/result ledger；绑定 side-effect class |
| R-03 | Risk | 宿主 sandbox、候选 sandbox 和薄层互相覆盖或出现绕过 | 嵌套 sandbox、tool proxy/broker、审批配置变化 | 先做候选边界 adapter；失败则暂停组合扩展 |
| R-04 | Risk | C6 把 trace/session view 错当执行 replay | 记录能看但不能重建环境/副作用边界 | C6 强制区分 recorded/simulated/live，live 默认禁止 |
| R-05 | Risk | C7 机器流程通过可能被误读为个人开发者可承受的人工运维成本 | 常驻服务、升级、备份、排障需要专家；真人时间缺失 | 保留 human timing unknown；以候选单人 stopwatch、服务数、退出路径签 G0/G7 |
| SP-04 | Sensitivity point | subprocess 墙钟、操作步骤和真人计时是不同测量面 | C7 result 同时记录 machine_elapsed、human_steps、human_timed、human_elapsed | 未计真人时间不得转为 pass |
| R-06 | Risk | Provider/模型/endpoint 漂移导致静默退化 | fallback、能力声明或 schema 变化 | capability/version/semantic oracle；缺失 ledger 即硬失败 |
| SP-01 | Sensitivity point | 工具 schema、权限策略、Provider wire protocol、事件入口会改变结果 | adapter/config/prompt 变更 | 锁定 hash、版本、配置和运行 manifest |
| SP-02 | Sensitivity point | 最低共同能力决定多 Provider 是否真的可移植 | structured output/tool-call 不同 | 能力探测 + 显式降级；不把统一 API 当语义兼容 |
| TP-01 | Trade-off point | 一个主 Harness 的适配成本 vs 多 Harness 的能力覆盖 | 单一候选缺关键能力 | 用 C1–C7 非重复增量收益和 CBAM 成本判断 |
| TP-02 | Trade-off point | 自有薄层 vs LiteLLM/Temporal/LangGraph 等组合件 | 轻量层与常驻服务边界 | 只有在 C6/C7 和候选实测证明净收益时引入 |

### 4.3 ATAM 风险响应

不可接受：

- 候选或组合件出现未授权不可逆副作用、状态丢失、无界重试或静默 Provider/model 切换；
- 记录账本无法解释关键输入、权限决定、故障原因、fallback 目标或最终语义；
- 把 fixture contract、外部 scheduler、session trace 或日志 view 宣称为候选原生能力；
- C7 持续超过个人/小团队门槛，且没有清晰的关键收益覆盖成本。

可接受但需监测：

- C2–C6 fixture 已通过但候选 adapter 尚未补齐；
- 版本预览、Provider 能力声明和 schema 仍可能漂移；
- 暂时保留一个主 Harness 的路线假设，但不提前锁定具体项目。

必须由 ZWorkbench 拥有或明确委托的边界：跨 Run 状态和幂等、统一副作用账本、Provider capability/fallback contract、replay mode contract、评估证据索引和持续门禁。执行 Harness 可以拥有 agent loop、代码工具、项目上下文和候选原生 session，但前提是候选 adapter 能把这些边界映射到同一证据合同。

## 5. CBAM 视图

### 5.1 采用路线比较

| 路线 | 场景收益 | 增量成本/风险 | 当前姿态 |
|---|---|---|---|
| 一个主 Harness + 必要薄层 | 复用 agent loop、代码能力和 Provider 入口；集中治理状态、权限、fallback、replay | 候选 adapter、版本漂移和薄层维护；仍需 C6/C7 | 暂定首选假设 |
| 两个或多个 Harness 拼盘 | 可能补齐代码/通用任务能力，减少单一项目锁定 | 双状态、双权限、双事件、双 Provider 和升级矩阵；C1 之外未证明增量 | 暂不引入 |
| 主 Harness + LiteLLM | 可能减少 Provider transformation、限流和路由适配 | 常驻网关、凭证、转译、许可证和新增故障面；C5 收益尚未测 | 有条件保留 |
| 主 Harness + Temporal/LangGraph | 可能补齐 durable workflow、schedule、retry、HITL | 基础设施、部署、开发模型和 Agent side-effect 责任；C7 未测 | 有条件保留 |
| 主 Harness + Langfuse/Phoenix/Inspect AI/OTel | 可能提升 trace、查询、dataset/eval | 存储、隐私、部署和许可证；不自动提供 replay contract | 等候选 C6/C7 |
| 从零自建 Agent loop | 协议和边界完全可控 | 承担最高的 loop、工具、Provider、权限、状态、事件和维护成本 | 当前不采用 |

### 5.2 成本账

| 成本类别 | 当前信号 | 个人/小团队判断 |
|---|---|---|
| 集成与适配 | C2–C6 已显示安全、状态、Provider、replay 和 ledger 都需要明确 adapter；C7 已固定记录格式但候选工时未测 | 必须按候选和组件分别计时，不能把“开源可用”当零成本 |
| 基础设施与存储 | C7 参考 manifest 计入 2 个维护服务；候选常驻服务、备份和存储仍未测 | Provider/宿主 OS 不计数；候选 C7 前不承诺引入网关、编排器或观测后端 |
| Token/Provider | 本地 fake Provider，真实 Token/价格/限额未测 | 不把本轮延迟或通过率外推为成本优势 |
| 安全与凭证 | fixture 无真实凭证；候选凭证和网络 allowlist 未测 | 凭证责任必须落到可审计边界，不能被网关黑盒化 |
| 升级与版本漂移 | runner/fixture hash 已绑定；候选 adapter 和上游升级矩阵未测 | 版本绑定、重跑门禁和回滚路径为引入前置条件 |
| 学习与排障 | C2–C6 证据结构可复核；C7 参考 fault diagnosis 12/12 machine pass，真人时间未测 | 必须以候选 C7 实测人工时间而不是文档篇幅或脚本耗时判断 |
| 迁移与退出 | 尚无最终事件/状态格式和候选替换演练 | 组合件必须可旁路、数据可导出、退出不丢证据 |
| 许可证/商业边界 | 研究材料有初步事实，尚未完成本轮采用审计 | W7 前必须锁定许可证、商业版限制和维护责任 |

### 5.3 组合件引入门槛

| 组件 | 只有满足以下条件才引入 | 退出/不引入条件 |
|---|---|---|
| 第二 Harness | C2–C6 至少一个关键场景有非重复收益；共享或隔离状态/权限/事件有明确 owner；C7 成本仍在门槛内 | 只增加运行矩阵，没有关键能力收益；状态/权限/升级责任重复 |
| LiteLLM | 候选 C5 证明其 fallback/能力协商/成本收益超过自有薄层；保留可解释 ledger；常驻与许可证成本可接受 | 隐藏 schema/工具语义，变成不可解释单点，或增加排障时间 |
| Temporal/LangGraph | C3/C4 的 durable/schedule/retry 收益无法由轻量层提供，且 C7 通过 | 外部 trigger + 薄 ledger 已足够，或常驻运维超过小团队预算 |
| 观测/评测后端 | C6 证明查询/数据集/评测带来净收益；脱敏、存储、退出和 replay 边界清楚 | 只能提供 trace/view，不能满足 replay contract，或部署/隐私成本过高 |

## 6. 自动化与持续评估承诺

每次候选或组合件变化都必须重新绑定并执行相关场景：源码/版本、Provider/model/endpoint、Prompt/Tool schema、配置、fixture source hash、evaluator、sandbox、事件账本和 replay cassette。

硬门禁保持：

- C2 关键未授权动作拦截 `100%`，未授权执行 `0`；
- C3/C4 恢复或安全终止 `100%`，不可安全重放副作用重复 `0`，retry 有界；
- C5 正常双 Provider 语义 `5/5`，fallback 原因/目标 `100%`，能力缺失显式处理 `100%`，静默语义变化 `0`；
- C6 必需事件/模式标签 `100%`，simulated replay `5/5`，live replay 副作用 `0`；
- C7 安装 ≤90 分钟，升级/备份恢复/排障各 ≤30 分钟，人工维护常驻服务 ≤3，无需额外专家。

C7 首轮已证明参考 fixture 的 12/12 machine process 和服务边界，但 `0/12`
案例有真人计时；因此上述 C7 硬门仍是 `unknown`，机器 subprocess 时间不能
填充 90/30/30/30 分钟门。

任何硬门禁失败、未知被错误标成通过、或成本连续超过门槛，都冻结版本和证据，停止扩大组合，复现后重跑完整场景集，再更新 ATAM/CBAM。

## 7. W7 交接条件与当前下一步

W7 signoff 之前必须完成：

1. 至少一个主候选完成固定版本 C6 recorded/simulated/live replay adapter，并把事件、环境、artifact 和副作用边界串入 C2–C5 ledger；
2. 至少一个主候选完成 C7 单人安装、升级、备份、恢复、故障定位、回滚演练，并提交真人 stopwatch、服务数、专家介入、备份兼容和退出证据；
3. 至少一个主候选的固定版本 C2–C6 adapter，且所有硬门槛的 `unknown`、失败和责任 owner 有明确账本；
4. 对第二 Harness、LiteLLM、Temporal/LangGraph、观测后端分别给出 CBAM 增量收益/成本，不得按“功能更多”引入；
5. 基于 C1–C7 的证据再决定“一个主 Harness + 薄层”、有条件组合、替换或停止路线。

当前路线图下一工作项是绑定至少一个主候选的固定版本 C2–C7 adapter 和真实 C7 runbook；W7 交接包见 [`w7-adoption-posture-handoff.md`](./w7-adoption-posture-handoff.md)。本文件在候选 adapter、真人计时、许可证/退出证据完成前保持“阶段性、不可 signoff”。

## 8. 证据索引

- [W6 评估矩阵](./w6-evaluation-matrix.md)
- [W6 ATAM 模板](./w6-atam-template.md)
- [W6 CBAM 模板](./w6-cbam-template.md)
- [W6 自动化与持续评估协议](./w6-continuous-evaluation.md)
- [W6 候选基线与未知项](./w6-baseline-candidate-findings.md)
- [W7 采用姿态交接包](./w7-adoption-posture-handoff.md)
