---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.coding-evidence.b2.pulled-forward
supersedes: 0015
---

# ADR 0016：coding-evidence 路线 B2 提前 —— C26/C28 用 Go 重写进 app/，B1 sidecar 退出

> 状态 `accepted`：Human 于 2026-10-14 在路线图 `1-5-6` 节点执行 `decide` 选 B，将 ADR 0015 原定「留作 1→100 后续」的 B2 路线提前到 `1-5-6` 落地。

## Context

ADR 0015（同日 `accepted`）在 Decision 1 把 ZW 差异化证据核心（CompositionOwner C26 / safe-stop C28）的处理定为二选一：

- **B1**：Python `src/zworkbench` 作为**可选本地 sidecar**，Go 经 loopback 调其证据 API；
- **B2**：把证据概念用 Go 重写进 `data`/`api` 层，留作 1→100 阶段后续决策。

0015 选了「B1 当前 + B2 未来」的过渡态，理由是 B2 重写量大、应后置。

但 0015 的核心前提是「Go 全 pivot」——主运行时彻底从 Python 换成 Go。保留一个「可选但活接线」的 Python 证据 sidecar，与「全 pivot」的语义存在落差：它让一个 Python 进程（即便可选）继续存在于工作台的运行拓扑里，后续读者容易误读成「这里又回 Python 做业务」。2026-10-14，Human 在 `1-5-6` 节点明确 `选 B`，决定把 B2 提前执行——用 Go 直接重写 C26/C28，彻底去掉 Python 进程依赖。

## Decision

### 1. coding-evidence 路线从 B1 翻转为 B2（仅此路径）

- 撤销 ADR 0015 Decision 1 的 B1 sidecar 路线：Go **不再** spawn / loopback 调用 Python 证据 API。
- B2 提前到 `1-5-6` 落地：用 Go 重写 CompositionOwner（C26）与 safe-stop（C28）证据核心，落进 `app/` 的 `data`/`api` 层，零 Python 进程依赖。
- 路线图节点 `1-5-6` 已据本决策改写（label / notes / exit_criteria 翻为 B2；旧 B1 判据已 clear），见 roadmap CLI `decide` 记录。

### 2. Python `src/zworkbench` 保留为历史/参考物，不再接线

- `src/zworkbench`（C26/C28 的既有 Python 实现）作为架构演进证据**保留**于 git 历史，不删除；
- 但它**不再被 `app/` 以任何方式调用**（无 sidecar、无 loopback、无 import）；其 `dependencies=[]` 零依赖属性不变，但仅作为静态历史事实，不进入运行拓扑。

### 3. 本 ADR 仅局部 supersede 0015

- 被取代的 0015 条款：**Decision 1 的 B1/B2 路线句**（"按路线 B1 作为可选本地 sidecar…路线 B2…留作 1→100 阶段的后续决策"）、**Decision 4 的 "Go 经 sidecar 调用" 表述**、**未解决 的 B2 bullet**（"B2…待 1→100 阶段按证据决定"）。
- 0015 **继续有效**的条款：主运行时=Go（`app/`）、Electron 改 spawn Go 二进制、Python `dependencies=[]` 仍为事实、Node/Electron 仅 `app/electron` devDependency、偏离性质为构建/分发期、PolyForm NC 处理。这些与 B2 提前不冲突。

## Consequences

- ADR 0015 相应条款以本 ADR 为准；0015 顶部已加局部 supersede banner。
- `1-5-6` 范围显著放大：从「接线切片」变为「C26/C28 的 Go 重写」——接近子项目。建议实现前用子节点 `1-5-6-1`（C26 Go 化）/ `1-5-6-2`（C28 Go 化）/ `1-5-6-3`（coding-evidence tab 接 Go）作 scope gate，避免单节点失控。
- 零依赖守卫：`test_zero_dependency_guard.py` 仍守 Python 侧（现为历史目录）；`app/` 的 Go 零 cgo 守卫（关联 1-5-8）仍需补齐，否则 Go 侧偏离无机械验证——本 ADR 不改变该缺口。
- 撤回弹性下降：若未来要「回到 Python 主运行时 / 恢复 B1 sidecar」，须重新移植或重新接线 C26/C28，成本高于 0015 原过渡态。这是 B2 提前的明确 trade-off，Human 已知情。
- README 索引新增本 ADR，并标注 0015 的 B1/B2 路线被本 ADR 局部 supersede。

## 未解决（不在本 ADR 范围）

- C26/C28 在 Python `src/zworkbench` 中的完整语义与未文档化边界，尚未在 Go 侧逐条对齐——属 `1-5-6-1` / `1-5-6-2` 的实现 scope，不在此处决策。
- B2 落地后的「证据核心」测试覆盖如何复用既有 Python 测试契约，待实现时定。
