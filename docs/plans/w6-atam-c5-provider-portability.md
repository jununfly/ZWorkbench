# W6 ATAM-C5：多 Provider 可迁移性、故障切换与显式降级

状态：`completed` · `acceptance/evaluation` · 不是 ZWorkbench 产品实现，也不是候选 Harness 已具备 C5 能力的证明

本文件收口路线图节点 `1-2-3` 的 ATAM 场景定义，并解释 C5 首轮 fixture
contract 对架构决策的影响。它把“支持多个 Provider”拆成能力协商、故障归因、有限
切换、语义一致性和证据可追责几个独立问题；不把兼容 HTTP API 或候选无关 router
的通过外推成产品级 Provider 抽象。

## 1. ATAM 质量属性场景

| 要素 | 冻结定义 |
|---|---|
| 刺激 | 双 Provider 执行同一确定性任务；分别注入正常响应、timeout、半截流和 structured output 能力缺失 |
| 环境 | 固定候选 Harness 源码/版本、模型、endpoint、Prompt/Tool schema、能力声明和 loopback fake Provider；无真实凭证、生产数据和外网 |
| 响应 | 请求前探测能力；每次 attempt 保留 Provider 身份；故障记录 reason；fallback 记录 from/to、原因和最终 semantic result；能力不足只能显式降级或安全失败 |
| 度量 | 正常语义一致 `5/5`/Provider；故障与能力缺失场景各重复 `3` 次；fallback 原因/目标记录率 `100%`；能力缺失显式处理率 `100%`；无 ledger 的静默 Provider/model 切换 `0`；fixture unknown 不得转化为候选通过 |
| 证据 | run manifest、fixture/router/runner hash、capability ledger、provider event ledger、attempt history、fallback/degradation ledger、逐例 semantic oracle 和候选 unknown ledger |

## 2. 首轮 fixture 结果

证据：[W6-0.1 C5 双 Provider 故障切换与显式降级](./w6-c5-provider-failover-findings.md)。正式
Run：`w6-0.1-c5-20260830T112617-960750Z`。

| 案例组 | 覆盖 | 期望语义 | 结果 |
|---|---:|---|---:|
| `normal-a` | 5 | fake-a 正常完成 `fixture-ok` | 5/5 |
| `normal-b` | 5 | fake-b 正常完成 `fixture-ok` | 5/5 |
| `timeout-once` | 3 | 记录 timeout，切换 fake-a | 3/3 |
| `stream-interrupt-once` | 3 | 记录半截流，切换 fake-a | 3/3 |
| `structured-output-unsupported` | 3 | 请求前识别能力缺失，显式切换 fake-a | 3/3 |
| 合计 | 19 | 保持同一 semantic oracle | **19/19** |

冻结身份：fixture manifest SHA-256 为
`182ba60e68bf79a8f328be79f77f33562db2c0bd8302c16ec44a14b8a8fac2d0`，fixture source
SHA-256 为 `525d6c320865d6085df57a3f619f2ef3f6f5f461a2fc7c6246817ca78dd3704c`，router
SHA-256 为 `32057c460e527286be5a0068c29601fa7ff245d8a27b7024d3315de296b04fb6`，runner
`w6-c5-runner/v1` 的 SHA-256 为
`3bdfe2c2986cd1af54cf928f177487f0386efda2a22f02f6862a0f9d06bc2463`。

观察到的聚合门槛：fallback 原因/目标 `9/9`，能力缺失显式处理 `3/3`，静默语义
变化 `0`，所有 endpoint 均为 `127.0.0.1`，真实 Provider 和不可逆副作用为 `0`。

## 3. C5 的协议语义

### 3.1 正常请求不是迁移证明

fake-a 和 fake-b 对 plain 任务都返回相同答案，router 归一化为
`{"answer":"fixture-ok"}`。这证明两个 endpoint 在最小请求面上可被同一 runner
调用；它不能证明工具调用参数、流式完成标记、structured schema、token 用量、限流
语义或错误分类在真实 Provider 之间一致。

### 3.2 故障切换必须有原因、有界且可回放

timeout 场景在 response header 前失败；stream 场景收到首个 SSE event 后因缺少完成
标记而失败。两者都保留失败 attempt，不在原 Provider 上静默重试，再写入
`provider.fallback`，明确切换到 fake-a。切换不是“成功的另一条路径”，而是一次需要
审计和评测的降级事件。

### 3.3 能力缺失必须在请求前暴露

fake-b 声明 `tool_calls` 和 `streaming`，不声明 `structured_output`。要求 JSON schema
的任务在发起完成请求前生成 `capability_missing:structured_output`，记录
degradation/fallback ledger，再由 fake-a 以 structured response 完成。

该语义只说明能力差异可以被显式建模；它不说明“声明支持”就等于 schema 兼容，也不
说明所有 Provider 的 tool-call 参数和结果语义可以被一个通用接口无损表达。

## 4. 架构事实与责任边界

| 能力 | C5 当前事实 | W7 必须确认的 owner |
|---|---|---|
| Provider wire protocol、stream parser、tool/structured schema | 本轮由 loopback fake Provider 和候选无关 router 固定 | 主 Harness 的 Provider 接口或薄 adapter；需保留原生错误/完成标记 |
| 能力探测与 capability contract | router 在请求前探测并落 ledger | 由 Provider adapter 或 ZWorkbench contract owner 统一负责；版本/声明变化触发回归 |
| fallback/degradation policy | 本轮固定为“明确 timeout/流中断/能力缺失后切 fake-a”，同 Provider retry 关闭 | 产品中必须有单一 owner；需决定由主 Harness、ZWorkbench router 还是网关拥有 |
| Provider/model/endpoint 身份 | 每个 capability、attempt、request、response 都记录 | 跨 Run evidence ledger；禁止只依赖不可查询 session log |
| 成本、限额、隐私与数据驻留 | 本轮没有真实 Provider 数据 | 产品边界和 Provider policy；不能由兼容层默认推断 |
| 跨 Run 状态、幂等和副作用 | 本轮只验证 semantic result，无真实副作用 | 与 C3/C4 的 state/effect/retry owner 串联，不能让 fallback 绕过安全合同 |

## 5. ATAM 风险、敏感点与权衡点

| ID | 类型 | 判断 | 触发条件 | 处理与证据 |
|---|---|---|---|---|
| R-C5-01 | Risk | 兼容 HTTP API 被误读为完整 Provider 兼容 | 切换 Provider、启用 tool call、stream 或 structured output | 固定 wire/schema/capability contract；候选 adapter 必须保留原生事件和失败样本 |
| R-C5-02 | Risk | Provider/model 静默切换，导致成本、能力或语义变化不可解释 | timeout、限流、额度耗尽、模型路由、配置漂移 | fallback ledger 必须有 from/to、reason、attempt、semantic result；缺失即 fail-closed unknown |
| R-C5-03 | Risk | fallback 后重复外部副作用或绕过审批 | Provider 故障发生在 tool/effect 已提交之后 | 将 C5 fallback 与 C2 approval、C3 idempotency、C4 reconcile 串联；没有 effect ledger 不得自动重试 |
| R-C5-04 | Risk | 能力声明不完整或漂移，降级被伪装成成功 | capability endpoint、模型、schema 或版本变化 | capability contract 版本化；持续评估检测 identity/hash 漂移并 pause |
| SP-C5-01 | Sensitivity point | capability endpoint 和声明集合 | Provider/模型/adapter 升级 | 纳入 evaluation identity；声明变化触发 C5 回归 |
| SP-C5-02 | Sensitivity point | SSE 完成标记、错误分类和 stream parser | Provider 返回半截流、非标准错误或重试头 | 用 timeout/stream interrupt fixture 保留原始事件 hash 和 failure reason |
| SP-C5-03 | Sensitivity point | structured schema、tool schema 和参数语义 | Provider 宣称支持但实际转译不同 | 候选级 adapter 以 schema oracle、tool-result ledger 和语义对照验证 |
| TP-C5-01 | Trade-off point | 一个主 Harness + 薄 Provider adapter vs 引入 Provider gateway | Provider 数量、schema 转译和限流治理增长 | 当前保留“主 Harness + 薄层”；只有 gateway 减少的重复适配成本超过运维/凭证/转译/许可证故障面才引入 |
| TP-C5-02 | Trade-off point | Provider fallback 可用性 vs 最低共同能力退化 | 主 Provider 缺少 structured/tool 能力 | fallback 只可在能力和语义 oracle 允许时启用；否则显式 safe-fail，不以成功率换静默退化 |
| TP-C5-03 | Trade-off point | 多 Harness 交叉覆盖 vs 重复 Provider、权限、状态、事件矩阵 | 第二 Harness 只增加同一 Provider fixture 的通过样本 | C5 不产生引入第二 Harness 的非重复收益；需等 C2–C7 和 CBAM 总成本证据 |

## 6. CBAM 增量决策

| 选项 | 可量化收益 | 增量成本/风险 | 当前姿态 |
|---|---|---|---|
| 一个主 Harness + 薄 Provider adapter | 保留主 Harness 的代码闭环；每个 Provider 只承担 endpoint/config/schema/stream/capability 映射 | adapter 仍需随候选版本、模型和 Provider 漂移维护；必须跨 C2–C6 保留 ledger | **主路线，进入候选级验证** |
| LiteLLM 或同类 gateway | 可能集中 endpoint、路由、凭证和部分协议转译 | 新增网关服务、限流/成本语义、凭证边界、许可证、故障归因和升级成本 | **保持候选，不因 fixture 通过引入** |
| 第二个执行 Harness | 可能增加模型/Provider 覆盖或局部代码能力 | 复制 loop、权限、状态、replay、Provider 和小团队运维矩阵 | **不因 C5 引入** |
| 从零重写 Agent loop | 理论上可统一所有语义和事件 | 同时承担工具生态、权限、恢复、回放、Provider 和长期维护 | **排除当前路线** |

本轮的 CBAM 判断不是“永远不使用 gateway 或第二 Harness”，而是把它们设为可被
重新打开的备选：必须提供非重复能力收益、候选固定版本证据和 C7 个人开发者/小团队
维护成本对照；否则保持一个主 Harness 加薄层。

## 7. 候选状态与不可接受边界

DeepSeek Harness、Pi Agent Harness、Codex Harness、OpenCode、Goose 当前 C5 均为
`unknown`。正式 Run 的 candidate baseline 明确记录原因：没有候选专属、固定源码/版本
的 C5 adapter；fixture contract pass 不能转化为候选 pass。

不可接受边界：

- 无 fallback/degradation ledger 的 Provider/model 静默切换；
- 用“OpenAI-compatible”标签替代 tool、stream、structured schema 的逐项验证；
- fallback 后丢失失败原因、Provider 身份、attempt history 或 semantic result；
- fallback 重放已发生但未 reconcile 的不可幂等副作用；
- 用真实凭证、真实 Provider 或外部网络扩大本轮 fixture 的证据范围；
- 用 fixture 通过、C1 请求成功或平均分抵消候选级 C5 unknown。

## 8. W7 入口与下一步

完成 C5 fixture/ATAM 收口后，W7 仍需按同一合同为至少一个主候选建立固定版本
adapter，至少验证：

1. 候选真实 Provider 配置与 Provider/model/endpoint 身份是否可绑定；
2. 候选原生 stream、tool-call、structured-output 事件是否能映射且不丢失败原因；
3. timeout、半截流、能力缺失和显式 fallback 是否与 C2–C4 的审批、幂等、恢复合同一致；
4. Provider/model/endpoint 漂移是否触发持续评估 pause，而不是静默改变结果；
5. adapter 的维护步骤、服务数量和排障时间是否满足个人开发者/小团队约束。

候选在满足上述条件、绑定完整版本/配置并保留可复核失败与通过样本前继续保持
`unknown`。本节点完成不等于 W6 选择主 Harness，也不授权开始 ZWorkbench 产品实现。

## 9. 证据索引

- [W6-0.1 C5 fixture findings](./w6-c5-provider-failover-findings.md)
- [C1 ATAM 专项证据](./w6-atam-c1-code-auditability.md)
- [C2 fail-closed 安全 adapter](./w6-atam-c2-safety-approval.md)
- [C4 中断、恢复与副作用重试](./w6-c4-recovery-findings.md)
- [W6 ATAM/CBAM 模板](./w6-atam-template.md)
- [持续评估控制面证据](./w6-continuous-evaluation-findings.md)
