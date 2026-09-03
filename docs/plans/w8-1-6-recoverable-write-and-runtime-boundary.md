# W8：可恢复本地写操作与运行边界决策

状态：`in_progress / local-write-HOLD / external-provider-out-of-roadmap` · 路线类型：`Product execution` · 日期：`2026-09-01`

本文只记录 W8 第一切片之后的本地可恢复写操作与运行边界。真实 Provider 的账户、
数据和退出责任属于路线外的账户 owner 事务；需要时只通过 `docs/references/` 中的
独立本地安全 runner 按需执行，不构成 ZWorkbench 核心开发或发布前置条件。

本文只完成边界、证据要求和决策，不接入真实 Provider、不读取 API Key、不执行真实
写操作，也不把隔离 fixture 的通过结果写成生产能力。

## 1. 结论先行

| Gate | 当前决定 | 允许的范围 | 不能推出的结论 |
|---|---|---|---|
| B：可恢复写操作 | **`HOLD`** | 继续验证 case-local、reversible fake sink 和 owner contract；保持 `local_read_only_run` | 不能把 composition approval 通过当成宿主级强制边界；不能放行真实文件写入、Git push、部署或外部任务 |
| W8 第一切片 | **在既定隔离边界内继续** | 目标为 DSH 主 Harness + Codex `0.139.0` Worker + 一个 SQLite composition owner + read-only workspace + loopback/fake Provider；当前代码仍是 Codex-only 回退 | 不代表 Codex native approval、真实写操作或生产 schema migration 已经签核 |

W8 本地写操作的放行条件是：`Gate B ∧ C7/NOTICE 边界仍成立`。任一本地安全硬门
为 `unknown` 都保持 `HOLD`，不得用综合分或模型输出抵消。路线外 Provider 资料不产生
新的 W8 roadmap 待办。

### 1.1 目标组合与当前回退基线

2026-09-03 的目标组合是 DSH 主 Harness + 进程外 Codex `0.139.0` Coding Worker；
当前代码中的 Codex-only 路径仅作为可运行回退基线。无论目标 bridge 还是回退路径，
SQLite composition owner 都是 `run / approval / effect / result / event / backup /
replay metadata` 的唯一 durable truth。外部 Provider 只在按需 runner 中作为被测
远端，不新增 W8 核心状态 owner；可恢复写操作只新增明确的 effect boundary 和恢复验证。

本节点不引入第二个顶层 Harness、Temporal/LangGraph、LiteLLM、常驻观测平台或新的权限
owner。只有当 C2–C7 证明某个组件带来非重复的关键收益，且个人开发者/小团队的服务数、
升级、排障、备份、许可证和退出成本均在阈值内，才另开节点评估。

## 2. 事实分层与当前证据

| 事实 | 来源/证据 | 判定 | 对放行的意义 |
|---|---|---|---|
| 当前第一切片可在隔离环境完成 owner-backed run、记录、导出和本地 backup/restore | `docs/plans/w8-controlled-pilot-scope-and-vertical-slice.md` 与 `1-5-5` evidence | `verified-for-isolated-fixture` | 只支持继续做本地受控验证，不支持真实 Provider 或真实写操作 |
| Codex 的 C3/C4/C5/C6 多数结果依赖 composition adapter；Codex native approval、原生 scheduler 和完整 durable agent state 仍有未知 | [`w7-codex-c3-c4-boundary.md`](./w7-codex-c3-c4-boundary.md)、[`w7-codex-c4-approval-findings.md`](./w7-codex-c4-approval-findings.md) | `pass-with-composition / native-unknown` | 可复用合同，不能提升为宿主强制能力 |
| C7 人工生命周期时间已记录：安装 `17.01s`、升级/回滚 `14.35s`、backup/restore `12.38s`、预制故障定位 `2分51.31秒` | [`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md) | `within-fixture-threshold` | 只证明本次隔离演练；逐包 NOTICE、商业边界、独立重建仍开放 |
## 3. Gate B：可恢复写操作资格

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

## 4. 既定 C1–C7 阈值如何作用于 1-6

本文件不重写 W6-0.1 阈值；C1–C7 在本节点继续服务于 W8 本地产品与隔离 fixture。
重点硬门如下：

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

这些是最低阈值，不是自动放行规则。宿主强制边界、Codex native approval、未知 effect
或完整 NOTICE/商业边界任一为 unknown，本地写操作仍不能放行。

## 5. ATAM：敏感点、风险和权衡

### 6.1 敏感点

| ID | 敏感点 | 受影响质量属性 | 一旦改变会影响 |
|---|---|---|---|
| SP-1 | 宿主强制 workspace/credential/process 边界 | 安全、可靠性 | 是否允许任何真实写 effect |
| SP-2 | approval token 与 effect claim/commit 关联 | 安全、恢复、审计 | 是否能安全 retry，是否会重复执行 |
| SP-3 | owner state 与 Harness state 的 identity 关联 | 可恢复、可观测、回放 | thread/turn/event/result 是否能解释和恢复 |
| SP-4 | backup、replay cassette、workspace checkpoint 的一致性 | 恢复、调试、退出 | 事故后是否能重建事实，是否产生敏感数据残留 |
| SP-5 | 个人开发者/小团队的服务数和人工介入 | 运维、成本、可持续性 | 是否应引入第二 Harness、gateway 或 workflow engine |

### 6.2 风险清单

| ID | 风险 | 触发信号 | 处置 |
|---|---|---|---|
| R-1 | preflight 看起来通过，但宿主实际仍可越界写入 | 只有配置测试，没有 OS/broker enforcement | 先补宿主级 C2 证据；在此之前禁止真实 write |
| R-2 | 中断发生在 effect 与 ledger 提交之间，自动重试造成重复副作用 | effect 状态为 `unknown`，没有 reconcile | 不自动 retry；以 operation ID、sink 查询和人工接管收敛 |
| R-3 | Codex 内部状态与 composition owner 状态漂移 | 缺少 thread/turn/event/result 关联或版本 schema 变化 | owner 为唯一 truth；schema/identity 不完整则停止新运行 |
| R-4 | 组合件虽能补能力，但维护成本不适合单人 | 服务数、人工排障、升级/备份时间超阈值 | CBAM 重新计算；不引入或退出，不用功能数量抵消 |

### 6.3 关键权衡

| 权衡 | 当前选择 | 理由 |
|---|---|---|
| Harness 原生状态 vs composition owner | owner 保持唯一 durable truth，Harness 仅作 adapter evidence | 防止第二状态源无法备份、回放或退出 |
| 自动 retry vs 不确定 effect | 不确定即停止，先 reconcile | 副作用安全优先于吞吐和表面成功率 |
| 轻量薄层 vs Temporal/LangGraph/LiteLLM 等常驻组件 | 继续单主 Harness + 必要薄层 | 小团队尚未有增量收益证据，避免提前增加服务/权限/迁移 owner |

## 6. CBAM：增量收益是否值得增量成本

| 选项 | 明确增量收益 | 新增成本/风险 | 当前姿态 |
|---|---|---|---|
| O0：维持 W8 第一切片 | 可观测、可导出、可恢复的本地只读运行；loopback/fake Provider 风险可控 | 不能完成真实远端任务或项目写入 | **当前基线，GO-within-W8** |
| O2：owner + reversible write boundary | 可处理受控本地修改，并验证恢复/回滚合同 | 宿主 sandbox、approval、幂等、reconcile、备份和故障排查 | **条件候选；Gate B 全部通过前不引入** |
| O3：第二 Harness | 可能增加某类任务或模型能力 | 双状态、双权限、双升级矩阵、事件/Provider 语义分裂 | **暂不引入；需 C2–C7 非重复收益** |
| O4：LiteLLM/Temporal/LangGraph/独立观测后端 | 可能补 Provider 路由、durable workflow 或查询/评测 | 常驻服务、凭证与数据面、迁移、许可证、退出和新的单点 | **保持候选；不能用功能清单代替 CBAM 证据** |

当前 CBAM 判断：O2 仍受本地写操作 Gate B 约束。O3/O4 没有被 W8 自动授权；如果未来
引入，必须携带增量收益、维护时间、服务数、备份/删除和替换路径的同批次 C2–C7 evidence。

## 7. 下一步执行顺序

1. **`1-6-3` 宿主强制边界与 native approval**：获得 OS/broker 级越界阻断证据，
   并区分 Codex native approval 与 composition approval。
2. **`1-6-4` reversible write 故障矩阵**：先用本地 fake sink 做 B3–B9，验证 claim、
   idempotency、interruption、reconcile、backup/restore、replay 和 rollback；仍不
   写真实项目。
3. **`1-6-5` ATAM/CBAM 复审与放行决定**：将增量收益和成本放在同一批次，输出
   `GO / CONDITIONAL / HOLD`，并回归 C2–C7；任何关键 unknown 保持 HOLD。

## 8. 相关证据

- [`w8-controlled-pilot-scope-and-vertical-slice.md`](./w8-controlled-pilot-scope-and-vertical-slice.md)
- [`w7-codex-c3-c4-boundary.md`](./w7-codex-c3-c4-boundary.md)
- [`w7-codex-c4-approval-findings.md`](./w7-codex-c4-approval-findings.md)
- [`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md)
- [`w7-codex-c7-remote-exit-responsibility.md`](./w7-codex-c7-remote-exit-responsibility.md)
- [`w6-fixtures-and-thresholds.md`](./w6-fixtures-and-thresholds.md)
- [`w6-atam-template.md`](./w6-atam-template.md)
- [`w6-cbam-template.md`](./w6-cbam-template.md)
- [`w7-codex-c7-notice-commercial-boundary.md`](./research/w7-codex-c7-notice-commercial-boundary.md)

本文件的 `HOLD/UNKNOWN` 是本地写操作工程放行状态，不是对 Codex 或任何 Provider
能力的法律或商业意见。
