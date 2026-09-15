---
doc-kind: architecture-map
authority: supporting
---

# ZWorkbench 文档地图

## 文档组织原则

本仓库文档按「ontology/wiki」组织：长期文档只保留无状态的实体、连接、事实、规则，不含过程标签（里程碑/提交/日期）。导航优先级：领域语言 → 方法论 → 设计/架构 → ADR。

## 阅读顺序

1. [领域语言](../ZJ-CONTEXT.md)：定义 Workbench、Harness、Run、Provider、effect、unknown 与 replay。
2. [方法论](methods/README.md)：定义证据层级、评测边界、失败语义与架构决策方法。
3. 设计与架构：见下方“架构手册”。
4. [ADR](zj-adr/README.md)：记录会长期约束系统结构的决策及其后果。

## 架构手册

- [系统概览](architecture/ta-overview.md) — 系统边界、主要组成与读者路由；authority-id: architecture.overview
- [分层与依赖](architecture/ta-layers.md) — DSH、Worker、Control Plane 与 Owner 的允许依赖；authority-id: architecture.layers.core
- [DSH runtime 集成](architecture/ta-dsh-runtime-integration.md) — 固定 artifact、manifest、启动与回滚边界；authority-id: architecture.subsystem.dsh-runtime-integration
- [Codex Worker bridge](architecture/ta-codex-worker-bridge.md) — Worker envelope、identity、失败关闭与进程生命周期；authority-id: architecture.subsystem.codex-worker-bridge
- [CompositionOwner](architecture/ta-composition-owner.md) — durable state、effect、approval、reconcile 与 backup/restore；authority-id: architecture.subsystem.composition-owner
- [本地只读运行流](architecture/ta-local-read-only-flow.md) — 从 preflight 到 owner-backed result 的触发、序列与退出；authority-id: architecture.flow.local-read-only-run
- [可恢复写入边界](architecture/ta-reversible-write-boundary.md) — write effect 的 HOLD、approval、host enforcement 与放行门；authority-id: architecture.cross-cutting.reversible-write-boundary
- [工作台用户界面](architecture/ta-workbench-user-surface.md) — 工作记录、任务详情、recorded view 与 owner-backed 界面边界；authority-id: architecture.user-surface.workbench

## 长期页面

- [方法论](methods/README.md) — 证据分层、失败语义与评测边界；authority-id: method.evidence-and-safety
- [ADR 0001：CompositionOwner 是唯一 durable owner](zj-adr/0001-composition-owner-is-the-unique-durable-owner.md) — 唯一 durable owner 的长期决定；authority-id: adr.composition-owner.unique-durable-owner
- [ADR 0002：映射版本只摘要引用语义](zj-adr/0002-ui-map-digests-reference-semantics-only.md) — 界面引用身份与迁移的长期决定；authority-id: adr.ui-reference.semantic-only-mapping-version
- [ADR 0003：工作台宿主是经回环提供的服务端渲染 HTML](zj-adr/0003-workbench-host-is-server-rendered-html-over-loopback.md) — 宿主形态的长期决定；authority-id: adr.ui-host.server-rendered-html-over-loopback
- [ADR 0004：宿主交互证据来自经 CDP 驱动的本机浏览器](zj-adr/0004-host-interaction-evidence-comes-from-a-local-browser-over-cdp.md) — 交互取证方式的长期决定；authority-id: adr.ui-host.interaction-evidence-via-local-cdp

## Product requirements

- [PRD 索引](prds/README.md) — 尚未实现或尚未由 owner-backed 证据证明的产品规格。

## Fixture documentation

- [Fixture 文档索引](../evaluation/fixtures/README.md) — 隔离输入、oracle、版本与安全约束；fixture documentation，不是产品或架构权威

## Agent skills

- [UI Reference skills binding](references/ui-reference-skills.md) — R1 产品规格与两个可独立安装的通用 UI 引用 skill 之间的 profile、验证和安全边界。

这一顺序优先回答“对象是什么、如何判断、如何连接、为何这样选择”，而不是复述某次
评测、路线节点或实现过程。

## 文档类型

| 类型 | 位置 | 允许内容 | 不承担的角色 |
|---|---|---|---|
| Wiki | `ZJ-CONTEXT.md`、`docs/methods/`、`docs/architecture/`、`docs/zj-adr/` | 实体、关系、事实、规则、稳定决策 | 单次运行结果或进度面板 |
| References | [docs/references/](references/README.md) | 外部合同、账户 owner 操作边界、受控 runbook | 默认产品配置或自动授权 |
| Fixture documentation | `evaluation/fixtures/**/README.md` | 隔离输入、oracle、版本和安全约束 | 产品使用或架构权威 |

文档中的目标和规则与代码/测试表达的是不同维度：代码、测试和运行产物证明当前实现事实，
文档权威页表达目标约束与稳定语义。发生差异时必须标记 target / implemented / unknown，
不能以一方静默替代另一方；稳定规则只回写一个 wiki 权威页。

## 系统边界

ZWorkbench 的目标组合由 DSH 主 Harness、进程外 Codex Coding Worker 与唯一的
CompositionOwner 构成。CompositionOwner 是跨 Run 的 run、attempt、event、effect、result、
approval、replay metadata 与 backup/restore 的唯一 durable owner。DSH、Codex、Provider 与
观测系统都只能提供输入、执行能力或 evidence，不能形成第二个 canonical state。

仓库中的可安装入口执行受控的本地只读任务；任何可产生副作用的动作都必须经过
`request → policy → decision → claim → execute → complete/reconcile`。未知 identity、permission、
effect、Provider 或 replay 状态必须 safe-stop。真实 Provider、真实写入、Git push、部署和 live
replay 只属于显式、受控的后续验证，不会由文档或历史 evidence 自动授权。

## 维护规则

- 新增稳定概念时，先更新领域语言、方法论、架构或 ADR 中的一个权威页；不要把同一规则复制到
  临时实现说明或评测结论。
- 不在仓库文档中保留实施过程、评测结论、研究 ledger 或路线状态；需要核对时以代码、测试、运行产物
  和 Git 历史为准。规划过程材料在其结论沉淀为权威页或 ADR 之后删除，不长期留存。
- 外部 Provider、凭证、账户、数据留存和退出的操作说明只放在 `docs/references/`；不记录 secret、
  原始资源标识、Prompt 或响应正文。
- 文档不以“已完成”“本轮”“日期”“commit”定义长期真相。需要 provenance 时，以 artifact receipt
  或 Git 历史为准，不复制到 wiki。

## 运行入口

- [References index](references/README.md) 提供真实 Provider 与账户 owner 的按需、只读入口。
- [Repository README](../README.md) 提供本地只读 CLI 的使用方式。
- [Agent instructions](../AGENTS.md) 定义协作时的执行、事实源和安全约束。
