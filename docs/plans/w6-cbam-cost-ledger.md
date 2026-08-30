# W6 CBAM-2：一次性、持续、迁移与退出成本账

状态：`completed` · `acceptance/evaluation` · 适用约束：个人开发者或小团队 · 不是生产费用报价，也不是 W7 最终采用结论

本文件收口路线图节点 `1-3-2`。它把候选 Harness、Provider gateway、编排器、观测/评测
后端和必要薄层的成本分成一次性、持续、迁移/锁定和退出四类，并将“已观测”“可计算
但未测量”“未知”明确区分。W6 没有真实 Provider、真实部署或真人 stopwatch，因此
不能凭空给出 Token 价格、月度运维人时或完整 TCO。

## 1. 成本分类与测量规则

| 类别 | 计入内容 | 必须记录的单位 | 当前可用证据 |
|---|---|---|---|
| 一次性成本 | 候选安装、版本绑定、Provider/tool/replay adapter、schema/策略接入、数据迁移准备 | 人分钟、机器分钟、变更文件/接口数、一次性服务与依赖数 | C2–C6 合同显示 adapter 面；真实候选人时未知 |
| 持续成本 | Token、Provider/网关费用、存储、常驻服务、备份、升级、漏洞修复、回归运行、排障 | 每次 Run Token/费用、GB/月、服务数、维护人分钟/月、回归案例数 | fake Provider 无 Token；参考维护服务数 2；真实月度成本未知 |
| 迁移/锁定成本 | 双写/双跑、协议转译、历史 ledger/cassette 迁移、兼容测试、回滚窗口、供应商锁定 | 迁移人分钟、重跑案例数、失败样本数、停机/并行运行时间、不可导出字段数 | 版本/hash 和 cassette 合同已定义；真实替换演练未知 |
| 退出成本 | 停服、数据导出/删除、替换 adapter、恢复独立可读性、许可证清理、残留凭证/权限撤销 | 导出/验证人分钟、残留服务数、不可导出 artifact 数、替代方案恢复时间 | 本轮未做候选退出演练，保持 unknown |

### 1.1 不允许混用的时间

- `machine_elapsed_seconds`：fixture/runner subprocess 墙钟，仅是机器执行下界；
- `human_elapsed_minutes`：单一真实操作者按 runbook 的 stopwatch 时间，才可用于
  C7/G0/G7；
- 工程适配人时：编写、调试和维护候选 adapter 的工作量，不能用一次 runner 执行时间替代；
- Provider latency：模型响应延迟，不等于 Provider 费用或人工等待成本。

任何成本项缺少对应单位或来源，都写为 `unknown`，不填零。

## 2. W6-0.1 成本信号

| 指标 | 当前结果 | 证据等级 | 成本含义 |
|---|---:|---|---|
| C1 DeepSeek 命令耗时 | `5.920s / 10` 次 | 局部 measured-candidate | 仅为候选命令运行时；不含安装、Token、Provider、人工确认或适配工程 |
| C1 Codex 命令耗时 | `11.827s / 10` 次 | 局部 measured-candidate | 同上；不能据此断言 Codex 总成本更高或更低 |
| C1 候选案例 | `20` | measured-candidate 局部 | 只说明 C1 交叉基线规模 |
| C2–C6 fixture 案例 | `118` | fixture-contract/pass-with-composition | 说明合同/评估资产覆盖，不是候选运维工时 |
| C7 机器流程 | `12/12 pass` | fixture-contract | 参考操作合同可自动检查，不是人工成本通过 |
| C7 真人计时 | `0/12` | unknown | 安装 ≤90、其他 ≤30 分钟门均不能签字 |
| 参考维护服务 | `2/3`：scheduler、evidence-ledger | fixture reference | Provider、宿主 OS 排除；候选真实服务数未知 |
| 参考额外专家 | `0` | fixture reference | 只说明参考 runbook 声明无需专家，不代表候选无需专家 |
| 真实 Provider/Token/存储费用 | 未测 | unknown | 本轮只用 loopback fake Provider，不能外推价格、限额或流量 |
| 候选固定版本 adapter 工程量 | 未测 | unknown | 五个候选 C5–C7 仍 unknown，没有可审计人时 |
| 迁移/退出演练 | 未测 | unknown | 不能宣称可导出、可替换、可停服或无锁定 |

C2–C6 的正式合同案例合计 `118`：C2 `15` + C3 `15` + C4 `54` + C5 `19` + C6
`15`。加上 C1 `20` 和 C7 `12`，W6 共保存 `150` 个案例级观察；案例数不是
成本单位，也不能把通过数折算成人时节省。

## 3. 统一成本模型

以下公式只规定 W7 的采集方式，不填入未经测量的值：

```text
one_time_person_minutes
  = candidate_binding
  + provider_adapter
  + safety_state_replay_adapter
  + fixture/evaluator_integration
  + initial_runbook

monthly_operating_cost
  = run_volume × provider_token_cost
  + run_volume × gateway_or_fallback_overhead
  + event_and_cassette_storage
  + backup_and_restore_operations
  + upgrade_and_regression_person_minutes
  + incident_diagnosis_person_minutes
  + maintained_service_cost

migration_cost
  = export_and_transform_person_minutes
  + dual_run_and_reconciliation
  + historical_ledger/cassette_compatibility
  + rollback_window
  + temporary_parallel_infrastructure

exit_cost
  = final_export_and_independent_verification
  + data_deletion_and_credential_revocation
  + adapter_replacement
  + service_shutdown_and_residual_cleanup
  + license/commercial_exit_work
```

计算时必须分别报告现金成本、机器资源、工程人时和操作者人时；不能用一个未定义
的“复杂度分”把四类成本隐藏在综合分中。

## 4. 选项成本比较

| 选项 | 一次性成本 | 持续成本 | 迁移/退出成本 | 当前证据与判断 |
|---|---|---|---|---|
| 一个主 Harness + 必要薄层 | 固定候选版本；建立 C2–C6 安全/状态/Provider/replay adapter；补 C7 runbook | 薄层 schema、回归、备份和故障排障；主 Harness 升级跟随成本 | 薄层若保持 canonical ledger、cassette 和可旁路接口，替换面较小；仍需实测 | 当前最小成本假设；收益已有合同信号，真实工程/人工成本未知 |
| 第二个 Harness | 第二套候选 binding、Provider/tool/session/event/replay/安全 adapter | 双 loop、状态、权限、事件、Provider、升级和排障矩阵 | 双历史格式、双 runbook、双退出路径；可能需要长期兼容 | C1 有交叉收益，但 C2–C7 无非重复收益证据；成本面显著扩张 |
| LiteLLM 或同类 gateway | gateway 部署、Provider 转译、凭证和路由接入 | 常驻服务、限流/预算、日志、升级、许可证和故障定位 | Provider 路由与 gateway API 锁定；需验证无 gateway 旁路、导出和切换 | C5 仅证明 contract 可建模；真实适配节省和 gateway 成本均 unknown |
| Temporal/LangGraph 或独立 scheduler | 工作流模型、状态迁移、Activity/节点和部署初始化 | 常驻服务、数据库/历史、备份、升级、调度和人工接管 | workflow history/schema、任务状态和策略迁移；停服/导出需要演练 | C3/C4 证明 durable 合同有价值，但未证明常驻系统的 C7 净收益 |
| Langfuse/Phoenix/Inspect AI/OTel | SDK/collector、事件映射、数据集/评分/存储接入 | 存储、索引、查询、脱敏、保留、升级和隐私治理 | trace/dataset/schema 导出、历史读取、停用和删除；replay 仍需自有合同 | C6 证明最低 replay contract；外部后端查询/评测收益和成本 unknown |
| 从零自建 Agent loop | loop、工具、Provider、权限、状态、事件、replay、评测和测试全套建设 | 最大生态兼容、漏洞、模型/工具适配和维护负担 | 自有格式退出容易但数据/生态兼容责任最大 | 没有本轮非重复收益；一次性和持续成本上界最高，排除当前路线 |

## 5. 个人开发者/小团队成本门

成本门不是估算值，而是采用前置约束：

- 单一操作者首次安装 ≤ `90` 分钟；升级、备份恢复、故障定位各 ≤ `30` 分钟；
- 需要人工维护的常驻服务 ≤ `3` 个；Provider 和宿主 OS 排除，但必须在真实部署中
  显式列出；
- 不依赖额外专家完成日常安装、升级、恢复和排障；专家升级路径若存在，必须计入；
- 具备可复核的备份、恢复、回滚、数据导出/删除、凭证撤销和退出路径；
- 任何新组件必须带来 C2–C6 至少一个现有主路线无法提供的关键收益，否则不承担其
  service、storage、升级和迁移成本；
- 关键 hard gate 失败、成本超门或成本未知时暂停扩大组合，不能用 C1/C2–C6 的
  fixture 通过抵消。

## 6. 当前未知与 W7 采集计划

| 未知项 | 为什么当前不能填数 | W7 采集方法 | 放行条件 |
|---|---|---|---|
| 候选 adapter 工程人时 | 没有固定候选 C2–C7 adapter | 固定版本后记录首次接入、调试、回归和后续升级 diff/人时 | 与主 Harness/薄层替代方案对照，不能只报成功案例 |
| 真人安装/升级/恢复/排障时间 | 当前 0/12 stopwatch | 同一操作者按固定 runbook 逐项计时，记录等待、人工步骤、专家介入 | 满足 90/30/30/30 分钟门；缺失保持 unknown |
| Provider/Token/限额/成本 | 只有 fake Provider | 使用隔离测试账户或脱敏计费数据，记录每 case input/output tokens、fallback 和费用 | 不进入本地默认 fixture；结果需与 Provider/model identity 绑定 |
| 常驻服务与资源 | C7 参考只计 2 个服务 | 候选部署后列出 daemon、数据库、gateway、collector、scheduler、备份和监控 | ≤3 个需人工维护服务，排除项有理由和 owner |
| 升级/回滚维护 | 只验证了 reference 文件快照 | 至少一次上游/Provider/config 变化的备份、回归、回滚和独立 rerun | ledger/cassette/artifact 可读；失败即 pause |
| 迁移/退出 | 没有候选历史数据和替代系统 | 导出 event/state/cassette/artifact，停用组件，恢复最小替代路径并核对残留 | 可导出/删除/替换；不可迁移字段显式列出并批准 |
| 许可证/商业边界 | 研究有初步资料但未完成采用审计 | 固定 commit/版本，审阅许可证、附加条款、商业功能和再分发责任 | 与部署和退出责任一并签字 |

## 7. CBAM 成本判断

当前唯一可保留的成本姿态是：

1. “一个主 Harness + 必要薄层”具有最小责任复制面，但其真实 adapter 工程量和 C7
   人工维护成本仍未测；
2. 第二 Harness、LiteLLM、Temporal/LangGraph、外部观测/评测后端均保持候选，不能
   因理论功能或 fixture pass 直接引入；
3. C3/C4 的 durable/幂等/recovery、C5 的 Provider contract、C6 的 replay contract
   和 C7 的 service manifest 是后续比较成本的共同接口，不是免费能力；
4. 任何“省下的成本”必须对应可观察的替代工作量，例如少一个 adapter、少一个常驻
   服务、少一次人工排障或少一组迁移步骤，并保留测量来源；
5. 在 C7 真人时间、候选固定版本和迁移/退出演练完成前，不计算净收益/成本比，不做
   W7 采用排序。

## 8. 证据索引与下一节点

- [W6 CBAM 场景收益与风险降低量化](./w6-cbam-benefits-risk-reduction.md)
- [W6 CBAM 模板](./w6-cbam-template.md)
- [W6 ATAM/CBAM 阶段性决策包](./w6-atam-cbam-decision-package.md)
- [C7 单人运维与生命周期 ATAM](./w6-atam-c7-operations-lifecycle.md)
- [W6 评估矩阵](./w6-evaluation-matrix.md)
- [持续评估控制面证据](./w6-continuous-evaluation-findings.md)

下一节点 `1-3-3` 将评估第二 Harness 和组合件的增量价值；它必须复用本账的成本
分类，并逐项证明非重复收益，不能重新以功能列表作决策。

