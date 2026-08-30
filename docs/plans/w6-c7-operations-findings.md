# W6-0.1 C7 个人开发者/小团队运维与生命周期成本证据

状态：`pass-with-unknown-human-timing` · `acceptance/evaluation` · 不是候选 Harness 通过结论，也不是 ZWorkbench 产品实现

## 1. 首轮范围与结论

证据运行：`w6-0.1-c7-20260830T122018-367856Z`。Runner 在每个案例创建全新的
case-local workspace，执行候选无关的生命周期 fixture；不安装依赖、不启动常驻
daemon、不访问 Provider/网络、不读取真实凭证或生产数据。

首轮结果分成两个维度：

| 维度 | 结果 | 含义 |
|---|---:|---|
| 机器流程与证据完整性 | `12/12 pass` | 4 类运维流程各重复 3 次，操作结果、事件、隔离边界、服务/依赖清单均通过 |
| 人工时间门 | `unknown`（`0/12` 有真人计时） | 没有操作者秒表数据，不能把 subprocess 墙钟时间当作安装/升级/恢复/排障人工时间 |
| 参考 MVP 维护服务 | `2` | `scheduler`、`evidence-ledger`；Provider 与宿主 OS 按约束排除 |
| 额外专家 | `false` | 仅说明参考 fixture runbook 没有专家专属步骤，不代表候选已证明无需专家 |

因此本轮只证明 C7 评估资产和参考操作合同可执行；G0/G7 仍保持
`unknown`，候选的 C7 状态也全部保持 `unknown`。

## 2. 固定阈值与测量边界

| 场景 | 硬阈值（分钟） | 本轮人工观测 | 机器墙钟时间（仅记录） |
|---|---:|---|---|
| 首次安装 | ≤90 | `unknown` | 3/3；均值 `0.001240s` |
| 常规升级 | ≤30 | `unknown` | 3/3；均值 `0.001526s` |
| 备份恢复 | ≤30 | `unknown` | 3/3；均值 `0.002209s` |
| 预制故障定位 | ≤30 | `unknown` | 3/3；均值 `0.001623s` |

机器时间由 runner/fixture 的 monotonic subprocess 墙钟测量，包含 case-local
fixture 执行开销；它是评估机执行下界，不是人类阅读文档、准备环境、确认结果、
处理凭证或排障的估计。首轮生成的
[`human-timing-template.json`](../../evaluation/runs/w6-0.1-c7-20260830T122018-367856Z/human-timing-template.json)
只含 `unknown`，后续必须由真实单一操作者填入各场景秒表分钟数，再用
`run_c7.py --human-timings-json` 重跑。

## 3. 场景证据

| 场景 | 操作合同 | 关键 oracle | 结果 |
|---|---|---|---|
| install | 干净 workspace 建立最小 app/config/state 布局 | 版本、配置、状态文件存在 | 3/3 pass |
| upgrade | 从 `0.1` 生成升级前 snapshot，再切换到 `0.2` | snapshot 保留旧版本，当前版本为目标版本 | 3/3 pass |
| backup_restore | 备份健康状态，注入损坏，再恢复并校验摘要 | 备份存在、摘要一致、状态恢复为 healthy | 3/3 pass |
| fault_diagnosis | 生成 provider timeout 预制故障和 degraded health | fault_id/run_id 关联，诊断分类和下一步存在 | 3/3 pass |

每个案例都保存：

- `operation/operation-events.jsonl`：开始、环境、前置条件、操作步骤、验证和完成事件；
- `operation/operation-result.json`：机器时间、人工计时状态、步骤清单、结果 oracle；
- `operation/service-manifest.json`：计入与排除的服务；
- `operation/dependency-manifest.json`：运行时依赖和专家要求；
- `process-result.json`：runner 进程返回码与命令；
- `human-timing-template.json`：人工计时待补模板。

## 4. ATAM 更新

| ID | 更新后的判断 | 证据/响应 |
|---|---|---|
| R-05 | C7 参考流程机器执行通过，不等于候选个人/小团队可运维；人工时间缺失时不能签 G0 | 维持 unknown；候选必须绑定版本、runbook、真实操作者计时、升级/回滚和退出路径 |
| R-07 | `维护服务 ≤3` 若不声明计数边界，Provider、宿主 OS 和临时 fake service 可能被错误计入 | 固定 `service-manifest` 的 counted/excluded 字段；参考构成为 2 个 counted services |
| SP-04 | 工具/脚本执行时长与人工操作时长是不同测量面 | 每个结果同时保存 `machine_elapsed_seconds`、`human_steps`、`human_timed` 和 `human_elapsed_minutes`；缺失人工值保持 unknown |
| TP-03 | 原生 scheduler/网关/编排器的能力收益可能被常驻维护和升级矩阵抵消 | 在候选 C7 人工计时和服务清单完成前，不引入第二 Harness、Temporal/LangGraph 或 LiteLLM |

不可接受的误读：不得将本轮 `0.001–0.003s` 机器时间写成“安装耗时”，不得将
参考服务清单写成任何候选的原生服务清单，也不得将 fixture 通过改写成 G0/G7
通过。

## 5. CBAM 更新

| 选项 | 本轮新增收益 | 本轮新增成本/未知 | 当前姿态 |
|---|---|---|---|
| 一个主 Harness + 必要薄层 | C7 需要的安装/升级/恢复/排障证据格式和服务计数边界已可自动生成 | 候选真实安装与人工工时仍未知；薄层的备份、升级和退出责任仍需测 | 继续保留为最小路线假设 |
| 外部 scheduler/Temporal/LangGraph | C7 fixture 显示 scheduler 与 evidence ledger 可以作为独立运维对象记录 | 常驻服务、备份、升级和排障成本没有真人数据，不能只按功能引入 | 有条件保留 |
| LiteLLM/外部观测后端 | 可纳入同一服务/依赖/升级/排障清单比较 | 网关/存储/隐私/许可证/退出成本尚未测 | 等 C5/C6 候选 adapter 与 C7 真人演练 |
| 第二 Harness | 无新增 C7 候选收益证据 | 将复制安装、升级、备份、凭证、事件和排障责任 | 暂不引入产品拼盘 |

## 6. 证据边界与下一步

- 本轮是 `fixture-contract`，不是 `measured-candidate`；五个候选的 C7 状态均为 `unknown`。
- C7 机器流程已形成 12 个可复核样本，但人工时间门仍未满足签字条件。
- G0 需要至少一个候选在固定版本上完成真实单人安装、常规升级、备份恢复和故障定位；G7 还需要许可证、维护责任、回滚/退出和兼容性证据。
- 下一步应先选择一个主候选，绑定其固定源码/二进制、Provider、配置和 runbook，执行 C2–C7 组合 adapter；同时补一次真实操作者 stopwatch 记录。

## 7. 固定证据索引

- Runner：[`evaluation/runner/run_c7.py`](../../evaluation/runner/run_c7.py)
- Fixture：[`evaluation/fixtures/w6-0.1/c7-operations.py`](../../evaluation/fixtures/w6-0.1/c7-operations.py)
- Summary：[`summary.json`](../../evaluation/runs/w6-0.1-c7-20260830T122018-367856Z/summary.json)
- Fixture manifest：[`fixture-manifest.json`](../../evaluation/fixtures/w6-0.1/manifests/fixture-manifest.json)
- 矩阵：[W6 评估矩阵](./w6-evaluation-matrix.md)
- ATAM：[W6 ATAM 模板](./w6-atam-template.md)
- CBAM：[W6 CBAM 模板](./w6-cbam-template.md)
