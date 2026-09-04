# ZWorkbench 文档地图

状态：`knowledge-baseline / target-state-approved-for-implementation-planning`<br>
日期：2026-09-03

这是方案准备阶段的统一入口。它回答“现在应相信哪份材料、哪些结论只是历史评测、开发从哪里开始”，不替代代码、测试或 roadmap JSON。

## 先读这四份

1. [开发前基线](plans/development-baseline.md)：当前目标、已完成准备、未关闭门和正式开发的进入顺序。
2. [目标系统架构](plans/designs/dsh-codex-hybrid-target-architecture.md)：目标态的分层、ownership、Worker contract、扩展面和 H1–H9 验收矩阵。
3. [DSH 源码/运行时布局设计](plans/designs/dsh-source-runtime-layout-and-maintenance.md)：ZWorkbench 与 ZDSHarness 的目录、artifact、cache、升级和维护边界。
4. [README](../README.md)：当前仓库实际可运行的 Codex-only `local_read_only_run`，不是目标混合架构已经完成的证明。

## 当前唯一决策答案

目标架构是：

```text
DSH 主 Harness
  └─ Codex Coding Worker（首期进程外 bridge）
       └─ ZWorkbench CompositionOwner（唯一 durable owner）
```

这意味着：

- DSH 持有顶层 Agent loop、插件组合、上下文、任务路由和个性化实验；
- Codex 只负责代码理解、修改、测试、构建和可审查 diff；
- ZWorkbench 持有 run、attempt、event、effect、result、approval、Provider 尝试、回放、备份、恢复和退出记录；
- DSH、插件、Codex session、Provider 日志和观测投影都不是第二个事实源；
- 当前代码中的 Codex-only 路径保留为回退基线；H1–H5 已有受控的 owner-backed bridge seam；
  H5 仅为组合式 evidence/replay 证据，不代表 DSH 原生或真实 Provider replay 已通过。

目标架构已获准进入实现规划；真实写入、真实 Provider 默认接入、Git push、部署、Webhook、全量插件市场和生产发布仍未获准。

## 文档分层与使用方式

| 目录/文件 | 作用 | 状态解释 |
|---|---|---|
| [`AGENTS.md`](../AGENTS.md) | Agent 执行规则、导航和长期硬约束 | 每次任务先读 |
| [`ZJ-CONTEXT.md`](../ZJ-CONTEXT.md) | 领域词汇、unknown、replay 和 Provider 责任边界 | 稳定语义 |
| [`plans/designs/`](plans/designs/) | 目标态和技术设计 | 当前目标以目标架构文档为准 |
| [`plans/development-baseline.md`](plans/development-baseline.md) | 准备阶段收口和开发入口 | 当前准备阶段权威摘要 |
| [`plans/personal-workbench-w8-roadmap.json`](plans/personal-workbench-w8-roadmap.json) | 节点、状态和决策历史事实源 | 只用 roadmap CLI 读写 |
| [`plans/personal-workbench-w8-roadmap.md`](plans/personal-workbench-w8-roadmap.md) | roadmap 的生成视图 | 不手工编辑路线图区块 |
| [`plans/w6-*`](plans/) | ATAM、CBAM、持续评估、C1–C7 合同和首轮基线 | acceptance/evaluation，不等于产品已实现 |
| [`plans/w7-*`](plans/) | Codex 候选的固定版本、组合式证据和 C7 审计 | 历史评测/回退基线；未知项仍有效 |
| [`plans/w8-*`](plans/) | 受控试点、`local_read_only_run`、DeepSeek 挑战者和目标边界 | 按文档头部状态区分 product execution 与 acceptance/evaluation |
| [`plans/w8-h1-bootstrap-findings.md`](plans/w8-h1-bootstrap-findings.md) | H1 runtime seam 的 fixture 证据与正式 artifact 资格边界 | fixture 与 clean maintainer-pinned artifact 已验证；可进入 H2 |
| [`plans/w8-h2-worker-handshake-findings.md`](plans/w8-h2-worker-handshake-findings.md) | H2 Worker handshake 的 owner correlation、严格 wire 和 safe-stop 证据 | owner-backed + fixture-composed 已验证；真实 Provider/H4-H5 仍未声称 |
| [`plans/w8-h3-worker-coding-findings.md`](plans/w8-h3-worker-coding-findings.md) | H3 只读 coding、真实 Codex runtime + loopback Provider 和 artifact receipt 证据 | fixture 与 real-Codex-runtime + loopback 已验证；真实远程 Provider/H4-H5 仍 HOLD |
| [`plans/w8-h4-worker-lifecycle-findings.md`](plans/w8-h4-worker-lifecycle-findings.md) | H4 Worker cancel、timeout、crash、parent stop、process-tree cleanup 和 recovery | 6/6 owner-backed + fixture-composed 场景通过；H5、host sandbox 和真实 Provider 仍 HOLD |
| [`plans/w8-h5-evidence-replay-findings.md`](plans/w8-h5-evidence-replay-findings.md) | H5 owner-backed recorded view、sealed cassette simulated replay、live replay deny 和 provenance gate | 7/7 场景通过；仅为 owner-backed + fixture-composed，真实 Codex/Provider replay 仍 HOLD |
| [`plans/w8-real-provider-compatibility-findings.md`](plans/w8-real-provider-compatibility-findings.md) | 真实远程 Provider 的分层兼容性、人工授权门和脱敏 staging 合同 | HTTP 与授权 Codex read-only staging 已 pass；loopback composition 已 pass；真实 Ark fallback 与退出仍按需/HOLD |
| [`references/optional-real-codex-provider-staging.md`](references/optional-real-codex-provider-staging.md) | 真实 Codex 0.139.0 + Ark 的 case-local 一次性只读 turn 入口与证据边界 | 最新授权 staging 已 pass；完整 Provider 兼容性仍 HOLD |
| [`plans/research/`](plans/research/) | 一手来源、固定 commit、collection status 和研究 ledger | 研究支撑；raw ledger 是生成证据 |
| [`references/`](references/) | 真实 Provider 和远端退出的按需人工材料 | 路线外，不阻塞本地开发 |
| [`../evaluation/fixtures/`](../evaluation/fixtures/) | 可重复的隔离输入和假服务 | 可复用测试资产 |
| [`../evaluation/evidence/`](../evaluation/evidence/) / [`../evaluation/runs/`](../evaluation/runs/) | 机器生成的运行证据和历史现场 | 默认本地保留，不批量提交或删除 |

## 现役答案与历史快照

当前目标架构、开发入口和硬约束只以 [目标系统架构](plans/designs/dsh-codex-hybrid-target-architecture.md)、
[开发前基线](plans/development-baseline.md)、本文件和根目录 [AGENTS.md](../AGENTS.md) 为准。
`w6-*`、`w7-*`、早期 `w8-*` 的评测/决策文档保留当时的证据、阈值和回退基线；
如果其中仍出现“Codex 唯一主 Harness”，应按文档头部的历史状态理解，不覆盖
2026-09-03 已批准的 DSH 主 Harness + Codex Coding Worker 目标态。路线图的事实状态
仍只读写 [`personal-workbench-w8-roadmap.json`](plans/personal-workbench-w8-roadmap.json)，
其 Markdown 是 CLI 生成视图。

## 研究准备阶段结论

| 阶段 | 已沉淀的结论 | 读取入口 |
|---|---|---|
| W2 | 核实 DeepSeek Harness、Pi 和 Codex 的对象身份与能力形状 | [W2 named harnesses](plans/research/w2-named-harnesses.md) |
| W3 | 区分执行型 Harness、代码专长执行器、编排、调度、Provider、观测和评测层 | [W3 alternatives](plans/research/w3-open-source-alternatives.md) |
| W4 | 观测/评测后端可以复用，但执行回放、副作用隔离、环境快照和 artifact lock 仍属 ZWorkbench | [W4 observability/replay](plans/research/w4-observability-replay-evaluation.md) |
| W6 | 用 ATAM 识别敏感点和权衡，用 CBAM 记收益/成本，并以自动化持续评估形成硬门 | [W6 matrix](plans/w6-evaluation-matrix.md) · [ATAM](plans/w6-atam-template.md) · [CBAM](plans/w6-cbam-template.md) |
| W7 | Codex + CompositionOwner 的组合式证据最多，保留为回退；原生 scheduler、approval、host sandbox 等不能过度推断 | [W7 adoption](plans/w7-codex-atam-cbam-adoption-decision.md) |
| W8 | DeepSeek 插件生态有真实供给，但 E4 durable fallback ledger、全冷却安全停止、E5 人工生命周期和 E6 前置条件仍未闭合 | [plugin findings](plans/research/w8-deepseek-plugin-ecosystem-findings.md) · [E4 findings](plans/w8-deepseek-e4-provider-failover-v2-findings.md) |

## 开发入口与停止条件

正式产品开发从目标架构的 Stage 0/1 开始：冻结 DSH profile、插件 allowlist、Codex Worker artifact、wire/schema、parent/child identity 和 capability facade；随后只做 case-local、fake/loopback Provider、只读或隔离 worktree 的 H1–H5。

以下事项继续保持 `HOLD` / `unknown-stop`，不会被文档收口升级为通过：

- `1-6-3` 的宿主强制边界与 Codex native approval；
- 真实本地写入、apply、Git push、部署和其他不可逆 effect；
- DSH 候选插件的 durable Provider fallback/degradation ledger；
- 真实 Provider 的自然故障 failover、远端数据、任务、Webhook、备份、retention、账单和账户退出；
- 混合架构的人工安装、升级、备份/恢复、排障和退出计时。

任何关键 identity、permission、effect、process、Provider 或 replay 状态不能确认时，结果必须是 `unknown` / `safe-stop`，不能用最终文本或旧评测证据补齐。

## 工作区证据纪律

- 评测输出、`evaluation/runs` 和大体量 raw research ledger 是复核现场，不是默认源代码提交物；提交时只选择最小、脱敏、与变更直接相关的 fixture 或摘要。
- 不能通过删除历史证据来制造“clean”。本次只做文档和 ignore 收口；删除、移动、重命名历史文件须另行确认。
- 真实 API key、token、cookie、生产数据和原始 Provider 响应不得进入文档、日志、owner、backup、artifact 或 git。
