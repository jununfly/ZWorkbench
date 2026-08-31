# W8 `1-6`：真实 Provider 与可恢复写操作放行决策

状态：`in_progress / HOLD` · 路线类型：`Product execution` · 日期：`2026-09-01`

本文把 W8 第一切片之后的两个扩展方向拆成独立放行 gate：

1. 真实 Provider：允许本地运行把请求发往真实火山方舟或其他远端 Provider；
2. 可恢复写操作：允许运行对本地工作区或其他 sink 产生可恢复、可审计的写副作用。

本文只完成边界、证据要求和决策，不接入真实 Provider、不读取 API Key、不执行真实
写操作，也不把隔离 fixture 的通过结果写成生产能力。

## 1. 结论先行

| Gate | 当前决定 | 允许的范围 | 不能推出的结论 |
|---|---|---|---|
| A：真实 Provider | **`HOLD / UNKNOWN`** | 继续使用 W8 的 loopback/fake Provider；可做官方资料核验和不带凭证的配置设计 | 不能把 OpenAI-compatible endpoint 当成统一合同、统一 retention 或统一删除入口；不能向真实 Ark 发起产品请求 |
| B：可恢复写操作 | **`HOLD`** | 继续验证 case-local、reversible fake sink 和 owner contract；保持 `local_read_only_run` | 不能把 composition approval 通过当成宿主级强制边界；不能放行真实文件写入、Git push、部署或外部任务 |
| W8 第一切片 | **在既定隔离边界内继续** | Codex `0.139.0` + 一个 SQLite composition owner + read-only workspace + loopback/fake Provider | 不代表 Codex native approval、真实 Provider、生产 schema migration 或真实退出责任已经签核 |

总放行条件是：`Gate A ∧ Gate B ∧ C7/NOTICE 边界仍成立`。一个 gate 通过不能替代
另一个 gate；任一关键证据为 `unknown` 都保持 `HOLD/UNKNOWN`，不得用综合分或模型输出
抵消安全硬门。

### 1.1 仍然采用“单主 Harness + 必要薄层”

1-6 不改变 W8 的组合选择：Codex `0.139.0` 仍是唯一主 Harness，SQLite
composition owner 仍是 `run / approval / effect / result / event / backup /
replay metadata` 的唯一 durable truth。真实 Provider 只新增 Provider adapter 和
责任清单；可恢复写操作只新增明确的 effect boundary 和恢复验证。

本节点不引入第二 Harness、Temporal/LangGraph、LiteLLM、常驻观测平台或新的权限
owner。只有当 C2–C7 证明某个组件带来非重复的关键收益，且个人开发者/小团队的服务数、
升级、排障、备份、许可证和退出成本均在阈值内，才另开节点评估。

## 2. 事实分层与当前证据

| 事实 | 来源/证据 | 判定 | 对放行的意义 |
|---|---|---|---|
| 当前第一切片可在隔离环境完成 owner-backed run、记录、导出和本地 backup/restore | `docs/plans/w8-controlled-pilot-scope-and-vertical-slice.md` 与 `1-5-5` evidence | `verified-for-isolated-fixture` | 只支持继续做本地受控验证，不支持真实 Provider 或真实写操作 |
| Codex 的 C3/C4/C5/C6 多数结果依赖 composition adapter；Codex native approval、原生 scheduler 和完整 durable agent state 仍有未知 | [`w7-codex-c3-c4-boundary.md`](./w7-codex-c3-c4-boundary.md)、[`w7-codex-c4-approval-findings.md`](./w7-codex-c4-approval-findings.md) | `pass-with-composition / native-unknown` | 可复用合同，不能提升为宿主强制能力 |
| C7 人工生命周期时间已记录：安装 `17.01s`、升级/回滚 `14.35s`、backup/restore `12.38s`、预制故障定位 `2分51.31秒` | [`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md) | `within-fixture-threshold` | 只证明本次隔离演练；逐包 NOTICE、商业边界、独立重建仍开放 |
| Provider 为火山方舟，OpenAI-compatible endpoint 为 `https://ark.cn-beijing.volces.com/api/coding/v3`，账户范围为个人，用户确认存在远端数据、任务、Webhook 和备份 | Human 提供；[`w7-codex-c7-remote-exit-responsibility.md`](./w7-codex-c7-remote-exit-responsibility.md) | `human-reported / externally-owned` | 这是退出清单的起点，不是资源 ID、retention 或删除结果证据 |
| 火山方舟官方资料 | [`w8-provider-exit-primary-sources.md`](./research/w8-provider-exit-primary-sources.md) 汇总官方 Coding Plan/API/条款页面 | `partially-official-verified / scope-limited` | endpoint、API Key 管理、广义数据处理、账单和账号退出已有官方事实；不能外推为 Coding API 的通用任务/Webhook/备份生命周期或最终零残留 |
| 当前环境对给定 endpoint 的一次未携带凭证 `GET /` | 2026-09-01 评估过程观察，返回 `401 AuthenticationError` | `non-evidence / boundary incident` | 未发送 API Key、Prompt、代码或用户数据；不作为 Provider 能力、条款或安全证明；后续停止访问真实 endpoint |

### 2.1 这次 endpoint 观察的处理

该请求不是计划中的产品验证，也没有使用真实凭证。它只说明服务端对无凭证请求返回
了认证错误，不能说明 API 路径、模型能力、数据 retention、任务/Webhook/backup
行为或删除语义。它被记录为边界事件，不计入任何 `pass`，后续所有真实 Provider
验证必须先完成 Gate A 的人工授权和资料闭环。

## 3. Gate A：真实 Provider 资格

### 3.1 判定矩阵

| 子门 | 必须证明什么 | 最低证据 | 通过阈值 | 当前状态/责任人 |
|---|---|---|---|---|
| A1 Provider identity | 厂商、产品、区域、endpoint、API 版本、模型和协议边界一一对应 | 官方 Coding Plan 页面 + 脱敏配置摘要 + 人工确认账户/项目 | 每一请求的 identity 可落到固定 endpoint/model/region；协议兼容不作为合同主体 | `partial / official-endpoint + human-account` / Human + Provider owner |
| A2 认证路径 | API Key 如何注入、轮换、撤销、审计，且不进入 owner/log/backup | 官方 API Key 获取/管理页面 + 账户 owner 的 key fingerprint 和撤销记录 | ZWorkbench 只接收运行时引用；secret 原文在输入、事件、export、backup 中出现次数为 0；撤销责任人明确 | `partial / official-lifecycle, target-key-unverified` / Human |
| A3 数据边界 | Prompt、代码、文件、output、错误、usage、telemetry 是否离开本地；是否用于训练；区域、子处理者和 retention | Provider 官方隐私/服务协议/数据授权条款，标注章节和生效日期 | 所有传输数据类别、保留期限/删除条件、区域和例外必须能绑定到本次 Coding 调用；广义条款不能替代 endpoint-specific 证据 | `scope-limited / target-retention-unknown` / Provider + 数据责任人 |
| A4 远端资源 | 任务、队列、Agent run、Webhook、备份、对象存储和缓存的创建来源及 owner | 控制台/API 脱敏 inventory：resource ID、创建者、schedule、目标、状态 | “无资源”或每项资源都有 ID、停止/删除动作和责任人；不能以本地 ledger 推断远端不存在 | `unknown / delegated` / Human |
| A5 远端退出 | 停止新请求、撤销 key、停用 schedule/Webhook、导出/删除数据、处理延迟 retention、账单和支持工单 | Provider 官方退出/删除说明 + 账户 owner 实际 runbook + 结果/响应 ID | 可逐项执行、验证并记录；延迟删除、法律留存和备份到期时间可见；不可观察项保持 stop | `unknown` / Human + Provider owner |
| A6 语义兼容 | stream 完成、结构化输出、工具/函数调用、错误、限额和 fallback 是否保留语义 | W6 C5 contract + Provider staging run 的脱敏 event ledger | 正常确定性任务 5/5 语义一致；fallback 100% 有原因/目标；静默模型或能力变化 0 | `not-run` / ZWorkbench |
| A7 安全试点 | 真实 Provider 的最小试用不触碰生产项目或不可逆副作用 | 合成 Prompt、非敏感 workspace、预算上限、网络/credential/effect 记录 | 先 read-only、人工在场、单账户、可停止；任何身份/数据/资源不确定即 safe-stop | `not-authorized` / Human |

Gate A 只有在 `A1–A7` 的关键项全部有可复核证据、且 C7/NOTICE 没有新阻断时，才可
进入一次受控的真实 Provider **只读**试点。它仍不自动放行写操作、远端任务、Webhook
或 Provider 侧备份管理。

### 3.2 Provider 退出责任

ZWorkbench 负责：停止本地 run/schedule/retry、阻断新请求、保护和脱敏本地 owner state、
导出/删除本地副本，并明确告诉操作者数据会离开本地边界。

Provider/账户 owner 负责：远端 Prompt/output/file/log/telemetry、任务、Webhook、备份、
retention、账户、账单和组织资源。当前产品不代替账户 owner 创建或删除这些资源；如果
未来开始代管其中任何资源，必须重新打开资源级 ownership、删除和 C7 gate。

## 4. Gate B：可恢复写操作资格

Gate B 只评估“可以恢复且能解释”的本地写操作。第一阶段不把 Git push、部署、发消息、
创建远端任务或写 Provider 资源当作测试 sink。

| 子门 | 必须证明什么 | 最低证据/阈值 | 当前状态 |
|---|---|---|---|
| B1 宿主边界 | workspace、state、凭证和进程权限由宿主级边界强制，而不是只靠配置声明 | OS sandbox/helper broker 或等价强制证据；越界访问 0；W8 preflight 只能算配置合同 | `HOLD / unknown` |
| B2 approval | 每个 effect 在执行前有可见、范围受限、不可重放的 approval | 5 类危险动作 × 3 次无审批，未授权执行 0；scope mismatch/token replay 0；Codex native approval 仍需单独证据 | `HOLD / composition-only` |
| B3 claim/commit | effect 的 claim、执行、提交和不确定状态由同一 owner durable 记录 | 每个 effect 有 operation ID、resource scope、attempt 和 result；不能用完成文本代替提交 | `not-run-for-real-write` |
| B4 幂等 | 同一逻辑操作重复触发只产生一个可接受结果 | 同一 `idempotency_key` 的有效 sink effect 计数为 1；重复/重试不增副作用；每个 attempt 可查询 | `not-run` |
| B5 中断恢复 | 写入前、写入完成但状态未提交、状态提交后等边界不会误判或重复写 | 每个注入点至少 3 次；100% 恢复或安全终止；关键状态丢失 0；不可安全重放副作用重复 0；retry 有界且有原因 | `composition-fixture-only` |
| B6 backup/restore | owner state、effect ledger、workspace checkpoint 可一起恢复并保持 identity | backup manifest/database/state 完整；SQLite integrity 通过；restore 后 digest/snapshot/operation identity 一致 | `owner-pass / production-unknown` |
| B7 replay | 记录查看、模拟回放和真实执行严格分离 | 必需事件字段完整率 100%；simulated replay 5/5 一致；live replay 默认拒绝且副作用 0 | `composition-pass / live-deny` |
| B8 rollback | 应用/adapter/schema/工作区写入均有回滚目标和恢复窗口 | 版本、schema、owner backup、workspace patch 可回滚；升级失败不丢 evidence；不能只回滚 CLI 二进制 | `HOLD / not-run` |
| B9 诊断 | 失败能从 run/effect/attempt/fault 关联到可执行的下一步 | 预制故障定位 ≤30 分钟；无专家介入；真实环境的未知故障不能被 fixture 时间替代 | `fixture-pass / production-unknown` |

B Gate 只有在 B1–B9 的“宿主强制、审批、幂等、中断恢复和回滚”均闭合后，才可以
从 fake reversible sink 扩到真实本地项目。任何不确定的 effect 都必须进入
`uncertain/safe-stop`，不得自动 retry。

## 5. 既定 C1–C7 阈值如何作用于 1-6

1-6 不重写 W6-0.1 阈值，而是把其适用范围从候选 fixture 收紧到“真实 Provider/真实
写操作的增量证据”。重点硬门如下：

- **C2**：5 类危险动作各重复 3 次，无审批执行次数必须为 0；真实 secret、外网、push、
  deploy 任一出现即硬失败。
- **C3**：相同幂等 key 的有效副作用只能为 1；每个 attempt、schedule、result 和
  effect 都可查询。
- **C4**：每个故障注入点至少 3 次，100% 恢复或安全终止；危险副作用重复 0；retry
  有界且原因可解释。
- **C5**：正常确定性语义 5/5 一致；fallback 原因和目标 100% 记录；静默语义变化 0。
- **C6**：必需事件字段完整率和模式标注率 100%；simulated replay 5/5；live replay
  副作用 0。
- **C7**：首次安装 ≤90 分钟；升级、backup/restore、预制故障定位分别 ≤30 分钟；
  单人无额外维护者介入；需人工维护的常驻服务 ≤3 个。

这些是最低阈值，不是自动放行规则。真实 Provider 数据责任、宿主强制边界、Codex
native approval、完整 NOTICE/商业边界或远端退出任一为 unknown，整体仍不能放行。

## 6. ATAM：敏感点、风险和权衡

### 6.1 敏感点

| ID | 敏感点 | 受影响质量属性 | 一旦改变会影响 |
|---|---|---|---|
| SP-A1 | Provider identity 与认证引用 | 安全、可观测、可退出 | 事件归属、账单责任、撤销路径和 evidence 脱敏 |
| SP-A2 | Provider 数据类别、区域、retention 和远端资源 owner | 隐私、可退出、运维 | 是否允许真实请求，以及退出后能否证明资源处理完毕 |
| SP-B1 | 宿主强制 workspace/credential/process 边界 | 安全、可靠性 | 是否允许任何真实写 effect |
| SP-B2 | approval token 与 effect claim/commit 关联 | 安全、恢复、审计 | 是否能安全 retry，是否会重复执行 |
| SP-B3 | owner state 与 Harness state 的 identity 关联 | 可恢复、可观测、回放 | thread/turn/event/result 是否能解释和恢复 |
| SP-B4 | backup、replay cassette、workspace checkpoint 的一致性 | 恢复、调试、退出 | 事故后是否能重建事实，是否产生敏感数据残留 |
| SP-C1 | 个人开发者/小团队的服务数和人工介入 | 运维、成本、可持续性 | 是否应引入第二 Harness、gateway 或 workflow engine |

### 6.2 风险清单

| ID | 风险 | 触发信号 | 处置 |
|---|---|---|---|
| R-A1 | OpenAI-compatible 只代表协议表面兼容，不代表数据/合同/资源语义兼容 | Provider identity、条款或资源 API 缺失 | 按 Provider/账户/endpoint 单独建账，保持 Gate A hold |
| R-A2 | 远端资源被误认为不存在，或退出时遗漏任务/Webhook/备份 | 只有本地日志，没有远端 resource ID/retention 证据 | 账户 owner 做脱敏 inventory；未知即 safe-stop |
| R-B1 | preflight 看起来通过，但宿主实际仍可越界写入 | 只有配置测试，没有 OS/broker enforcement | 先补宿主级 C2 证据；在此之前禁止真实 write |
| R-B2 | 中断发生在 effect 与 ledger 提交之间，自动重试造成重复副作用 | effect 状态为 `unknown`，没有 reconcile | 不自动 retry；以 operation ID、sink 查询和人工接管收敛 |
| R-B3 | Codex 内部状态与 composition owner 状态漂移 | 缺少 thread/turn/event/result 关联或版本 schema 变化 | owner 为唯一 truth；schema/identity 不完整则停止新运行 |
| R-C1 | 组合件虽能补能力，但维护成本不适合单人 | 服务数、人工排障、升级/备份时间超阈值 | CBAM 重新计算；不引入或退出，不用功能数量抵消 |

### 6.3 关键权衡

| 权衡 | 当前选择 | 理由 |
|---|---|---|
| 真实 Provider 的即时收益 vs 远端数据/退出不确定性 | 先 HOLD；保留 loopback/fake baseline | 真实请求会引入不可由本地 ledger 观察的资源和 retention 责任 |
| Harness 原生状态 vs composition owner | owner 保持唯一 durable truth，Harness 仅作 adapter evidence | 防止第二状态源无法备份、回放或退出 |
| 自动 retry vs 不确定 effect | 不确定即停止，先 reconcile | 副作用安全优先于吞吐和表面成功率 |
| 轻量薄层 vs Temporal/LangGraph/LiteLLM 等常驻组件 | 继续单主 Harness + 必要薄层 | 小团队尚未有增量收益证据，避免提前增加服务/权限/迁移 owner |

## 7. CBAM：增量收益是否值得增量成本

| 选项 | 明确增量收益 | 新增成本/风险 | 当前姿态 |
|---|---|---|---|
| O0：维持 W8 第一切片 | 可观测、可导出、可恢复的本地只读运行；零真实 Provider 风险 | 不能完成真实远端任务或项目写入 | **当前基线，GO-within-W8** |
| O1：真实 Provider 薄 adapter | 真实模型能力、真实限额/延迟和 Provider 语义证据 | 数据离境、retention、账单、资源退出、凭证维护、C5/C6 回归 | **条件候选；Gate A 全部通过前不引入** |
| O2：owner + reversible write boundary | 可处理受控本地修改，并验证恢复/回滚合同 | 宿主 sandbox、approval、幂等、reconcile、备份和故障排查 | **条件候选；Gate B 全部通过前不引入** |
| O3：第二 Harness | 可能增加某类任务或模型能力 | 双状态、双权限、双升级矩阵、事件/Provider 语义分裂 | **暂不引入；需 C2–C7 非重复收益** |
| O4：LiteLLM/Temporal/LangGraph/独立观测后端 | 可能补 Provider 路由、durable workflow 或查询/评测 | 常驻服务、凭证与数据面、迁移、许可证、退出和新的单点 | **保持候选；不能用功能清单代替 CBAM 证据** |

当前 CBAM 判断：O1/O2 的潜在收益是真实的，但尚未超过其数据责任、宿主安全和退出
成本的证据门槛。O3/O4 没有被 1-6 自动授权；如果未来引入，必须携带增量收益、维护
时间、服务数、备份/删除和替换路径的同批次 C2–C7 evidence。

## 8. 下一步执行顺序

按 roadmap 子节点执行，不跳过 gate：

1. **`1-6-1` Provider 证据与远端资源 inventory**：只收集官方文档/条款和 Human
   账户信息；明确 endpoint、认证路径、数据类别、任务/Webhook/backup、retention、
   账单、删除入口和责任人；没有凭证值，没有真实 API 调用。
2. **`1-6-2` 真实 Provider 只读 staging 资格**：只有 `1-6-1` 关闭关键 unknown 后，
   用合成 Prompt、隔离 workspace、人工在场和预算上限验证 C5/C6；不启用 effect、
   scheduler、Webhook 或远端资源创建。
3. **`1-6-3` 宿主强制边界与 native approval**：获得 OS/broker 级越界阻断证据，
   并区分 Codex native approval 与 composition approval。
4. **`1-6-4` reversible write 故障矩阵**：先用本地 fake sink 做 B3–B9，验证 claim、
   idempotency、interruption、reconcile、backup/restore、replay 和 rollback；仍不
   写真实项目。
5. **`1-6-5` ATAM/CBAM 复审与放行决定**：将增量收益和成本放在同一批次，输出
   `GO / CONDITIONAL / HOLD`，并回归 C2–C7；任何关键 unknown 保持 HOLD。

在 `1-6-1` 完成前，唯一安全的“下一动作”是资料核验和责任清单填充，而不是配置
真实 Provider 或开始写入功能。

## 9. 相关证据

- [`w8-controlled-pilot-scope-and-vertical-slice.md`](./w8-controlled-pilot-scope-and-vertical-slice.md)
- [`w7-codex-c3-c4-boundary.md`](./w7-codex-c3-c4-boundary.md)
- [`w7-codex-c4-approval-findings.md`](./w7-codex-c4-approval-findings.md)
- [`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md)
- [`w7-codex-c7-remote-exit-responsibility.md`](./w7-codex-c7-remote-exit-responsibility.md)
- [`w6-fixtures-and-thresholds.md`](./w6-fixtures-and-thresholds.md)
- [`w6-atam-template.md`](./w6-atam-template.md)
- [`w6-cbam-template.md`](./w6-cbam-template.md)
- [`w7-codex-c7-notice-commercial-boundary.md`](./research/w7-codex-c7-notice-commercial-boundary.md)

本文件的 `HOLD/UNKNOWN` 是工程放行状态，不是对火山方舟、Codex 或任何 Provider 的
法律意见，也不是对其不存在某项能力的负面结论。
