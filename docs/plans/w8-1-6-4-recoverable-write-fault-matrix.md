# W8 `1-6-4`：可恢复本地写操作故障矩阵

状态：`fixture-level evidence assembled / production write HOLD` · 路线类型：
`acceptance/evaluation`

本文把 W7/W8 已有的隔离证据按 Gate B 的 B3–B9 重新归并，回答一个具体问题：
在不写真实项目、不连接真实 Provider、不执行 Git push 或部署的前提下，
composition owner 是否已经具备“可声明、可恢复、可回放、可退出”的本地写操作合同。

本文不是 ZWorkbench 产品写入功能的实现，也不把 fixture 的通过结果升级为生产放行。

## 1. 固定边界

| 边界 | 本轮约束 |
|---|---|
| 主 Harness | Codex `0.139.0`，唯一主 Harness |
| durable owner | 一个 SQLite composition owner，持有 run/approval/effect/result/event/replay metadata |
| Provider | loopback/fake Provider；不读取真实 API key，不访问真实 Ark endpoint |
| sink | case-local reversible fake sink；不触碰 ZWorkbench 工作区真实文件 |
| 人员与服务 | 个人开发者/小团队；常驻维护对象不超过 3 个，不引入第二 Harness、Temporal、LangGraph 或独立观测后端 |
| 未知 effect | `uncertain` 时 safe-stop，先 reconcile，禁止自动重试 |

## 2. 结果总览

| Gate B 子门 | 隔离证据 | 当前判定 | 能否放行真实项目写入 |
|---|---|---|---|
| B3 claim/commit | C4 composition approval 的 effect/result ledger 与同一 `run_id`、`operation_id`、`idempotency_key` | `fixture pass` | 不能；尚未证明真实项目 sink 的提交语义 |
| B4 幂等 | C3 `15/15 pass-with-composition`；同 key 只有一个有效 effect | `fixture pass` | 不能；真实项目查询/reconcile 尚未接入 |
| B5 中断/恢复 | C4 `36/36 recovery controls pass`；状态丢失 0、不安全重复 0、retry≤1、reconcile/safe-stop `36/36` | `fixture pass / native approval unknown` | 不能；需先解决宿主边界与 approval owner |
| B6 backup/restore | owner-backed backup/restore `20/20 checks`；人工耗时 `12.38 秒` | `owner fixture pass` | 不能；跨环境、加密、retention 和真实灾难恢复仍未知 |
| B7 replay | C6 `15/15 pass-with-composition`；simulated `5/5`，live replay default-deny 且副作用 0 | `fixture pass` | 不能；已批准 live replay 未放行 |
| B8 rollback | owner 跨 `0.138.0 → 0.139.0 → 0.138.0` machine compatibility pass；owner schema、配置 identity、既有 ledger 保持 | `partial / workspace rollback unknown` | 不能；未闭合应用/adapter/schema/workspace patch 的统一回滚 |
| B9 diagnosis | 预制故障人工定位 `2 分 51.31 秒`，低于 30 分钟 | `fixture pass` | 不能；真实未知故障和生产数据边界未验证 |

综合结论：B3–B7、B9 在隔离 fixture 层已经形成可复核合同；B8 只有 owner/版本兼容
子集，B1 宿主强制和 B2 Codex native approval 仍是上位硬门。因此 Gate B 保持
`HOLD`，当前允许范围仍是 `local_read_only_run` 和 case-local reversible fake sink。

## 3. 证据矩阵

### 3.1 B3：claim/commit 与 identity 关联

来源：[`C4 composition summary`](../../evaluation/runs/w7-codex-c4-approval-20260831T032346-194000Z/summary.json)。

- 4 个故障点 × 3 类工具 × 3 次重复，共 36 个 case；
- `all_approval_and_effect_ids_correlated=true`；
- `unattended_and_scope_effects_zero=true`；
- `token_replay_effects_zero=true`；
- composition approval owner 产生 approval/effect/result 记录，Codex 不被假定为 durable truth owner；
- `native_approval.observed_cases=0`，且 `native_approval.status` 明确为
  `unknown/not-required-for-composition`。

这证明的是“一个外部 owner 能约束 case-local effect 的 claim/commit 记录”。它不证明
真实 workspace 的原子提交、文件锁、Git index 或远端 API 的提交语义。

### 3.2 B4：幂等与重复触发

来源：[`C3 summary`](../../evaluation/runs/w7-codex-c3-c4-20260830T162343-560708Z/summary.json)。

- 场景包括首次触发、同 key 重复、延迟触发、中断后重试和 missed trigger；
- `15/15 pass-with-composition`；
- `one_effect_per_key=true`；
- 外部 deterministic trigger 被明确标注为 scheduler，不把它写成 Codex 原生 scheduler。

C3 只闭合 owner/fixture sink 的重复抑制。接入真实项目前，必须为实际 sink 定义查询
接口和 reconcile 规则，否则一次“执行成功但 ledger 未提交”的不确定状态不能安全收敛。

### 3.3 B5：中断、恢复、reconcile 和 safe-stop

来源：[`C4 composition summary`](../../evaluation/runs/w7-codex-c4-approval-20260831T032346-194000Z/summary.json)。

阈值及结果：

| 指标 | 阈值 | 结果 |
|---|---:|---:|
| 故障点 | `turn_interrupt`、`provider_timeout`、`tool_timeout`、`process_interrupt` | 4 类均覆盖 |
| 工具类别 | `read-only`、`idempotent`、`approval-required` | 3 类均覆盖 |
| 每格重复 | 3 | 满足 |
| 状态丢失 | 0 | 满足 |
| 不安全副作用重复 | 0 | 满足 |
| 最大 retry | 1 | 满足 |
| reconcile 或 safe-stop | 36/36 | 满足 |
| native approval request | 36 个 case 中 0 个观察到 | `unknown`，不能当作通过 |

因此恢复策略的安全核心是：先读取 effect/result ledger，再决定 reconcile、有限重试或
safe-stop；不是根据 Codex 的自然语言完成文本判断“应该重做”。

### 3.4 B6：owner backup/restore

来源：[`backup/restore evidence`](../../evaluation/runs/w7-codex-c7-human-20260831T180332/README.md)。

在真实 composition owner（SQLite）和 Codex adapter 的隔离 case 中，检查通过：

- owner database、manifest、state JSON 和 schema 均存在；
- `run_id`、`thread_id`、`turn_id`、Provider identity 和 adapter result 均记录；
- SQLite integrity 通过；
- 先损坏 restore target，再用 backup 替换；
- restore 后 state digest 和完整 snapshot 一致；
- 无 effect、Provider 为 loopback；
- 人工 stopwatch 为 `12.38 秒`，低于 C7 的 30 分钟时间阈值。

该结果关闭了“没有真实 composition owner / 没有 backup/restore 物证”的缺口，但没有
关闭备份加密、长期 retention、跨机器恢复、远端备份删除或真实灾难恢复责任。

### 3.5 B7：回放与真实执行分离

来源：[`C6 summary`](../../evaluation/runs/w7-codex-c5-c6-20260830T165822-636804Z/summary.json)。

- `recorded_view`、`simulated_replay`、`live_replay` 三种模式均显式标注；
- 总计 `15/15 pass-with-composition`；
- simulated replay 预期匹配 `5/5`；
- live replay 默认拒绝，Provider/tool/network/外部副作用均为 0；
- 必需 event 字段完整率和 mode label 正确率均为 100%。

这只证明回放边界可以由 composition adapter 约束，不证明 Codex 原生 replay contract，
也不证明经过人工批准的 live replay 可安全连接真实项目。

### 3.6 B8：版本、owner 和 rollback 兼容性

来源：[`owner upgrade compatibility summary`](../../evaluation/runs/w7-codex-owner-upgrade-20260831T095350-497892Z/summary.json)。

该 machine probe 验证：

- 旧版 `0.138.0`、当前版 `0.139.0`、回滚版 `0.138.0` 的 owner schema 都为
  `zworkbench-composition-owner/v1`；
- 配置 identity 保持；
- 升级前的既有 ledger 在升级后和回滚后仍保留；
- 受控 app-server 启动失败被持久化为 `failed`，且无 effect；
- owner reopen 后 state 仍可读取；
- machine checks 全部通过，summary 状态为 `machine-pass / human-unknown`。

该证据只覆盖“Codex 包版本变化下的 owner 兼容性”。仍缺：

1. workspace patch/checkpoint 的回滚目标与冲突处理；
2. adapter schema migration 的 forward/backward contract；
3. backup、replay cassette 与 workspace checkpoint 的一致性回滚；
4. 失败升级后的人工停止、恢复和再次触发 runbook。

故 B8 暂定 `partial`，不允许把 CLI 二进制回滚等价为完整工作台回滚。

### 3.7 B9：故障定位可操作性

已有 C7 人工证据：固定 `fault_id`、run/event identity、候选版本、owner、Provider、
policy/approval、tool/effect/result 和 next action 均可从隔离目录复核；单人耗时
`2 分 51.31 秒`，低于 30 分钟阈值。

该时间关闭的是预制 fixture 的诊断可操作性，不代表真实未知故障一定能在同一时间内
定位，也不代表在真实 Provider 数据进入后可以保存同样完整的日志。

## 4. 上位硬门与停止条件

下列条件仍阻止从 fixture sink 扩展到真实本地项目：

1. **B1 宿主强制边界**：已有 macOS 普通进程写边界机制探针 `3/3`，但 app-server、
   子进程、MCP、凭证、DNS/网络的统一继承和拒绝证据未闭合；
2. **B2 Codex native approval**：`approvalPolicy=on-request` 只在 thread/start
   返回了配置摘要；运行时观察仍为 `item/commandExecution/requestApproval=0`，
   composition approval 不能回填 native approval；
3. **B8 完整 rollback**：workspace/checkpoint/schema/cassette 的统一回滚未知；
4. **真实 Provider Gate A**：真实 endpoint 的数据 retention、远端任务/Webhook/备份
   和逐对象退出责任仍为 unknown；
5. **C7 法律/供应链/退出**：NOTICE、商业/API 边界、独立重建和真实远端退出仍未完全
   签核。

任何 effect 在执行后结果未知，都必须转为 `uncertain → reconcile/safe-stop`；不得
   因 C3/C4/C6 的 fixture pass 自动 retry 或自动触发真实项目写入。

## 5. ATAM / CBAM 决策

### ATAM

| 敏感点 | 本轮观察 | 结论 |
|---|---|---|
| owner 与 Harness identity 对齐 | C3/C4/C6/C7 均保留 run/thread/turn/effect/result 关联 | 可继续采用单 owner；需要持续 schema 回归 |
| effect 不确定状态 | C4 先 reconcile，approval-required 超时 safe-stop | 保持保守策略，暂不追求自动化吞吐 |
| replay 与 live effect 分离 | C6 live replay default-deny | 继续默认只读/模拟回放 |
| 宿主边界 | 普通 sandbox 机制通过，产品继承未知 | 不允许真实写入 |
| 小团队维护成本 | 2 个主要维护对象，未引入常驻组件 | 不引入第二 Harness 或 workflow engine |

### CBAM

当前保留的增量路线是：

`Codex 唯一主 Harness → 一个 composition owner → case-local reversible sink → 证据闭环`

只有在 B1/B2/B8 关闭后，真实本地写入的收益才值得纳入下一轮 CBAM。此时仍需比较
“继续薄层”与“引入 helper broker/容器/第二 Harness”的净收益，至少量化服务数、人工
升级时间、备份/删除责任、排障时间和退出成本；不能用功能数量抵消新的权限 owner。

## 6. 本节点结论与后续

`1-6-4` 的隔离故障矩阵证据已组合完成，但结论不是 Gate B 放行，而是：

- B3–B7、B9：`fixture-level pass-with-composition`；
- B8：`partial`；
- B1/B2：`unknown/HOLD`；
- Gate B：`HOLD`；
- 允许范围：`local_read_only_run`、模拟回放和 case-local reversible fake sink；
- 禁止范围：真实项目写入、Git push、部署、远端任务/Webhook/备份和真实 Provider。

下一执行节点为 `1-6-5`：把 Gate A、Gate B、C7/NOTICE 和个人开发者/小团队成本放到
同一 ATAM/CBAM 复审中，输出最终 `GO / CONDITIONAL / HOLD`。在此之前不改写本节点
为真实写入已通过。
