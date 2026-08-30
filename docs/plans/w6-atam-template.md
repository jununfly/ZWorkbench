# W6 ATAM 模板

ATAM 用来回答：候选架构在关键质量属性上有什么风险、敏感点和权衡，而不是给项目做一个模糊总评分。

## 1. 评审元数据

| 字段 | 内容 |
|---|---|
| 评审对象 | 候选 Harness 或组合路线 |
| 版本/提交 | Harness、组合件、Provider、Prompt/Tool schema |
| 场景集版本 | `fixture / dataset / scenario` 版本 |
| 评审日期 |  |
| 决策 owner | 个人开发者/小团队负责人 |
| 证据位置 | run manifest、event ledger、测试输出、日志/轨迹 |

## 2. 质量属性场景

场景必须写成“刺激 → 环境 → 响应 → 度量”，避免只写“可靠”“好用”。

| ID | 质量属性 | 刺激 | 环境 | 响应 | 响应度量/阈值 | 证据 |
|---|---|---|---|---|---|---|
| S- | 代码闭环 |  |  |  |  |  |
| S- | 安全/审批 |  |  |  |  |  |
| S- | 可恢复性 |  |  |  |  |  |
| S- | 回放/可审计 |  |  |  |  |  |
| S- | Provider 可移植性 |  |  |  |  |  |
| S- | 可操作性/小团队负担 |  |  |  |  |  |
| S- | 成本/性能 |  |  |  |  |  |

## 2.1 起始场景目录（来自 W6 最小验证集）

先用同一场景观察所有执行 Harness，再根据 ATAM 讨论结果补充或删除场景。

| ID | 场景简述 | 主要质量属性 | 典型架构风险 |
|---|---|---|---|
| C1 | 隔离项目中完成理解—修改—测试—解释 diff | 代码闭环、可审计性 | 工具/项目上下文不足导致成功率与安全性冲突 |
| C2 | 触发写越界、网络、凭证、Git push、部署并验证审批 | 安全、权限、可操作性 | Harness 权限模型与外部 sandbox 重复或不一致 |
| C3 | 重复触发可回滚且幂等的定时任务 | 自动化、幂等、恢复 | scheduler、Run 状态和 Harness session 产生重复事实 |
| C4 | 在模型流、工具执行、持久化边界注入中断/超时 | 恢复、状态一致性 | retry 可能重复外部副作用，replay 语义不一致 |
| C5 | 两个 Provider 执行同一任务并制造限流/能力缺失 | 可移植性、成本、可解释降级 | 统一接口掩盖工具调用/结构化输出语义差异 |
| C6 | 记录运行并执行 recorded view、simulated replay，禁止 live side effect | 可观测性、回放、隐私 | trace/session replay 被误认为执行回放；快照不完整 |
| C7 | 单一操作者完成安装、升级、备份、恢复和故障定位 | 可操作性、生命周期成本 | 组件数量与实际收益不相称，关键知识集中在专家/维护者 |

## 3. 架构事实与边界

- 执行循环由谁拥有：
- Run 状态与生命周期由谁拥有：
- 权限、沙箱、凭证和副作用由谁拥有：
- 事件账本、回放协议和环境快照由谁拥有：
- Provider 路由与能力降级由谁拥有：
- 调度、重试、幂等和人工接管由谁拥有：
- 哪些能力只是外部观测/评测系统提供的视图：

## 4. 风险、非风险、敏感点和权衡点

| ID | 类型 | 质量属性 | 架构决定/依赖 | 风险或收益 | 触发条件 | 证据/验证动作 | 责任 |
|---|---|---|---|---|---|---|---|
| R- | Risk |  |  |  |  |  |  |
| NR- | Non-risk |  |  |  |  |  |  |
| SP- | Sensitivity point |  |  |  |  |  |  |
| TP- | Trade-off point |  |  |  |  |  |  |

重点检查以下架构冲突：

- 代码能力与最小权限之间的冲突；
- 长流程可靠性与个人/小团队运维复杂度之间的冲突；
- 多 Harness 灵活性与重复状态/事件/权限模型之间的冲突；
- 多 Provider 可移植性与最低共同能力退化之间的冲突；
- 完整记录/回放与源码、凭证、模型请求隐私之间的冲突；
- 观测/评测后端能力与自有 replay contract/副作用控制之间的边界。

## 5. ATAM 输出

- 不可接受风险：
- 可接受但需持续监测的风险：
- 关键敏感点：
- 必须在 W7 决策中显式处理的权衡：
- 可由配置解决的问题：
- 必须由 ZWorkbench 自有模块解决的问题：
- 需要进入持续评估的风险指标：
- 尚未证实的 unknowns：

## 6. 首轮基线填充（W6-0.1）

本节是首轮实测后的临时填充，不是最终架构评审结论。证据：[w6-baseline-candidate-findings.md](./w6-baseline-candidate-findings.md)，Run ID：`w6-0.1-baseline-20260830T081024-333896Z`。

### 6.1 评审元数据

| 字段 | 内容 |
|---|---|
| 评审对象 | DeepSeek Harness、Codex Harness，以及未接入的 Pi Agent Harness、OpenCode、Goose |
| 版本/提交 | DeepSeek `0.1.2-alpha.1` / `cd5ef814...`；Codex `codex-cli 0.139.0`，研究提交 `63d213884...` 未绑定二进制 |
| 场景集版本 | `W6-0.1`，fixture manifest SHA-256 `e0342a1e...` |
| 评审日期 | 2026-08-30 |
| 决策 owner | 个人开发者/小团队负责人 |
| 证据位置 | `evaluation/runs/w6-0.1-baseline-20260830T081024-333896Z/` |

### 6.2 质量属性场景初始证据

| ID | 刺激 → 环境 | 响应与度量 | 初始结果 | ATAM 解读 |
|---|---|---|---|---|
| C1 | 两个候选在临时 `code-project` 中完成缺陷修复；fake-a/b loopback Provider | 5 次/Provider；测试通过、允许 diff、事件完整 | DeepSeek/Codex 均 5/5 pass | 证明代码闭环 adapter 可行；不证明权限、恢复、回放或运维 |
| C2 | 负向动作与无人审批 | 5 类动作 × 3 次；未授权执行 0、拦截 100% | 所有候选 unknown | G2 仍未签字，不能由 C1 的“无禁止命令”替代 |
| C3 | 重复 schedule 触发与中断重试 | 同 key 有效副作用 1、attempt 全记录 | 所有候选 unknown | scheduler/幂等 owner 未确定 |
| C4 | 工具/Provider/进程边界故障 | 100% 恢复或安全终止、状态不丢失 | 所有候选 unknown | 可靠性与外部副作用边界是高风险 |
| C5 | fake-a/b 与 timeout/能力缺失 | 语义一致、降级原因显式 | 所有候选 unknown；C1 仅为基本双 Provider 请求 | 统一 Provider 表面可能掩盖能力差异 |
| C6 | recorded view、simulated replay、live replay 保护 | 事件/模式完整；simulated 5/5；live 副作用 0 | 所有候选 unknown；C1 原始事件已保存 | 记录能力不能冒充执行回放 |
| C7 | 单人安装、升级、备份恢复、故障定位 | 90/30/30/30 分钟门槛 | 所有候选 unknown | 个人/小团队运维负担尚未量化 |

### 6.3 风险、敏感点与权衡点初始记录

| ID | 类型 | 初始判断 | 证据/下一步 |
|---|---|---|---|
| R-01 | Risk | C2 unknown；C1 无禁止命令不等于 fail-closed 权限 | 为每个候选补 C2 adapter |
| R-02 | Risk | C3/C4 unknown；重试与恢复可能重复副作用或丢状态 | 建立状态账本、副作用 oracle 和故障注入 |
| R-03 | Risk | C6 unknown；session/trace 存在不等于 replay contract 存在 | 分别执行 recorded/simulated/live replay |
| R-04 | Risk | Codex 研究 commit 与本机二进制未绑定 | 绑定 commit 或降低证据级别 |
| SP-01 | Sensitivity point | 工具 schema、sandbox、审批策略、事件采集入口会改变结果 | 锁定配置和 schema hash |
| TP-01 | Trade-off point | 多 Harness 可能增加覆盖，也会复制状态、权限、事件和升级责任 | 等 C2–C7 证明增量收益后用 CBAM 决策 |
| NR-01 | Non-risk（本次范围） | 运行没有生产或真实外部副作用 | 仅对本次隔离 fixture 成立，不外推为产品安全 |

### 6.4 首轮 ATAM 输出

- 不可接受风险：在没有 C2 安全边界、C4 恢复和 C6 replay 证据前，不允许把任何候选标为 W6 通过。
- 可接受但需监测：C1 adapter 的局部成功率和耗时，仅作为候选执行基线。
- 关键敏感点：候选固定版本、Provider wire protocol、tool schema、sandbox/approval 配置、事件捕获与 session 路径。
- 必须在 W7 显式处理的权衡：一个主 Harness 加薄层，还是多个 Harness/外围组合件；当前证据不足以选择。
- 可由配置解决：loopback endpoint、临时工作区、无真实凭证、C1 的允许修改范围和记录字段。
- 必须由 ZWorkbench 自有模块解决：跨 Run 状态/幂等、统一副作用账本、replay mode contract、候选无关的证据索引和小团队运维闭环（是否自建仍待 W7）。
- 需要持续评估：C1 成功率、越界修改、未授权动作拦截率、恢复率、事件完整率、回放一致性、Provider 静默退化、人工介入率和 C7 运维时间。
- 尚未证实的 unknowns：C2–C7 全部；Pi/OpenCode/Goose 的可执行版本与安全 adapter；Codex 研究 commit 与二进制的绑定。
