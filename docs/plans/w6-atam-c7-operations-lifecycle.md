# W6 ATAM-C7：单人运维、恢复与生命周期成本

状态：`completed` · `acceptance/evaluation` · 适用约束：个人开发者或小团队 · 不是候选 Harness 通过结论，也不是 ZWorkbench 产品实现

本文件收口路线图节点 `1-2-5` 的 ATAM 场景定义，并解释 C7 首轮 fixture
contract 对组合架构选择的影响。C7 关注的不只是功能能否启动，而是一个没有专职
平台团队的操作者能否安装、升级、恢复和排障；它把机器可自动验证的流程、真人操作
时间、维护服务数量、专家依赖、回滚和退出责任分开记录。

## 1. ATAM 质量属性场景

| 要素 | 冻结定义 |
|---|---|
| 刺激 | 单一操作者在固定版本候选上依次执行首次安装、常规升级、备份恢复和预制故障定位；必要时执行回滚/退出路径 |
| 环境 | 全新隔离 workspace；固定源码/二进制、Provider、配置、依赖、runbook 和服务清单；无真实生产数据、真实凭证、外网和不可逆副作用 |
| 响应 | 操作者能够按 runbook 独立完成流程；每步写入 operation ledger；验证结果、故障 ID、依赖、维护服务、备份、恢复和回滚证据均可复核 |
| 度量 | 安装人工时间 ≤ `90` 分钟；升级/备份恢复/故障定位各 ≤ `30` 分钟；维护常驻服务 ≤ `3` 个；不需要额外专家；四类流程各重复 `3` 次；机器流程和必需事件完整率 `100%` |
| 证据 | 固定版本身份、runbook、operation ledger、步骤与验证、service/dependency manifest、备份/回滚/退出记录、真人 stopwatch、人工介入和失败样本 |

人工 stopwatch 是 G0/G7 签字的必需证据。runner 的 subprocess 墙钟时间只表示
fixture 执行下界，绝不能替代操作者阅读文档、准备凭证、确认结果或排查问题的时间。

## 2. 首轮 fixture 结果

证据：[W6-0.1 C7 个人开发者/小团队运维与生命周期成本](./w6-c7-operations-findings.md)。正式
Run：`w6-0.1-c7-20260830T122018-367856Z`。

| 场景 | 重复 | 机器流程 | 人工门 | 固定阈值 |
|---|---:|---:|---|---:|
| 首次安装 | 3 | 3/3 pass | `unknown`，0 次真人计时 | ≤90 分钟 |
| 常规升级 | 3 | 3/3 pass | `unknown`，0 次真人计时 | ≤30 分钟 |
| 备份恢复 | 3 | 3/3 pass | `unknown`，0 次真人计时 | ≤30 分钟 |
| 预制故障定位 | 3 | 3/3 pass | `unknown`，0 次真人计时 | ≤30 分钟 |
| 合计 | 12 | **12/12 pass** | **pass-with-unknown-human-timing** | — |

参考 fixture 的维护服务清单为 `2` 个：`scheduler`、`evidence-ledger`；Provider
和宿主 OS 按冻结规则排除。四类流程均声明不需要额外专家，且只操作 case-local
可逆文件。首轮未安装依赖、未启动常驻 daemon、未访问网络或 Provider。

机器耗时只作为记录：12 个案例均在约 `0.001–0.003` 秒范围内完成，平均约
`0.001649` 秒；该数值不构成任何人工运维效率结论。

## 3. 运维合同与可复核证据

| 场景 | 操作合同 | 关键 oracle |
|---|---|---|
| `install` | 干净 workspace 建立最小 app/config/state 布局 | 版本、配置和状态文件存在且 schema 正确 |
| `upgrade` | 从 `0.1` 生成升级前 snapshot，再切换到 `0.2` | snapshot 保留旧版本，当前版本为目标版本，可回滚入口存在 |
| `backup_restore` | 备份健康状态，注入损坏，再恢复并核对摘要 | 备份存在、恢复摘要一致、状态回到 `healthy` |
| `fault_diagnosis` | 生成 Provider timeout 预制故障和 degraded health | fault ID/run ID 关联，诊断分类和下一步动作存在 |

每个案例至少保存：

- `operation/operation-events.jsonl`：开始、环境、前置条件、步骤、验证和完成事件；
- `operation/operation-result.json`：机器时间、人工计时状态、步骤清单和 oracle；
- `operation/service-manifest.json`：计入与排除的服务及维护数量；
- `operation/dependency-manifest.json`：运行时依赖和专家要求；
- `process-result.json`：runner 返回码与命令；
- `human-timing-template.json`：真人计时待填模板。

## 4. 架构事实与责任边界

| 能力 | C7 当前事实 | W7 必须确认的 owner |
|---|---|---|
| 安装/升级 runbook | 参考 fixture 能生成可复核步骤，但不是候选安装流程 | 主 Harness、薄层和 ZWorkbench 自有模块的版本/配置/迁移 owner |
| 备份/恢复/回滚 | 参考 fixture 对 case-local state 做摘要恢复 | 产品必须明确 Run ledger、Provider 配置、cassette、artifact 和策略的备份/恢复顺序 |
| 故障定位 | 参考 fixture 关联 `fault_id`、`run_id`、健康状态和建议动作 | 单一诊断入口；必须能跨 C2–C6 ledger 定位权限、恢复、Provider、replay 和副作用问题 |
| 维护服务计数 | 参考 MVP 计入 scheduler、evidence-ledger 共 2 个；Provider/宿主 OS 排除 | 候选真实部署的 daemon、数据库、gateway、观测后端和代理必须逐项列入/排除并说明理由 |
| 依赖和专家门槛 | 参考 runbook 无额外专家、仅 Python runtime | 候选需要真实凭证、数据库、容器、平台知识或专家升级时必须计入人工成本和风险 |
| 升级/退出 | 本轮只验证本地版本标记与 snapshot | 必须提供兼容性、迁移、回滚、数据导出/删除、许可证和退出证据 |
| 人工操作时间 | 本轮 0/12 有真人 stopwatch | 由单一真实操作者按固定 runbook 记录每类时间、人工步骤、等待和介入；缺失保持 unknown |

## 5. ATAM 风险、敏感点与权衡点

| ID | 类型 | 判断 | 触发条件 | 处理与证据 |
|---|---|---|---|---|
| R-C7-01 | Risk | fixture 或脚本通过被误读为候选可运维 | 只看返回码、机器耗时或文档存在 | 分离 machine/human 字段；候选必须有固定版本 runbook 和真人 stopwatch |
| R-C7-02 | Risk | 服务数量和专家依赖被低估 | 把 gateway、数据库、scheduler、观测后端、broker 或人工升级链路排除 | 候选 service/dependency manifest 逐项计数；Provider/宿主 OS 排除必须显式声明 |
| R-C7-03 | Risk | 升级或恢复破坏 Run ledger、Provider 配置、cassette 或副作用账本 | schema、版本、依赖、配置或组合件变化 | 执行备份、恢复、回滚和独立 rerun；与 C3/C4/C6 evidence identity 关联 |
| R-C7-04 | Risk | 故障定位依赖专家或跨多个不可查询日志 | Provider timeout、权限 deny、replay mismatch 或状态损坏 | 提供单一诊断入口、fault/run correlation、下一步动作和失败样本；人工介入需计时 |
| R-C7-05 | Risk | 退出成本被忽略，形成不可迁移的数据/策略锁定 | 外部观测后端、gateway、Temporal 或第二 Harness 被引入 | 验证导出、删除、替换、许可证和停服路径；没有退出证据不得扩大组合 |
| SP-C7-01 | Sensitivity point | 安装包、版本、配置、依赖和迁移脚本 | 候选/薄层升级或换 Provider | 纳入 evaluation identity；触发 install/upgrade/backup 回归 |
| SP-C7-02 | Sensitivity point | 常驻服务、数据存储和备份拓扑 | 引入 scheduler、gateway、观测后端或 broker | 更新 service/dependency manifest；超过 3 个或需要专家即重新做 CBAM |
| SP-C7-03 | Sensitivity point | 人工步骤、等待时间和真实错误处理 | runbook、凭证、网络或平台环境变化 | 单一操作者独立计时；不允许以 subprocess 时间或作者估计填充 |
| SP-C7-04 | Sensitivity point | 回滚/退出后的 ledger、cassette 和 artifact 可读性 | 版本降级、组件替换、停用外部后端 | 做导出/恢复/独立 rerun，记录兼容性和残留数据 |
| TP-C7-01 | Trade-off point | 功能覆盖 vs 个人/小团队生命周期负担 | 引入第二 Harness、gateway、scheduler 或观测后端 | 只有非重复收益超过安装、升级、备份、排障和退出成本才引入 |
| TP-C7-02 | Trade-off point | 常驻 durable/orchestration 服务 vs 轻量本地状态/账本 | 长流程、定时任务和恢复需求增长 | 用 C3/C4/C7 的真实服务数、故障定位和恢复演练比较；不按理论能力决策 |
| TP-C7-03 | Trade-off point | 自动升级便利性 vs 可回滚和证据稳定性 | 上游、Provider、schema 或配置漂移 | 默认先 pause/备份/回归，再升级；unknown 或 hard failure 不自动推进 |

## 6. CBAM 增量决策

| 选项 | 可量化收益 | 增量成本/风险 | 当前姿态 |
|---|---|---|---|
| 一个主 Harness + 必要薄层 | 维护主体集中；可以只对安全、状态、Provider、replay 和证据边界维护薄层 | 候选真实安装、升级、恢复、退出和人工排障仍需测 | **最小路线假设，进入候选 C7 验证** |
| Temporal/LangGraph 或独立 scheduler | 可能增强 durable workflow、schedule 和 retry | 常驻服务、数据备份、升级、诊断和退出复杂度；C7 真人成本尚未证明值得 | **有条件保留，不因 fixture pass 引入** |
| LiteLLM / 外部观测评测后端 | 可能减少 Provider 路由、trace 查询或评测编排工作 | gateway/存储/凭证/许可证/隐私/停服责任必须纳入运维矩阵 | **等待 C5/C6 候选 adapter 和真人 C7 成本** |
| 第二个 Harness | 可能增加局部模型/工具生态 | 复制安装、Provider、权限、状态、replay、升级和排障矩阵 | **不因 C7 引入产品拼盘** |
| 从零自建全栈平台 | 理论上可统一所有运维边界 | 个人开发者承担最大版本、生态、恢复和退出责任 | **排除当前路线** |

C7 的 CBAM 原则是“按总生命周期成本决策”，而不是按功能列表决策。当前参考
fixture 的 2 个维护服务只是合同示例，不是对候选真实部署的承诺；候选服务、人工
时间、专家介入和退出证据缺失时，不得把任何组合件标记为净收益。

## 7. 候选状态与不可接受边界

DeepSeek Harness、Pi Agent Harness、Codex Harness、OpenCode、Goose 当前 C7 均为
`unknown`。正式 Run 的 candidate baseline 原因是：没有候选专属固定版本 runbook 和
真人操作者计时；fixture contract 不能转化为候选通过。

不可接受边界：

- 把机器 subprocess 墙钟时间写成安装、升级、恢复或排障人工时间；
- 没有固定版本、依赖清单、服务清单、备份/回滚和退出路径就签 G0/G7；
- 维护服务超过 3 个，或需要额外专家，却没有已批准的非重复收益和成本决策；
- 升级、恢复或退出破坏 C2–C6 的 policy、state、effect、Provider、replay 或 artifact ledger；
- 用参考 fixture 的 12/12 pass 抵消候选人工时间 unknown、许可证风险或真实排障失败；
- 依靠不可查询的多个日志/后台服务才能完成单人故障定位；
- 将 Provider、宿主 OS、临时 fake service 排除计数却不在真实候选部署中显式说明。

## 8. W7 入口与下一步

W6 C7 fixture/ATAM 收口后，W7 必须选定至少一个主候选，绑定固定源码/二进制、
Provider、配置、依赖和 runbook，并由单一真实操作者执行：

1. 首次安装并记录完整人工 stopwatch、等待和人工步骤；
2. 常规升级、备份恢复、回滚和独立 rerun；
3. 预制 Provider/权限/replay/状态故障定位，记录 fault/run correlation 与专家介入；
4. 逐项核对维护服务、依赖、许可证、数据保留、导出/删除和退出路径；
5. 将真人时间与 C2–C6 的安全、恢复、Provider、事件和 replay ledger 关联，重新判断 G0/G7。

在真人计时、固定版本 runbook、真实服务/依赖清单和回滚/退出证据完成前，C7 和
G0/G7 继续保持 `unknown`。本节点完成只代表 C7 评估合同已收口，不代表任何候选
已采用，也不授权开始 ZWorkbench 产品实现。

## 9. 证据索引

- [W6-0.1 C7 fixture findings](./w6-c7-operations-findings.md)
- [W6 C6 事件记录与回放 ATAM](./w6-atam-c6-replay-evaluation.md)
- [W6 C5 Provider 可迁移性 ATAM](./w6-atam-c5-provider-portability.md)
- [W6 ATAM/CBAM 模板](./w6-atam-template.md)
- [W6 评估矩阵](./w6-evaluation-matrix.md)
- [持续评估控制面证据](./w6-continuous-evaluation-findings.md)
