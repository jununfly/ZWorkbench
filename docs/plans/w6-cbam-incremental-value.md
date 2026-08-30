# W6 CBAM-3：第二 Harness 与组合件的增量价值

状态：`completed` · `acceptance/evaluation` · 适用约束：个人开发者或小团队 · 不是产品实现授权或 W7 最终采用结论

本文件收口路线图节点 `1-3-3`。它回答的不是“哪个项目功能最多”，而是：在已有
“一个主 Harness + 必要薄层”的前提下，第二个执行 Harness 或一个外围组合件是否
带来无法由主路线提供的关键收益，并且是否值得它增加的状态、权限、事件、升级、
排障、迁移和退出责任。

## 1. 增量价值判定规则

### 1.1 四项硬条件

新增选项只有在以下条件全部满足时才可进入 W7 采用候选：

1. **非重复场景收益**：至少一个 C2–C6 关键场景出现主路线无法提供的结果；必须是
   固定源码/版本、配置、Provider、fixture、adapter 和原始证据绑定的
   `measured-candidate`，不能只是 C1 交叉样本或理论能力列表；
2. **风险降低可归因**：能明确说明它降低哪个 ATAM 风险，以及与主路线相比减少了哪
   个可观察坏结果；不能把外部 trace、HTTP 兼容或功能数量当作风险降低；
3. **责任不重复**：状态、权限、Provider、事件、replay、备份、升级和诊断各有唯一
   owner；新增选项不能产生第二套事实账或绕过 C2–C6 合同；
4. **生命周期成本可接受**：一次性、持续、迁移/锁定和退出成本均有单位与证据；
   C7 满足安装 ≤90 分钟、升级/备份恢复/排障各 ≤30 分钟、维护服务 ≤3、无需额外
   专家，并且可导出/替换/回滚/退出。

任一条件为 `unknown` 时，保持候选状态，不扩展产品组合；硬门失败时暂停升级和
组合扩展，不以其他场景的通过结果抵消。

### 1.2 增量价值公式（只规定采集，不伪造数值）

```text
incremental_value
  = non_duplicate_scenario_benefit
  + attributable_risk_reduction
  - one_time_integration_cost
  - recurring_operation_cost
  - migration_and_lock_in_cost
  - exit_cost
```

每项必须保留场景 ID、证据等级、来源、单位和 owner。W6 当前没有候选固定版本
adapter、真实 Provider 费用或真人 C7 时间，因此不计算数值化的收益/成本比。

## 2. 当前证据下的选项矩阵

| 选项 | 可期待的独立角色 | 当前非重复收益证据 | 重复责任/成本风险 | 当前姿态 |
|---|---|---|---|---|
| 第二执行 Harness | 补齐主 Harness 无法提供的代码、通用任务、Provider 或运行边界 | 只有 DeepSeek/Codex 的 C1 交叉基线；Pi/OpenCode/Goose C1–C7 多数仍 unknown；没有 C2–C6 非重复 candidate evidence | 第二套 loop、session、Provider、权限、状态、事件、replay、升级和排障矩阵 | **不引入** |
| SWE-agent / Aider 等代码专长执行器 | 对特定代码任务提供专长或替代路径 | 研究层面可期待代码能力，但没有本轮统一 C2–C7 adapter 和非重复实测 | 仍需项目上下文、权限、状态、事件、Provider、replay 和 runbook 边界；不能直接替代工作台 | **保持候选，只有明确代码缺口才重开** |
| LiteLLM 或同类 Provider gateway | 集中 Provider transformation、路由、限流、预算和 fallback | C5 fixture 证明 fallback/capability contract 可独立建模，不证明 gateway 比薄 adapter 更省 | 常驻 gateway、凭证和限额 owner、schema/stream 转译、故障单点、许可证和退出锁定 | **不引入** |
| Temporal / LangGraph / 独立 scheduler | durable workflow、schedule、retry、HITL 或状态图 | C3/C4 fixture 证明这些合同值得测，但没有证明常驻系统相对轻量组合的净收益 | 数据库/历史/worker、备份、迁移、升级、时区和排障责任；Agent 副作用仍需自有合同 | **有条件候选** |
| Langfuse / Phoenix | trace、查询、可视化、dataset/experiment 入口 | C6 fixture 已证明自有 event/cassette/mode contract；外部查询净收益未测 | 存储、collector/backend、隐私、许可证、保留/删除和退出；trace 不能代替 replay | **有条件候选** |
| Inspect AI | 离线 dataset、solver、scorer 和 agent eval | 研究层面适合评测，但没有本轮与主 ledger/replay/副作用边界的集成实测 | 评测输入/输出、judge、版本和依赖维护；不提供安全 broker 或长期 Run 状态 | **有条件候选** |
| OpenTelemetry / OpenInference 等语义层 | 跨 Harness/Provider 的低层 telemetry 词汇和导出 | 研究证据支持互操作方向；不提供完整 canonical ledger 或 replay | semconv 版本迁移、字段丢失/截断、collector 和隐私配置；不是执行引擎 | **作为可选协议层，不独立引入后端** |
| 从零重写 Agent loop | 完全控制 loop、工具和事件语义 | 没有本轮非重复收益；现成候选已有 C1 局部结果 | 承担生态、Provider、权限、恢复、replay、测试、升级和退出的最大总成本 | **排除** |

## 3. 按组件的重开门槛

| 组件 | 必须证明的非重复收益 | 必须同步采集的成本 | 不能接受的结果 |
|---|---|---|---|
| 第二 Harness | 在至少一个 C2–C6 关键场景比主 Harness + 薄层多出可复核能力；例如主路线无法满足的工具/模型/恢复边界，而不是同一 C1 再跑一遍 | 第二套安装、版本绑定、Provider/tool/session/event/replay adapter、C7 服务数、人时、许可证和退出 | 只有 C1 交叉验证；复制状态/权限/事件 owner；无法统一 ledger 或退出 |
| LiteLLM | 固定双 Provider 实测显示 adapter、路由、限流、成本或故障排障总工作量下降，且保留 capability/fallback/degradation ledger | gateway 部署、凭证、限额、转译、升级、旁路、存储和停服/替换 | 只提供兼容 HTTP 表面；隐藏 tool/stream/structured 语义；成为不可解释单点 |
| Temporal/LangGraph | 候选 C3/C4 证明轻量外部 trigger + 薄状态/幂等/recovery 层无法满足关键 durable/schedule/retry/HITL 合同 | worker/DB/history 服务数、备份恢复、schema 迁移、排障、人工接管和退出 | 理论 durable 能力，但 C7 超门或 Agent effect/replay owner 不清 |
| Langfuse/Phoenix | 候选 C6 证明查询、关联、dataset/experiment 或调试时间有可量化净收益 | collector/backend、存储 GB/月、脱敏、访问、TTL、备份、许可证和导出/删除 | 只有 trace/view；不能满足 canonical event/replay contract；默认记录敏感内容 |
| Inspect AI | 评测集、solver、scorer 能减少真实评测编排人时，并能锁定 evaluator/artifact identity | Python/依赖、并发/重试、dataset 版本、judge 成本、结果导出和维护人时 | 只能评分，不能关联运行/Provider/tool/replay 证据；收益无法超过接入成本 |
| OTel/OpenInference | 能减少跨候选事件字段映射和导出成本，且保留原始 payload 与规范化字段 | collector、semconv 升级、敏感字段策略、丢弃/截断和查询后端 | 用 semconv 猜测式丢字段；将 span tree 解释成完整工作台事件账或 live replay |

## 4. 第二 Harness 的专项判断

### 4.1 当前增量收益只有交叉基线

DeepSeek Harness 与 Codex Harness 的 C1 结果在 fake-a/fake-b 上均为 5/5，合计
20/20。这个交叉样本可以降低单一候选 C1 判断偏差，但它没有证明第二个 Harness
在 C2 安全、C3 调度、C4 恢复、C5 Provider、C6 replay 或 C7 运维上提供新能力。

Pi Agent Harness、OpenCode、Goose 没有完成同等固定版本 adapter，因此不能用研究
文档的功能列表为第二 Harness 计入收益。

### 4.2 第二 Harness 的证明义务

如果 W7 要重新打开第二 Harness，必须与主候选使用同一 W6 fixture 和 evidence
contract，至少完成一个非重复场景的固定版本实测，并回答：

- 新增能力是否不能由主 Harness 的薄 adapter 提供；
- 新增 session/state/permission/event/replay 是否有共享或清晰隔离的 owner；
- Provider、凭证、sandbox、approval、effect、backup 和 diagnosis 是否避免双事实；
- 第二套安装、升级、回滚、退出和故障定位是否仍满足个人/小团队 C7；
- 如果第二 Harness 被移除，canonical ledger、cassette、artifact 和历史评测是否仍可读。

在这些证据完成前，第二 Harness 只是研究候选，不是产品组合件。

## 5. 当前最小组合决定

当前保留的最小组合是：

> 一个主 Harness + 必要薄层；薄层只承接已由 C2–C7 合同证明必须跨候选统一的安全、状态/幂等、Provider、replay、证据和持续评估边界。

暂不引入第二 Harness、LiteLLM、Temporal/LangGraph、Langfuse/Phoenix、Inspect AI
或独立 OTel 后端。这个决定不是永久排除，而是因为当前没有一项满足四项硬条件，
并且 C7 真人时间、候选固定版本、真实 Provider、许可证、迁移和退出证据仍为
`unknown`。

薄层本身也不能被默认视为免费：它的工程、测试、升级和排障成本必须进入上一节点
的成本账；如果某项薄层演化成独立常驻服务或第二事实系统，就必须重新按本节点
作为组合件评估。

## 6. 自动化持续评估要求

每次重新打开一个组件，都必须生成新的 evaluation identity，并运行受影响场景：

- 第二 Harness：至少 C1–C6，重点是 C2–C6 非重复能力、owner 和 side-effect ledger；
- LiteLLM：C5 双 Provider、能力缺失、stream/error、fallback 和成本/限额；
- Temporal/LangGraph：C3 schedule/missed trigger/idempotency、C4 resume/retry/reconcile；
- Langfuse/Phoenix/Inspect AI/OTel：C6 event/cassette/mode、脱敏、评测结果关联和 C7 运维；
- 任一组件：C7 安装、升级、备份恢复、故障定位、回滚、服务数、专家介入和退出。

持续门禁要求硬失败或关键 unknown 时 `pause`；保留失败样本、成本变化、版本差异、
回滚目标和独立 rerun。组件通过自己的场景，不代表它可以绕过主 Harness 的 C2–C6
安全、状态、Provider 或 replay 合同。

## 7. 节点结论与后续交接

本节点结论：

- 第二 Harness：当前只有 C1 交叉价值，没有非重复关键收益，暂不引入；
- LiteLLM：保留为 Provider gateway 候选，等待 C5 候选实测和成本对照；
- Temporal/LangGraph：保留为 durable/schedule 候选，等待 C3/C4 候选能力缺口和 C7 证据；
- Langfuse/Phoenix/Inspect AI/OTel：保留为观测/评测/语义层候选，不能替代自有 replay/副作用合同；
- 从零重写 Agent loop：当前排除；
- 当前路线假设：一个主 Harness + 必要薄层；不做最终采用签署。

W6 的 CBAM 节点完成后，W7 应优先绑定一个主候选的固定版本 C2–C7 adapter 和真实
C7 runbook，再根据本文件的四项硬条件决定是否重新打开任一组合件。所有候选总体、
G0/G7 和最终主 Harness 选择在证据完成前继续保持 `unknown`/`conditional-handoff`。

## 8. 证据索引

- [W6 CBAM 场景收益与风险降低量化](./w6-cbam-benefits-risk-reduction.md)
- [W6 CBAM 成本账](./w6-cbam-cost-ledger.md)
- [W6 CBAM 模板](./w6-cbam-template.md)
- [W6 ATAM/CBAM 阶段性决策包](./w6-atam-cbam-decision-package.md)
- [W6 评估矩阵](./w6-evaluation-matrix.md)
- [W7 采用姿态交接包](./w7-adoption-posture-handoff.md)

