# W6 CBAM 模板

CBAM 用来回答：一个候选或新增组合件带来的场景收益和风险降低，是否值得它增加的集成、运维、迁移和锁定成本。

当前阶段性汇总见：[W6-0.1 ATAM/CBAM 阶段性决策包](./w6-atam-cbam-decision-package.md)。本模板保留选项成本账和 C1–C7 增量证据；C7 fixture 已完成，但候选固定版本 adapter 与真人运维计时完成前只允许条件性交接 W7，不代表最终采用。

## 1. 选项定义

| 选项 | 角色 | 新增能力 | 复用能力 | 与现有方案重叠 | 退出/替换方式 |
|---|---|---|---|---|---|
| O- | 主 Harness / 组合件 / 自建模块 |  |  |  |  |

## 1.1 研究基线的选项组

先按层级记录价值，避免把不同层级项目相加后误判为一个产品：

| 选项组 | 可期待收益 | 主要增量成本/风险 | 需要验证的 CBAM 问题 |
|---|---|---|---|
| 一个主 Harness + ZWorkbench 薄层 | 复用完整 Agent loop、工具和代码能力，减少自建范围 | 主 Harness 边界、版本漂移、缺少调度/跨运行账本 | 节省的自建/维护时间是否超过适配与退出成本 |
| 第二个 Harness | 补齐某类代码或通用任务能力 | 双运行状态、权限、事件模型、Provider 和升级矩阵 | 增量场景收益是否能被 C1–C6 实测证明 |
| Temporal/LangGraph | durable workflow、schedule、retry、HITL/state graph | 基础设施、开发模型和 Agent side-effect 责任 | C3/C4/C7 的可靠性收益是否值得常驻运维 |
| LiteLLM | Provider 统一、路由、限流、fallback、成本 | 网关、凭证、转译、故障排查和许可证审计 | C5 是否减少 Provider 适配总成本而非引入新单点 |
| Langfuse/Phoenix/Inspect AI/OTel | 观测、评测、trace/dataset/semantic vocabulary | 数据存储、隐私、部署、许可证；不解决完整 replay | C6/C7 的诊断收益是否超过自有事件账本的接入成本 |
| 从零自建 Agent loop | 完全控制协议和边界 | 最大实现、测试、维护、模型/工具兼容成本 | 是否存在所有现成候选都无法通过 G1–G7 的关键缺口 |

## 2. 场景收益与风险降低

| 场景 ID | 场景 | 当前基线痛点 | 采用后收益 | 风险降低 | 收益证据 | 重要性权重 |
|---|---|---|---|---|---|---:|
| C- | 代码闭环 |  |  |  |  |  |
| C- | 自动化恢复 |  |  |  |  |  |
| C- | Provider 故障/迁移 |  |  |  |  |  |
| C- | 观测/回放/评测 |  |  |  |  |  |
| C- | 单人运维 |  |  |  |  |  |

收益不能只写“功能更多”，应尽量关联可观察结果：减少人工时间、提高成功率、减少未授权动作、降低恢复时间、降低定位时间、减少 Provider 单点依赖等。

## 3. 成本账

| 成本类别 | 一次性成本 | 持续成本 | 证据/估算方法 | 可接受上限/判断 |
|---|---|---|---|---|
| 集成与适配 |  |  | API/SDK/进程边界、fixture |  |
| 基础设施与存储 |  |  | 服务数量、资源、备份和监控 |  |
| Token/Provider |  |  | 同一评测集成本、fallback 成本 |  |
| 安全与凭证维护 |  |  | 权限策略、漏洞/升级频率 |  |
| 升级与版本漂移 |  |  | 破坏性变更、兼容测试 |  |
| 学习与排障 |  |  | 文档、错误可见性、操作耗时 |  |
| 迁移与退出 |  |  | 数据格式、协议、替换路径 |  |
| 许可证/商业版边界 |  |  | 许可证和目录审计 |  |

## 4. 增量组合决策

对每个新增组件单独填表，不因为它“能力强”就默认引入。

| 组件 | 它解决的明确场景 | 增量收益 | 增量风险降低 | 增量复杂度 | 是否已有重复能力 | 引入条件 | 不引入/退出条件 |
|---|---|---|---|---|---|---|---|
| Temporal/LangGraph | durable workflow/schedule/retry |  |  |  |  |  |  |
| LiteLLM | Provider 路由/限额/fallback |  |  |  |  |  |  |
| Langfuse/Phoenix | 观测/评测/查询 |  |  |  |  |  |  |
| Inspect AI | 离线 agent eval |  |  |  |  |  |  |
| 第二个 Harness | 明确的执行能力缺口 |  |  |  |  |  |  |

## 5. CBAM 输出

- 当前基线：
- 选择的场景及重要性排序：
- 各选项带来的主要收益：
- 各选项降低的主要风险：
- 最高的一次性成本：
- 最高的持续成本：
- 最高的迁移/锁定成本：
- 值得引入的最小组合：
- 不值得引入或应推迟的组件：
- 需要自动化持续监测的成本/收益指标：
- W7 应采用的姿态及理由：

## 6. 首轮基线填充（W6-0.1）

本节只记录首轮可观察收益和成本信号，不据此完成 W7 采用决策。证据：[w6-baseline-candidate-findings.md](./w6-baseline-candidate-findings.md)，Run ID：`w6-0.1-baseline-20260830T081024-333896Z`。

### 6.1 首轮选项价值

| 选项 | 本轮已证明的收益 | 本轮仍未知的成本/风险 | CBAM 姿态 |
|---|---|---|---|
| 一个主 Harness + ZWorkbench 薄层 | DeepSeek、Codex 均可在两个 fake Provider 上完成 C1 5/5；可复用代码闭环、测试和基础事件输出 | C2–C7 adapter 成本、版本漂移、跨 Run 状态和退出成本 | 保留为待验证主路线 |
| 第二个 Harness | 提供 C1 独立交叉基线，降低单一候选判断偏差 | 没有证明 C2–C7 增量收益；增加双状态/权限/Provider/升级矩阵 | 暂不引入产品拼盘 |
| Temporal/LangGraph | 本轮无直接证据 | 常驻服务、开发模型和 Agent 副作用责任 | 保持候选，不作引入结论 |
| LiteLLM | 本轮无 C5 fallback/能力协商证据 | 网关、凭证、转译和故障排查成本 | 保持 unknown |
| Langfuse/Phoenix/Inspect AI/OTel | 本轮直接保留原始事件/会话，尚未证明外部后端增益 | 存储、隐私、部署、许可证及 replay 边界 | 保持 unknown |
| 从零自建 Agent loop | 无 | 最高实现/测试/维护成本，且无本轮收益证据 | 不因本轮局部结果引入 |

### 6.2 首轮可量化成本信号

| 成本/收益指标 | 结果 | 解释 |
|---|---:|---|
| DeepSeek C1 候选执行耗时 | 5.920 秒 / 10 次 | 仅为候选命令耗时，不含 C7 运维 |
| Codex C1 候选执行耗时 | 11.827 秒 / 10 次 | 仅为候选命令耗时，不含安装和 Provider 成本 |
| C1 候选样本 | 20 个 | 2 候选 × 2 fake Provider × 5 次 |
| 真实 Provider/Token 成本 | 未测 | loopback fake Provider，不得外推 |
| 常驻服务数量 | 未测 | 本轮只启动临时 fake Provider，不是 C7 演练 |
| 安装/升级/备份/恢复/排障时间 | C7 fixture 机器流程 12/12 pass；真人计时 0/12 | subprocess 时间不作为人工时间；候选工时仍 unknown |
| 参考 MVP 维护服务数 | 最大 2（scheduler、evidence-ledger） | Provider 与宿主 OS 排除；候选常驻服务仍需实测 |
| 参考 runbook 专家介入 | `false` | 仅是 fixture 声明，不替代候选单人演练 |

### 6.3 增量组合门槛

| 组件 | 本轮状态 | 后续引入条件 | 不引入/退出条件 |
|---|---|---|---|
| 第二个 Harness | 只有 C1 增量证据 | 在 C2–C6 至少证明明确、非重复的能力收益，并能共享或清晰隔离状态/事件/权限账 | 只增加运行矩阵而没有关键场景收益 |
| Temporal/LangGraph | C3/C4/C7 unknown | C3/C4 的 durable、幂等和恢复收益超过小团队常驻运维成本 | C7 超门槛，或可由轻量外部触发器安全满足 |
| LiteLLM | C5 unknown | 双 Provider fallback/能力协商降低总适配成本，且不成为不可解释单点 | C5 语义差异仍需自有层兜底，网关增加故障面 |
| 观测/评测后端 | C6 unknown | 对查询、数据集和评测的收益能超过自有事件账本的部署/隐私成本 | 只能提供 trace/view，不能满足 replay contract 或引入过高运维负担 |

### 6.4 首轮 CBAM 输出

- 当前基线：两个候选的 C1 代码闭环通过；C2–C7 未形成可排序证据。
- 最高的一次性成本：尚不能量化；明确存在候选专属 adapter、版本绑定和安全/事件契约适配成本。
- 最高的持续成本：尚不能量化；预计主要风险在多 Harness 状态/权限/升级矩阵和外围服务维护。
- 值得引入的最小组合：本轮不作最终选择；仅保留“一个主 Harness + 必要薄层”作为待验证假设。
- 不值得引入或应推迟的组件：在 C3–C7 数据出现前，不为功能数量引入第二 Harness、Temporal/LangGraph、LiteLLM 或观测后端。
- 持续监测：C1 成功率、人工介入、C2 拦截、C4 恢复、C5 fallback、C6 回放一致性、C7 运维时间、Token/存储/服务数和升级工时。
- W7 姿态：暂不决策；完成 C2–C7 并将 ATAM 风险与 CBAM 成本放在同一证据批次后再定。

### 6.5 C2 adapter 增量证据

证据：[`w6-c2-adapter-findings.md`](./w6-c2-adapter-findings.md)，Run ID：`w6-0.1-c2-20260830T093457-799592Z`。

| 维度 | 当前判断 |
|---|---|
| 增量收益 | 用一个候选无关 adapter 同时覆盖 DeepSeek/Codex 的五类负向动作；15 次无人审批全阻断；一次性批准边界可验证 |
| 一次性成本 | action/tool schema 适配、side-effect oracle、ledger 持久化和候选执行配置锁定 |
| 持续成本 | approval token 生命周期、ledger schema、候选版本漂移，以及宿主 sandbox 兼容性 |
| 组合判断 | 支持“一个主 Harness + 薄安全层”作为待验证路线；不构成引入第二 Harness 的收益证明 |
| 未解决成本 | 若要求宿主级强制 broker，需要新增进程边界和 C2/C4 重测成本 |

### 6.6 C4 durable/recovery 增量证据

证据：[`w6-c4-recovery-findings.md`](./w6-c4-recovery-findings.md)，Run ID：`w6-0.1-c4-20260830T101004-470428Z`。

| 维度 | 当前判断 |
|---|---|
| 增量收益 | 用统一 durable state、attempt、fault、result 和 effect ledger 覆盖 6 个故障点；54/54 通过，能区分 resume、bounded retry 与 safe-stop |
| 一次性成本 | fixture 状态机、故障注入与逐例 oracle；候选接入仍需把其真实事件/工具边界映射到同一合同 |
| 持续成本 | ledger 存储、schema 兼容、operation id/幂等协议、故障样本保留和人工接管；本批次未测真实服务运维时间 |
| 组合判断 | 支持“一个主 Harness + 必要薄 durable/recovery 层”作为待验证路线；不证明应立即引入 Temporal/LangGraph |
| 引入条件 | 候选原生恢复无法满足 C4，且组合件在 C3/C4 的可靠性收益超过个人/小团队部署与排障成本 |
| 不引入/退出条件 | 仅增加状态/事件/权限重复账，或 C7 运维超过 W6 阈值且没有关键门槛收益 |

### 6.7 C3 scheduler/idempotency 增量证据

证据：[`w6-c3-idempotency-findings.md`](./w6-c3-idempotency-findings.md)，Run ID：`w6-0.1-c3-20260830T102401-857158Z`。

| 维度 | 当前判断 |
|---|---|
| 增量收益 | 外部确定性 trigger、跨进程 key、attempt/schedule/result/effect ledger 和 sink oracle 在 15/15 case 验证了单结果幂等合同 |
| 一次性成本 | 触发器与 idempotency adapter、状态 schema、重复/错过/延迟场景 oracle；候选接入仍需映射 scheduler/session API |
| 持续成本 | scheduler 常驻/唤醒、状态备份、时区与错过触发处理、ledger 保留和排障；本批次没有 C7 时间数据 |
| 组合判断 | 对个人开发者/小团队，外部轻量 trigger + 薄幂等层是可验证的 `pass-with-composition` 候选，不等于立即引入复杂编排器 |
| 引入条件 | 候选原生 scheduler 无法提供可审计 schedule/attempt/key/effect 语义，且外部组合的 C7 成本在阈值内 |
| 不引入/退出条件 | 产生重复状态/权限/事件事实，或错过触发、备份、升级和排障成本超过原生能力收益 |

### 6.8 C5 Provider failover/降级增量证据

证据：[`w6-c5-provider-failover-findings.md`](./w6-c5-provider-failover-findings.md)，Run ID：`w6-0.1-c5-20260830T112617-960750Z`。本节只记录 acceptance/evaluation 的可观察收益和成本信号，不完成 W7 采用决策。

| 维度 | 当前判断 |
|---|---|
| 增量收益 | 19 个隔离案例验证了双 Provider 的 identity/model/endpoint、能力探测、attempt history、显式 fallback/degradation ledger 和 semantic oracle；正常 A/B 各 5/5，故障 9/9 |
| 一次性成本 | router、capability contract、stream parser、structured schema、fallback ledger 和逐例 oracle；候选接入仍需绑定各自 Provider/API/事件边界 |
| 持续成本 | Provider 凭证、限额、成本、schema 漂移、fallback 质量和事件存储；本批次没有真实 Provider 或常驻网关运维数据 |
| 组合判断 | 支持“一个主 Harness + 薄 Provider contract/adapter”作为待验证路线；不证明第二 Harness 或 LiteLLM 的增量收益 |
| LiteLLM 引入条件 | 候选实测证明网关能降低总 Provider 适配与排障成本，并保留可解释的 capability/fallback ledger；其常驻服务、许可证和故障面在 C7 内可接受 |
| 不引入/退出条件 | 只提供统一 HTTP 表面却隐藏 schema/工具语义，或增加一个无法解释的 fallback 单点；个人/小团队运维超过既定 C7 门槛 |

### 6.9 C6 replay contract 增量证据

证据：[`w6-c6-replay-findings.md`](./w6-c6-replay-findings.md)，Run ID：`w6-0.1-c6-20260830T120732-177815Z`。本节只记录 acceptance/evaluation 的可观察收益和成本信号，不完成 W7 采用决策。

| 维度 | 当前判断 |
|---|---|
| 增量收益 | 15 个隔离案例验证了 recorded view、cassette-only simulated replay 和默认拒绝 live replay 的边界；模式标签/必需事件字段 100%，simulated 5/5，effect guard 变化 0 |
| 一次性成本 | event schema、environment manifest、cassette、mode policy、execution counter、effect guard 和候选 replay adapter；候选接入仍需映射真实 session/trace/API |
| 持续成本 | 事件/录音存储、敏感信息脱敏、保留期限、查询索引、schema 兼容和退出导出；本批次未测外部观测后端运维 |
| 组合判断 | 支持“一个主 Harness + 薄 replay contract/证据索引”作为待验证路线；不证明必须引入 Langfuse/Phoenix/Inspect AI/OTel |
| 观测/评测后端引入条件 | C6 候选实测证明查询、dataset/eval 或关联收益超过自有 ledger 成本；不改变 live replay 的 fail-closed policy |
| 不引入/退出条件 | 只能提供 trace/view、无法保证 cassette-only 或模式边界，或引入过高存储/隐私/部署/排障成本 |

### 6.10 C7 运维与生命周期成本增量证据

证据：[`w6-c7-operations-findings.md`](./w6-c7-operations-findings.md)，Run ID：`w6-0.1-c7-20260830T122018-367856Z`。

| 维度 | 当前判断 |
|---|---|
| 增量收益 | 4 类生命周期操作各重复 3 次，共 12/12 machine process pass；固定了 operation ledger、人工步骤、服务/依赖清单和时间测量边界 |
| 一次性成本 | 增加 C7 fixture/runner、逐 case 文件 oracle、服务计数规则和人工计时模板；候选仍需固定版本 runbook adapter |
| 持续成本 | 候选安装、升级、备份兼容、回滚、排障、凭证、存储和退出成本仍未测；本轮没有真实 daemon 或外部后端运行 |
| 人工时间信号 | `0/12` 真人计时；安装 ≤90、升级/恢复/排障 ≤30 的硬门暂为 `unknown`，不是 pass |
| 组合判断 | 参考 MVP 服务数为 2/3，说明可把常驻服务纳入 CBAM 账；不能据此证明 Temporal/LangGraph、LiteLLM、观测后端或第二 Harness 值得引入 |
| 引入条件 | 至少一个候选的真实 C7 工时、服务数、专家介入、回滚和退出证据在阈值内，并且组合件带来 C2–C6 的非重复关键收益 |
| 不引入/退出条件 | 任一关键工时超门且无足够收益覆盖，或新增服务复制状态/权限/事件并增加排障责任 |
