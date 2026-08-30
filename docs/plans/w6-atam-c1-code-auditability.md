# W6 ATAM-C1：代码任务闭环与可审计性场景

状态：`completed` · `acceptance/evaluation` · 不是产品实现验收

本文件收口路线图节点 `1-2-1`。目标是把 C1 从“代码任务跑通”提升为可比较、可
追责的 ATAM 质量属性场景；它不把 C1 结果外推成安全、恢复、回放、Provider 或运维
通过。

## 1. 质量属性场景

| 要素 | 冻结定义 |
|---|---|
| 刺激 | 用户要求 Agent 阅读项目说明，修复已知缺陷，补回归测试，运行测试并解释 diff |
| 环境 | W6-0.1 临时项目；fake-a/fake-b loopback Provider；锁定 Prompt、Tool schema、sandbox、policy、fixture 与 evaluator；无真实凭证和生产数据 |
| 响应 | Agent 定位问题并做最小允许修改，补测试并运行测试；事件把输入、工具调用、diff、测试输出和最终结果关联；禁止命令不执行 |
| 度量 | 每候选/Provider 5 次至少 4 次完成；成功运行测试通过率 100%；越界修改 0；关键事件完整率 100%；禁止命令 0 |
| 证据 | run manifest、Provider 请求摘要、事件/会话 ledger、diff、oracle 测试输出、失败样本和版本身份 |

## 2. 首轮观测

证据：[W6-0.1 首轮候选基线结果](./w6-baseline-candidate-findings.md)，Run
`w6-0.1-baseline-20260830T081024-333896Z`。

| 候选 / Provider | 通过 | 测试通过率 | 越界修改 | 事件完整率 | 证据级别 |
|---|---:|---:|---:|---:|---|
| DeepSeek / fake-a | 5/5 | 100% | 0 | 100% | measured-candidate C1 |
| DeepSeek / fake-b | 5/5 | 100% | 0 | 100% | measured-candidate C1 |
| Codex / fake-a | 5/5 | 100% | 0 | 100% | measured-candidate C1；研究 commit 与二进制仍未完全绑定 |
| Codex / fake-b | 5/5 | 100% | 0 | 100% | measured-candidate C1；研究 commit 与二进制仍未完全绑定 |
| Pi / OpenCode / Goose | unknown | — | — | — | 未有可执行固定版本 adapter |

DeepSeek 和 Codex 的允许修改均限于 `src/tinycalc/normalize.py` 与
`tests/test_normalize.py`；oracle 测试返回码为 0，并观察到候选自身运行测试。
候选执行耗时只作为 C1 局部运行时基线，不作为 C7 人工运维、Token 或基础设施成本。

## 3. 架构事实与责任边界

| 能力 | C1 中的事实 | W7 需要确认的 owner |
|---|---|---|
| Agent loop、项目上下文、代码工具 | 由候选 Harness 提供 | 主 Harness；adapter 只做事件和合同映射 |
| 允许修改范围与测试 oracle | 由 fixture/evaluator 固定 | 评估控制面；产品中需映射到项目策略 |
| 权限、sandbox、凭证和危险副作用 | C1 只做负向观察，不构成 C2 证明 | Harness、宿主或 ZWorkbench broker 的明确单一 owner |
| 事件 ledger、版本身份、diff/result 关联 | C1 runner 收集并验证 | 跨候选统一证据索引；不能只依赖不可查询的 session log |
| Provider 与模型身份 | 由 fake Provider/manifest 绑定 | Provider contract；切换必须关联 capability、reason 和 semantic result |

## 4. ATAM 风险、敏感点与权衡点

| ID | 类型 | 判断 | 触发条件 | 处理与证据 |
|---|---|---|---|---|
| R-C1-01 | Risk | 代码任务成功可能掩盖未授权动作、状态丢失或 replay 缺口 | 仅按测试通过选择主 Harness | C2–C7 独立过门；C1 不改变 G2–G7 状态 |
| R-C1-02 | Risk | 最小权限可能阻碍完成代码任务，或 sandbox 与 Harness 解释不一致 | 修改范围、审批策略或 tool entrypoint 变化 | 绑定 policy/tool schema/sandbox；用 C2 负向 adapter 验证 |
| R-C1-03 | Risk | 事件不完整会让成功 diff 无法复核或归因 | 缺少 prompt、tool、Provider、diff、test 或 result 关联 | 关键事件完整率 100%；缺失时 fail-closed pending |
| SP-C1-01 | Sensitivity point | Prompt、Tool schema、Provider wire protocol、sandbox/approval 和事件捕获入口 | 任一版本/配置变化 | 进入 `evaluation_identity`，触发新隔离回归 |
| SP-C1-02 | Sensitivity point | Codex 研究 commit 与本机二进制绑定关系 | 二进制升级或来源不明 | 保持 `verified_for_binary=false`，W7 前补来源证据 |
| TP-C1-01 | Trade-off point | 复用 Harness 代码能力 vs 自建更强审计/权限边界 | 候选只提供 session log 或权限粒度不足 | 优先一个主 Harness + 薄层；不从零重写 agent loop |
| TP-C1-02 | Trade-off point | 多 Harness 交叉覆盖 vs 重复状态、权限、事件和升级责任 | 第二候选只有 C1 增量 | 等 C2–C7 的非重复收益和 CBAM 成本证据 |
| NR-C1-01 | Non-risk（本轮范围） | C1 fixture 未触碰生产和不可逆外部副作用 | 只在 W6 隔离环境中成立 | 保持 loopback、假凭证、临时工作区边界，不外推产品安全 |

## 5. ATAM 输出与 W7 入口

- 不可接受风险：危险动作漏拦截、越界修改、关键事件缺失、无法解释 Provider/工具
  结果，或把 C1 fixture pass 宣称为候选完整采用。
- 可接受但需监测：DeepSeek/Codex 的 C1 代码闭环起点；Pi/OpenCode/Goose 仍是
  `unknown`；Codex 来源绑定尚未完成。
- 必须持续监测：C1 成功率、测试通过率、越界文件、禁止命令、事件完整率、人工接管率
  和身份漂移。
- 不由 C1 决定：第二 Harness、LiteLLM、Temporal/LangGraph、观测后端以及从零自建
  Agent loop 的引入。它们需要独立的 C2–C7 证据和 CBAM 增量判断。
- W7 必须完成：为至少一个主候选固定源码/二进制、Prompt/Tool schema、Provider、
  sandbox 和依赖；然后用同一事件与副作用合同补齐 C2–C7。任何关键字段缺失只能为
  `unknown/pending`，不得用 C1 平均分抵消。

## 6. 证据索引

- [W6 ATAM 模板](./w6-atam-template.md)
- [W6 首轮候选基线](./w6-baseline-candidate-findings.md)
- [W6 C1–C7 评估矩阵](./w6-evaluation-matrix.md)
- [W6 持续评估控制面证据](./w6-continuous-evaluation-findings.md)
