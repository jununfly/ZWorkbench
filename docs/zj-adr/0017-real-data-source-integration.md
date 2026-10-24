---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.datasource.real-source-integration
related: "0015,0016"
---

# ADR 0017：真实数据源接入策略（roadmap 1-2 epic）

> 状态 `accepted`：Human 于 2026-10-24 在「代码 / docs 与 roadmap 解耦」P1 评审中确认，
> 将 roadmap 1-2 数据源接入的既有实现沉淀为本 ADR。原决策已随代码落地，本 ADR 仅固化
> 稳定事实，不新增任何运行时行为；代码注释改为引用本 ADR（保留 `formerly roadmap X` 溯源）。

## Context

收尾图 1-2「真实数据源接入」把 7 个业务包（market / research / limitup / review /
inspection / optimization / mastery）从 `RemoteStubSource`（固定返回
`"remote source not wired yet (stub)"`）迁到真实 / 本地数据源。改造前的问题：

- 7 个包各自实现一个 stub，无统一开关、无统一失败语义；
- C36 回退永远被触发，且无法区分「没配」和「配了但坏了」；
- 重复实现（HTTP、超时、鉴权、失败分类）分散在 7 包。

与此同时，真实行情 / 研究源选型、本地可导入数据集、回退语义收敛是需要长期稳定的架构决策，
但此前只活在 roadmap 节点 1-2-1 ~ 1-2-5，随 roadmap 退役即成死链。本 ADR 把它们固化为
稳定事实源。

## Decision

### 1. 统一 datasource 契约与配置开关（formerly roadmap 1-2-1）

- 新增 `app/internal/datasource` 包，承载与领域无关的：配置、开关、超时、鉴权、
  HTTP GET + JSON 解码、失败分类。
- 业务包只保留「源名 + 路径 + 查询参数 + 领域结构」，不再重复实现。
- 纯 stdlib，零外部依赖（沿用 ADR 0015 的 Go 零 cgo 约束）。

### 2. 真实源选型：东方财富公开接口，免费免 token（formerly roadmap 1-2-2 / 1-2-2-1）

- market / research / limitup 经东方财富公开接口取真实 A 股数据；非官方接口，自用可接受。
- 若需合规化，仅改 `app/internal/<pkg>/eastmoney.go` 一处，业务包 `Source` 契约不动
  （接口隔离）。
- limitup 的 clist / ulist 子端点（D7）用基于真实读数的精确情绪阶段，取代纯涨停数启发式。

### 3. 本地可导入数据集（formerly roadmap 1-2-3 / 1-2-4）

- mastery（游资心法库 D9）、review（复盘 D8）、inspection / optimization（真实持仓输入
  D11 / D12 / D13）支持从本地文件导入。
- 与远程源分开：`DataFiles` 配置承载本地路径段；空串 = 未导入，回退内嵌快照。文件缺失
  与网络失败是不同失败语义，不混为一谈。

### 4. fallback 语义收敛（formerly roadmap 1-2-5）

- `Status` 四值枚举区分：未配置 / 源失败 / 陈旧快照 / 命中——三者都不当作成功，也不当
  同一种失败报警。
- `StatusCarrier` 接口让 7 包响应写入语义状态；`Source[T]` 泛型契约统一「多源回退」。
- `FallbackChain` 是 7 包回退循环的唯一真相源：语义改动只此一处，不再各包各写一遍。

## Consequences

- 7 包回退语义收敛到 `datasource` 包，C36 回退现在能正确区分「没配 / 坏了 / 陈旧」。
- 远程源开关与本地导入解耦，失败分类可观测。
- 真实源选型集中在各包 `eastmoney.go`，合规化 / 替换成本低。
- 本 ADR 取代 roadmap 1-2-1 ~ 1-2-5 作为数据源决策的稳定事实源；代码注释改为引用本 ADR
  （保留 `formerly roadmap X` 溯源）。
- 相关：ADR 0015（Go 零依赖）、ADR 0016（evidence B2，同属 1-5-6 收尾）。

## 溯源（formerly roadmap）

roadmap 1-2-1 / 1-2-2 / 1-2-2-1 / 1-2-3 / 1-2-4 / 1-2-5（含设计子标签 D7 / D8 / D9 / D11 /
D12 / D13）。
