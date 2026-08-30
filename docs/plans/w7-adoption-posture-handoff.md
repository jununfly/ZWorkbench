# W7 采用姿态交接包

状态：`conditional-handoff` · W6 最终采用 `not-signed-off` · `acceptance/evaluation`

本文件是 W6 到 W7 的决策交接，不是 ZWorkbench 实现设计，也不是任何候选已通过的声明。

## 1. W6 signoff disposition

W6 不签署“直接进入产品实现”的最终采用决定。原因不是 fixture 失败，而是关键
证据仍停留在候选无关合同或 `unknown`：

| 证据层 | 当前结果 | 能够支持的结论 | 不能支持的结论 |
|---|---|---|---|
| C1 候选代码闭环 | DeepSeek/Codex 在 fake-a/b 各 5/5 pass | 两个候选已有代码任务 adapter 起点 | 不证明安全、恢复、回放、运维或产品可发布 |
| C2–C6 fixture contract | C2/C4/C5/C6 通过；C3 为 `pass-with-composition` | 已固定安全、状态、Provider、回放和幂等合同形状 | 不改写候选原生能力状态 |
| C7 fixture contract | `12/12 machine process pass`；维护服务 2/3 | 运维证据格式和服务计数边界可复核 | `0/12` 真人工时，不能签 G0/G7 |
| 候选 C2–C7 | 五个候选仍为 `unknown` | 已知需要哪些候选 adapter | 不能做综合分、主基座选定或组件采用 |

因此 W6 的实际结论是：`evidence-contract ready`，不是 `candidate adoption ready`。

## 2. 交接的采用姿态

W7 采用以下待验证路线：

> 一个主 Harness + 必要薄层；薄层只拥有被证据证明必须跨运行统一的治理合同。

优先候选范围暂收敛为 DeepSeek Harness 与 Codex Harness，因为二者已有 C1
固定入口证据；这只是 W7 adapter 优先级，不是最终主 Harness 选择。Pi Agent
Harness、OpenCode、Goose 继续保留在研究矩阵，直到具备可执行固定版本和安全入口。

薄层的候选自有边界：

- fail-closed 权限、审批和副作用分类；
- 跨 Run durable state、幂等 key、attempt/effect/result ledger；
- Provider capability、fallback/degradation 和语义结果合同；
- recorded/simulated/live replay mode contract 与环境/artifact 关联；
- 跨候选评估证据索引、回归门禁和未知项账本。

执行 Harness 可继续拥有 agent loop、项目上下文、代码工具和原生 session，但
只有在 adapter 能把其事件、权限、状态和副作用映射到上述合同后，才能进入候选
门槛判断。

## 3. 暂不采用的路线

| 路线 | W7 姿态 | 只有何时重新打开 |
|---|---|---|
| 两个或多个 Harness 产品拼盘 | 暂不采用 | 某一 C2–C6 关键场景有非重复收益，且状态/权限/事件 owner 和 C7 成本可证明 |
| 主 Harness + LiteLLM | 暂不采用 | 候选 C5 证明网关减少总适配/排障成本，并保留可解释 fallback ledger |
| 主 Harness + Temporal/LangGraph | 暂不采用 | 候选 C3/C4 原生能力不足，且 durable/schedule/retry 收益覆盖常驻运维成本 |
| 主 Harness + Langfuse/Phoenix/Inspect AI/OTel | 暂不采用 | C6 证明查询/dataset/eval 带来净收益，脱敏、存储、退出边界明确 |
| 从零自建 Agent loop | 暂不采用 | 所有可复用执行候选都无法通过关键硬门槛，且有明确深模块 ownership 与成本预算 |

## 4. W7 必须完成的验证顺序

1. 固定一个优先候选的源码提交/二进制版本、配置、Prompt/Tool schema、Provider/model/endpoint、sandbox 和依赖快照。
2. 建立该候选的 C2 fail-closed adapter，确认真实工具入口的审批、网络、凭证、文件、push/deploy 边界；不得用候选无关 fixture 代替。
3. 建立并执行候选 C3/C4 adapter，确认跨 Run scheduler、幂等、checkpoint、resume、retry、reconcile 和 safe-stop。
4. 建立候选 C5/C6 adapter，确认双 Provider 能力协商、显式降级、事件账本、环境快照、cassette 和 live replay 默认拒绝。
5. 由一名真实操作者完成候选 C7 安装、升级、备份恢复、预制故障定位和回滚；使用 stopwatch 填充安装 ≤90 分钟、其余各 ≤30 分钟门，并记录专家介入与服务清单。
6. 完成许可证、商业版边界、维护者集中度、升级/回滚、备份兼容、数据导出和退出演练。
7. 仅在以上证据齐全后，以 ATAM 风险和 CBAM 增量成本评估“一个主 Harness + 薄层”、有条件组合、替换/分叉或停止。

## 5. W7 signoff 门槛

W7 只能在以下条件全部具备后给出最终采用姿态：

- 至少一个候选在固定版本上完成 C1–C7，所有关键事件、权限决定、状态、Provider、回放和副作用证据可关联；
- G0/G7 不再是 unknown：真人运维工时、服务数、专家介入、许可证、升级/回滚、备份兼容和退出责任均有证据；
- G2/G3/G5/G6 的候选 adapter 不出现未授权副作用、状态丢失、无界 retry、静默 Provider 切换或 simulated/live 边界混淆；
- 所有引入的组合件都有 CBAM 的一次性、持续、迁移、锁定与退出成本，并证明非重复关键收益；
- 自动化回归门禁可在候选、配置、Provider、fixture 或 schema 变化时重跑，并对失败/unknown fail-closed。

任一关键门槛失败或 unknown 时，W7 只能输出 `pending`、`replace` 或 `stop`，不能输出
“推荐采用”或进入产品实现。

## 6. 证据索引

- [W6 ATAM/CBAM 阶段性决策包](./w6-atam-cbam-decision-package.md)
- [W6 C7 运维证据](./w6-c7-operations-findings.md)
- [W6 评估矩阵](./w6-evaluation-matrix.md)
- [W6 自动化与持续评估协议](./w6-continuous-evaluation.md)
- [W6–W7 路线图](./personal-workbench-roadmap.md)
