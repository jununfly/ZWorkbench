# W6 CBAM-1：场景收益与风险降低量化

状态：`completed` · `acceptance/evaluation` · 不是 ZWorkbench 产品实现，也不是 W7 最终采用排序

本文件收口路线图节点 `1-3-1`。目标是把 W6-0.1 的 ATAM 场景结果转换为 CBAM
可使用的“毛收益”和“可观察风险降低”基线，同时严格保留证据层级。这里的数字
描述 fixture 合同或局部候选 adapter 的覆盖，不代表线上风险下降百分比、Token 节省、
MTTR 改善或人工时长节省；净收益必须等待 `1-3-2` 的一次性、持续、迁移和退出成本。

## 1. 量化方法与边界

### 1.1 三层指标

| 层 | 计算方式 | 可以回答 | 不能回答 |
|---|---|---|---|
| 场景合同收益 | `通过案例 / 该场景案例总数`，并保留模式、工具类别和重复数 | 规格化 fixture 是否持续满足预期语义 | 生产任务成功率或真实用户价值 |
| 可观察风险降低 | 记录硬失败计数、未授权执行、状态丢失、重复副作用、静默语义变化、模式误标和 effect guard 变化 | 本批次隔离边界中哪些坏结果被阻止 | 线上风险概率、漏洞风险或真实外部系统安全 |
| 证据覆盖 | 必需字段、身份、attempt、policy、state、effect、replay 和人工时间的已测/未知状态 | 结论是否可复核、可归因、可持续回归 | “没有观测到”就是“不会发生” |

### 1.2 证据层级

- `measured-candidate`：候选固定源码/版本、配置、Provider、adapter 和原始证据均绑定；
- `fixture-contract`：候选无关隔离 fixture 达到合同阈值；
- `pass-with-composition`：由外部轻量组合件满足合同，不是 Harness 原生能力；
- `unknown`：版本、边界、人工成本或证据缺失。

本文件不得把 `fixture-contract` 或 `pass-with-composition` 改写成候选通过；
`unknown` 也不得由另一个场景的 100% 结果抵消。

## 2. W6-0.1 场景收益与风险降低矩阵

合计为 7 个场景、150 个案例级观察：C1 `20` + C2 `15` + C3 `15` + C4 `54` +
C5 `19` + C6 `15` + C7 `12`。这些案例来自不同的 oracle 和证据层级，不能相加
成为一个“系统通过率”。

| 场景 | 当前可观察基线痛点 | W6-0.1 毛收益 | 可观察风险降低 | 证据状态/限制 |
|---|---|---|---|---|
| C1 代码闭环 | 仅有局部候选代码闭环；安全、恢复和回放边界未覆盖 | DeepSeek/Codex 在 fake-a/b 各 5/5，合计 20/20；测试通过率 100%、越界修改 0、关键事件完整率 100% | 在隔离项目中减少“代码成功但无法审计/越界”的可观察失败；禁止命令 0 | `measured-candidate` 的局部 C1；不覆盖 G2–G7，其他候选仍 unknown |
| C2 安全/审批 | 无人值守危险动作若无策略可能直达外部副作用 | 五类危险动作各 3 次，共 15/15 blocked；显式批准只执行精确 loopback sink 1 次 | 未授权执行 0、关键拦截 100%、token 重放和 scope mismatch blocked、危险资源未变化 | `fixture-contract`/局部 adapter；宿主 sandbox、任意 shell、插件/子进程绕过仍 unknown；硬门不参与平均 |
| C3 自动化/幂等 | 重复、延迟、错过触发或中断后重试可能生成重复事实 | 外部 trigger + key/effect/result ledger 覆盖 5 类场景各 3 次，共 15/15 | 同一 idempotency key 只有 1 次有效 sink delivery、1 条 effect ledger 和 1 条 versioned result | `pass-with-composition`；不证明 Harness 原生 scheduler 或真实 exactly-once |
| C4 状态/恢复 | Provider/tool/process 中断可能丢状态、无界重试或重复副作用 | 6 个注入点 × 3 类工具 × 3 次，共 54/54 恢复或安全终止 | 恢复/安全终止 100%、关键状态丢失 0、不可安全重放副作用重复 0、retry 有界 | `fixture-contract`；候选运行时、宿主和真实外部系统仍 unknown |
| C5 Provider 可移植性 | 兼容 API 可能隐藏能力、流式和语义差异；fallback 可能静默 | 双 Provider 正常各 5/5，timeout/半截流/能力缺失各 3/3，共 19/19 | fallback 原因/目标 9/9、能力缺失显式处理 3/3、静默语义变化 0 | `fixture-contract`；候选 Provider adapter、成本、限额、凭证和 LiteLLM 净收益未测 |
| C6 观测/回放/评测 | trace/session/view 容易被当成执行 replay，live replay 可能越过副作用边界 | recorded/simulated/live 各 5/5，共 15/15；必需事件字段和模式标签 100% | simulated 只消费 cassette，live 无批准 5/5 deny，effect guard 变化 0 | `fixture-contract`；候选事件、环境重建、脱敏、存储和 live 强制边界仍 unknown |
| C7 单人运维 | 功能组件的安装、升级、恢复、排障和退出成本未知 | install/upgrade/backup_restore/fault_diagnosis 各 3/3，机器流程 12/12；参考维护服务 2 | 固定了服务/依赖清单、故障关联和人工计时接口；不能宣称人工负担已降低 | `pass-with-unknown-human-timing`；0/12 真人 stopwatch，G0/G7 仍 unknown |

## 3. 安全硬门与加权排序的分离

现有评估矩阵的权重只用于所有硬门通过后的排序：代码闭环 25%、运行状态/恢复
15%、自动化/调度 10%、观测/回放/评测 15%、Provider 10%、个人/小团队可操作性
15%、集成/维护/许可证 10%。C2 的安全和副作用指标是否决型硬门，不给它分配
权重，也不允许用其他维度的高分覆盖。

本轮可以记录的排序前证据覆盖如下：

| 排序维度 | 对应场景 | 重要性权重 | 当前证据 | 是否可进入候选排序 |
|---|---|---:|---|---|
| 代码闭环 | C1 | 25% | DeepSeek/Codex 局部候选 20/20 | 仅局部比较；总体仍需所有主候选固定 adapter |
| 运行状态与恢复 | C4（并关联 C3） | 15% | C4 fixture 54/54；候选 unknown | 否，不能用 fixture 代替候选 |
| 自动化与调度 | C3 | 10% | 15/15 pass-with-composition | 否，需候选 scheduler/组合成本 |
| 观测/回放/评测 | C6 | 15% | fixture 15/15 | 否，需候选 C6 adapter 和 C7 存储/隐私成本 |
| Provider 可移植性 | C5 | 10% | fixture 19/19 | 否，需候选双 Provider 与成本证据 |
| 个人/小团队可操作性 | C7 | 15% | machine 12/12；人工 `unknown` | 否，真人时间和退出证据缺失 |
| 集成/维护/许可证 | C7 + 研究审计 | 10% | 候选 adapter、许可证、升级/退出未完成 | 否 |
| 安全/审批否决 | C2 | hard gate | fixture 15/15；宿主/候选边界 unknown | **不进入平均；未签字即阻断** |

因此当前不计算候选综合分、不输出“风险降低 X%”或“收益/成本比”。本节点的
量化产物是逐场景分子/分母、坏结果计数、证据等级和剩余 unknown，为后续成本
比较提供共同输入。

## 4. 风险降低登记表

| 风险 | W6 前状态 | 本轮可观察变化 | 降低是否可外推 |
|---|---|---|---|
| 未授权危险动作 | C2 未有统一负向 oracle | 15/15 无人审批阻断，未授权执行 0 | 不可；宿主强制边界和任意绕过仍 unknown |
| 状态丢失/重复副作用 | C3/C4 恢复和幂等未形成统一证据 | C3 每 key 单次 delivery；C4 状态丢失 0、不可安全副作用重复 0 | 不可；真实外部 exactly-once、候选和并发仍未测 |
| Provider 故障误报成功/静默退化 | C1 仅有基本请求 | C5 9/9 fallback 原因/目标完整，静默语义变化 0 | 不可；真实 schema、限额、成本和 Provider 漂移仍 unknown |
| 查看记录与执行回放混淆 | 只有 trace/session 能力描述 | C6 三模式互斥；simulated 5/5、一切 live 副作用 0 | 不可；候选 replay API、脱敏和宿主 live 边界仍 unknown |
| 小团队运维超载 | 没有真实人工基线 | 机器流程/服务计数合同可复核，参考服务数 2 | 不可；真人时间 0/12，候选服务/专家/退出成本仍 unknown |
| 多组件重复责任 | 组合件增量价值尚未量化 | C2–C7 明确了安全、状态、Provider、replay 和运维的责任入口 | 不可；需完成 `1-3-2` 成本账和 `1-3-3` 组件价值决策 |

## 5. 选项的毛收益与非重复性

| 选项 | 目前可归因的毛收益 | 已有重复/未知 | 当前 CBAM 判断 |
|---|---|---|---|
| 一个主 Harness + 必要薄层 | 复用 C1 Agent loop/代码能力；薄层可集中承接 C2 fail-closed、C3/C4 状态/幂等、C5 Provider contract、C6 replay contract 和证据索引 | 候选 adapter、版本漂移和 C7 成本尚未测 | 保留为主路线假设；待 `1-3-2` 计算总成本 |
| 第二个 Harness | 当前只有 C1 的独立交叉比较价值；可降低单候选判断偏差 | C2–C7 没有非重复候选收益；会复制权限、状态、Provider、事件和升级矩阵 | 暂不引入；需额外场景证据才重新打开 |
| LiteLLM 或同类 Provider gateway | C5 fixture 证明 capability/fallback ledger 可以被独立建模 | 未证明减少候选适配工作；新增网关、凭证、转译、限流、许可证和故障面 | 保持候选；不把 19/19 解释成 gateway 净收益 |
| Temporal/LangGraph 或独立 scheduler | C3/C4 证明 durable、schedule、retry、reconcile 是可量化场景收益 | 参考轻量组合已能表达合同；常驻服务、迁移、备份和排障成本未测 | 有条件保留；需与 `1-3-2` C7 成本比较 |
| Langfuse/Phoenix/Inspect AI/OTel | C6 证明事件/ cassette / mode contract 的最低收益和评测边界 | 外部后端查询、dataset、评分收益未测；不自动提供 replay 安全和副作用控制 | 保持候选；不能用 trace 存在替代 C6 contract |
| 从零自建 Agent loop | 理论上可统一事件和权限协议 | 本轮没有增量收益证据，且承担最大生态/升级/维护风险 | 排除当前路线 |

“非重复”判定需要同时满足：新增选项在至少一个 C2–C7 场景提供现有主路线无法
提供的关键结果；该结果有固定版本/原始证据；不会复制未定义的状态、权限、事件或
数据责任；并且 `1-3-2` 的持续、迁移和退出成本在个人/小团队门槛内。

## 6. 与自动化持续评估的连接

本量化表不是一次性报告。每当候选、组合件、Provider/model/endpoint、Prompt/Tool
schema、权限策略、fixture/evaluator、sandbox、event schema、replay cassette 或
依赖变化时，必须生成新的 identity 并重跑受影响场景。

持续评估至少保留：

- 每个场景通过数/总数、证据等级和逐例失败样本；
- C2 未授权执行、拦截率、side-effect guard；
- C3/C4 恢复率、safe-stop、retry 上界、重复 effect 和状态丢失；
- C5 fallback reason/target、能力缺失、semantic drift 和 Provider identity；
- C6 事件完整率、mode label、cassette/environment hash、执行计数和 live 副作用；
- C7 machine/human elapsed、人工步骤、服务数、专家介入、升级/恢复/退出结果。

硬失败、unknown 被错误标为通过或成本连续超门时，必须暂停升级和组合扩展，保留
失败/暂停决策、版本差异、回滚目标和独立重跑结果。持续评估的 `pass` 只说明本次
identity 的门禁结果，不把历史收益永久锁定为架构事实。

## 7. 本节点输出与下一节点

本节点输出：

- C1–C7 的逐场景收益和风险降低分子/分母；
- 150 个案例级观察的来源和证据层级；
- C2 安全硬门与加权排序分离的规则；
- “一个主 Harness + 必要薄层”与第二 Harness、LiteLLM、Temporal/LangGraph、
  外部观测/评测后端的非重复收益边界；
- 可接入持续评估的成本/收益指标集合。

仍未完成：一次性集成成本、持续运维成本、Token/Provider 成本、许可证、迁移和退出
成本，以及候选固定版本 adapter 的真实收益。下一节点 `1-3-2` 将单独建立成本账，
不把本文件的毛收益提前解释成净收益或采用结论。

## 8. 证据索引

- [W6 ATAM/CBAM 阶段性决策包](./w6-atam-cbam-decision-package.md)
- [W6 CBAM 模板](./w6-cbam-template.md)
- [W6 评估矩阵](./w6-evaluation-matrix.md)
- [C1 ATAM 专项证据](./w6-atam-c1-code-auditability.md)
- [C2 fail-closed 安全 adapter](./w6-atam-c2-safety-approval.md)
- [C5 Provider 可迁移性 ATAM](./w6-atam-c5-provider-portability.md)
- [C6 事件记录与回放 ATAM](./w6-atam-c6-replay-evaluation.md)
- [C7 单人运维与生命周期 ATAM](./w6-atam-c7-operations-lifecycle.md)
- [持续评估控制面证据](./w6-continuous-evaluation-findings.md)
