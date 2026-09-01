# W8 DeepSeek 独立挑战者评估

状态：已完成 acceptance/evaluation · 最终姿态：`unknown-stop / no-change`

本报告只评估固定版本的 DeepSeek Harness 是否足以挑战当前 Codex 唯一主 Harness。它不修改 ZWorkbench 生产代码、不新增生产 Harness、不接入真实 Provider/API Key，也不把通用 composition fixture 的结果冒充为 DeepSeek 原生能力。

## 1. 固定对象与边界

| 项目 | 冻结值 |
| --- | --- |
| 候选 | DeepSeek Harness |
| 仓库 | `https://github.com/deepseek-ai/deepseek-harness` |
| commit | `cd5ef8148158c3a752a658978873241fdf8e2bbc` |
| 版本 | `0.1.2-alpha.1` |
| 运行入口 | `apps/cli/lib/bin.js`，profile `headless` / `acp` |
| 共同 fixture | [`evaluation/fixtures/w6-0.1`](../../evaluation/fixtures/w6-0.1) |
| Provider | loopback fake-a / fake-b；无真实凭证、外网、生产数据或外部副作用 |
| 路线角色 | acceptance/evaluation；W8 产品主线仍为 Codex 0.139.0 + SQLite composition owner |

候选源码在隔离 checkout 中完成 `pnpm install --frozen-lockfile` 与 `pnpm run build:lib`。C1–C6 的原始 ACP/session 过程保留在临时目录；仓库只提交精简 summary，避免把大型 `evaluation/runs` 历史目录纳入版本库。

本次 parity rerun 修正了两处评估基础设施问题：ACP runner 改用 fd 级字节 framing，避免 `select()` 与文本缓冲联用造成已完成 turn 的假超时；C4 fake Provider 补齐 `tool_timeout` mode，并让显式 `RETRY_TOOL` 优先生成 tool call。此前的 smoke 目录只作为诊断记录，正式结论以 `w8-deepseek-parity-*` 目录为准。

## 2. C1–C7 结果

| 场景 | 候选实测结果 | 候选判定 | 关键边界 |
| --- | --- | --- | --- |
| C1 代码闭环 | fake-a/fake-b 各 5/5；共 10/10 | `pass` | 真实 DeepSeek CLI agent loop 能读、改代码、加测试、运行测试，并保留 session 事件；只证明代码闭环 |
| C2 fail-closed 安全 | fail-closed adapter 6/6；关键拦截率 100%，未授权执行/secret 泄露/越界修改均为 0 | `pass-with-adapter` | 证明候选在当前安全 adapter seam 上满足 fixture；不等于宿主 sandbox/native approval 已签核 |
| C3 自动任务、定时、幂等 | 5 场景 × 3 次，共 15/15；同 key 有效副作用 1、重复额外副作用 0 | `pass-with-composition / native unknown` | DeepSeek ACP 可以作为执行 seam；schedule、attempt、effect、result、reconciliation 由外部 composition owner 持有，候选 scheduler/cron/trigger 未测量 |
| C4 中断、恢复、副作用重试 | 4 故障 × 3 工具类 × 3 次，共 36；非 approval-required 24/24 通过，approval-required 12/12 unknown，无 fail | `partial / unknown-stop` | ACP `session/resume`、cancel、process-kill 恢复和外部 effect ledger 可验证；未观察到候选原生 permission request，turn identity 也未暴露 |
| C5 双 Provider 故障切换 | fake-a/fake-b 正常独立路由 10/10；timeout fake-a 时只发生同路由 retry，fake-b 0 次请求 | `unknown` | 能切换配置 endpoint 不等于自动 failover；没有候选-owned fallback/degradation reason contract |
| C6 可观测与回放 | 记录视图和 session log 5/5；resume 不自动发送历史 update；evaluator-only 双解码确定 | `unknown` | 固定版本明确不提供 transcript replay；日志恢复不是 replay，live replay 与副作用 replay 未建立 |
| C7 运维、许可证、退出 | 根 MIT、NOTICE 自检通过、250 个 DSH package 均声明 MIT | `unknown-stop` | 缺真人安装/升级/备份恢复/故障定位 stopwatch、候选真实 backup/restore、远端退出责任和 source-to-binary provenance |

证据入口：

- [C1 parity summary](../../evaluation/evidence/w8-deepseek-parity-c1-both-20260901/summary.json)
- [C2 summary](../../evaluation/evidence/w8-deepseek-c2-20260901/summary.json)
- [C3 parity summary](../../evaluation/evidence/w8-deepseek-parity-c3-20260901/summary.json)
- [C4 parity summary](../../evaluation/evidence/w8-deepseek-parity-c4-20260901/summary.json)
- [C5 Provider parity summary](../../evaluation/evidence/w8-deepseek-parity-c5-20260901/summary.json)
- [C6 replay parity summary](../../evaluation/evidence/w8-deepseek-parity-c6-20260901/summary.json)
- [C7 audit summary](../../evaluation/evidence/w8-deepseek-c7-20260901/summary.json)

对应 runner：

- [`run_deepseek_challenger.py`](../../evaluation/runner/run_deepseek_challenger.py)
- [`run_deepseek_c3_c4.py`](../../evaluation/runner/run_deepseek_c3_c4.py)
- [`run_deepseek_c5_provider.py`](../../evaluation/runner/run_deepseek_c5_provider.py)
- [`run_deepseek_c6_replay.py`](../../evaluation/runner/run_deepseek_c6_replay.py)

## 3. 重要发现

### 3.1 ACP 是有价值的候选 seam，但不是完整工作台合同

DeepSeek ACP 提供标准化的 `session/new`、`session/list`、`session/resume`、`session/close` 与 `session/cancel`，并将 session 事件持久化。真实跨进程 probe 证明这些能力在固定 checkout 上可运行。

但该 ACP surface 明确不提供 transcript replay、session deletion、fork、additional directories、terminal 或 interactive UI 扩展；`session/resume` 恢复日志而不重放历史 update。因此它可以作为未来 adapter 的 session transport，不能单独承担 ZWorkbench 的可回放和副作用协调合同。

### 3.2 retry 与 failover 必须分开

DeepSeek 的 `dsh-llm-retry` 能在同一个 provider route 上按策略重试失败的 model request，并记录 `llm/retry`。C5 故障 probe 观察到的正是同一路由 retry；独立 fake-b 没有被联系。没有第二 Provider 选择、切换原因和降级结果账本，就不能称为双 Provider failover。

### 3.3 “MIT”不等于完整商业退出证明

源码审计得到的事实是：根 LICENSE 为 MIT，`THIRD_PARTY_NOTICES.md` 已提交并通过生成校验，250 个 DSH package 的 manifest 均声明 MIT；依赖和 vendored/native 组件仍保留各自条款。

这解决了许可证材料的第一层问题，但没有解决发布二进制的 provenance：`apps/cli/lib/bin.js` 是本地构建产物，不是 git 跟踪的 source artifact，也没有签名 release binary、构建声明或可验证 source-to-binary 证明。个人试点不得把本地 build 当成可审计发布物。

## 4. ATAM 结果

| 敏感点 | 观察 | 结论 |
| --- | --- | --- |
| SP-01 代码闭环 | C1 10/10，候选 loop 能完成最小开发任务 | 局部支持；Codex 主线没有被推翻 |
| SP-02 权限与安全 | C2 在显式 adapter 上 6/6，关键拦截 100% | 可复用安全 seam；仍需宿主级边界负责授权 |
| SP-03 自动化触发 | headless 无 scheduler/trigger contract | 继续由 composition owner 持有，DeepSeek 原生能力 unknown |
| SP-04 恢复与副作用 | ACP 能恢复 session；没有候选 effect ledger 和幂等副作用协议 | 不足以签核 C4；不得让模型自行重放外部写入 |
| SP-05 Provider 可移植性 | endpoint 可分别配置；timeout 不会自动切换第二 Provider | C5 unknown；需要独立 router/fallback adapter |
| SP-06 记录与回放 | session log 可读，resume 不 replay 历史 update | 只能作为 recorded state，不满足 live/simulated replay 合同 |
| SP-07 小团队可操作性 | 静态材料完整；真人生命周期和退出流程缺失 | C7 hard gate 未过 |

ATAM 决策：DeepSeek 当前最大的新增价值是标准 ACP session transport，而不是一个已经覆盖自动化、恢复、failover、replay、运维和退出的完整替代 Harness。该价值不足以抵消引入第二状态语义、权限映射、Provider 映射和升级矩阵的敏感点。

## 5. CBAM 增量账本

| 方案 | 可测收益 | 新增成本 | 当前姿态 |
| --- | --- | --- | --- |
| Codex 唯一主 Harness + composition owner | 已有 C2/C4/C5/C6/C7 主线证据和真实 owner | 继续维护一个 owner 与少量 adapter | 保持 |
| 引入 DeepSeek 为第二主 Harness | C1 代码闭环、ACP session transport、可配置 DeepSeek endpoint | 第二套 loop/session/tool/event 语义；C3/C4/C5/C6/C7 仍需补齐；权限、迁移、升级、退出双倍审计 | 不引入 |
| DeepSeek 只作为受控候选/可选 adapter | 可在需要时复用 ACP transport；不改变产品主线 | 仍需明确 adapter contract、固定版本和证据目录 | 保留未来选项 |
| 自建完整 DeepSeek 编排拼盘 | 理论上可补齐 scheduler/router/replay | 对个人开发者或小团队意味着长期维护 loop、state、policy、effects、replay、ops | 不作为当前路线 |

CBAM 判断：目前没有被 Codex + composition owner 覆盖之外的、已测量且非重复的收益。局部 ACP 价值不足以支付第二 Harness 的长期维护和退出成本，因此最终为 `no-change`。

## 6. 最终决策与重开条件

最终决策：

1. Codex 继续作为唯一主 Harness；本轮不新增 DeepSeek 生产集成。
2. DeepSeek 保留为独立挑战者记录，不把 `pass-with-adapter` 或 `partial` 当作主线能力。
3. C3、C4、C5、C6、C7 的 unknown/unknown-stop 不通过综合平均分掩盖。
4. 如果未来要重新挑战主 Harness，必须先补齐候选专属 scheduler/trigger、effect ledger + 幂等 retry、双 Provider fallback/degradation ledger、明确 replay modes、真人运维 stopwatch、真实 composition backup/restore、远端退出责任和 source-to-binary provenance，并在同一固定版本上重跑 C1–C7。

本报告结论是评估边界，不是 DeepSeek Harness 的一般产品质量评价，也不是许可证法律意见。
