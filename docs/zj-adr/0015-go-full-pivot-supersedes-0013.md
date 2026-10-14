---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.go.full.pivot
supersedes: 0013
---

> **Partially superseded by [ADR 0016](0016-coding-evidence-b2-pulled-forward.md) (2026-10-14):** the B1 sidecar route and the "B2 deferred to 1→100" clause in Decision 1, the "Go 经 sidecar 调用" phrasing in Decision 4, and the B2 bullet in 未解决 are superseded — coding-evidence now follows B2 (Go reimplements C26/C28 in `app/`, zero Python process). The rest of ADR 0015 remains in force.

# ADR 0015：Go 全 pivot —— 取代 ADR 0013 的桌面壳偏离边界

> 状态 `accepted`：Human 于 2026-10-14 在路线图 `1-5`（B 方向）明确选择「Go 全 pivot」，
> 推翻 ADR 0013 的核心前提。`supersedes ADR 0013`。

## Context

ADR 0013 把 ZWorkbench 的桌面形态建立在两个前提上：

1. **Python 零依赖核心是运行时**（`pyproject.toml` 的 `dependencies = []`）；
2. Electron 只是**薄壳**，spawn 既有的 Python `ui-host`（server-rendered HTML，ADR 0003），
   自己不持有业务逻辑。

在此前提下，`desktop/` 被登记为一个「可选外壳」式的偏离：Node/Electron 只存在于
`desktop/` 的 `devDependencies`，删掉整个目录核心不受影响。

2026-10-14，Human 重新评估语言策略后选择 **B：Go 全 pivot**——以 Go 为主运行时镜像
easy-stock（Go 本地 API + React/TS 前端 + Electron 壳 + SQLite），不再让 Python 充当 UI 运行时。
这一选择使 ADR 0013 的两个前提同时失效：

- 主运行时从 Python 变成 **Go**（`app/`，`module github.com/jununfly/ZWorkbench/app`）；
- Electron 壳从「spawn Python ui-host」变成「**spawn Go 二进制**」，并承载前端资源。

与此同时，已提交的 `desktop/`（Phase 1，含菜单/托盘/单实例锁/自检/截图 harness，1-1-1/1-1-2
已完成、1-1-3 打包 in_progress）不再作为活跃方案——它构造的是 Python-ui-host 桌面壳，与 B 互斥。

本 ADR 的作用：在 B 已被接受的前提下，**重新划界**「零依赖 / 偏离」语义，取代 ADR 0013 的旧边界。

## Decision

### 1. 主运行时 = Go（镜像 easy-stock），Python 核心降为可选 sidecar

- 工作台的主业务逻辑运行在 **Go 本地服务**（`app/cmd/server` + `app/internal/*`），
  纯标准库起骨架，零 cgo 外部依赖（证据底座待 1-5-5 用 `modernc.org/sqlite` 非 cgo 驱动落地）。
- 既有的 Python 核心（`src/zworkbench`，CompositionOwner C26 / safe-stop C28）**不删除**，
  按路线 B1 作为**可选本地 sidecar**存在：Go 经 loopback 调其证据 API；删除不影响主工作台。
  路线 B2（把证据概念用 Go 重写进 `data`/`api` 层）留作 1→100 阶段的后续决策。

### 2. 「零依赖 / 偏离」语义重新划界

| 维度 | ADR 0013（已 supersede） | 本 ADR（B 之后） |
|---|---|---|
| Python 运行时依赖 | 零第三方依赖（核心边界） | 不变：`src/zworkbench` 仍 `dependencies=[]` |
| Node/Electron | 仅 `desktop/` devDependency，spawn Python | 仅 `app/electron` devDependency，spawn **Go 二进制** |
| Go 运行时 | 不存在 | 主运行时；保持零 cgo 外部依赖（无 cgo 驱动） |
| 偏离守卫 | `tests/test_zero_dependency_guard.py` 守 Python 侧 | 同守卫保留并**扩展**到 `app/`：Go 侧零 cgo 依赖需等价守卫（见未解决） |

偏离性质仍为「构建/分发期」而非「核心运行时」：`electron` 只在打包分发 `app/` 时需要；
`app/` 的 Go 服务本身 `go build` 出单一二进制即可运行，不依赖 Python 或 Node。

### 3. `desktop/` 转入 retired（保留 git 历史，停止新开发）

- `desktop/`（旧 Python-ui-host 壳）不再活跃：不再新增功能、不再推进 `1-1-3` 的 electron-builder
  打包（打包目标改为 Go 二进制，归 `1-5-2`）。
- 代码**保留**作架构演进证据，不删除；路线图节点 `1-1`（及其子节点）通过 `1-5` 的
  `supersedes` 边与 retired 决策标注为历史。

### 4. 差异化证据能力不丢，仅换承载位置

CompositionOwner（C26）与 safe-stop（C28）仍是 ZW 的差异化核心，只是从「Python 主运行时内」
变为「Go 经 sidecar 调用」或「后续 Go 移植」。语义不变，位置可变。

## Consequences

- **ADR 0013 被本 ADR `supersedes`**：其「Node/Electron 只存在于 desktop/、Python 核心零依赖」
  的边界定义以本 ADR 为准；旧文档保留历史语义，标注 `superseded by 0015`。
- 新打包目标 = **Go 二进制**（1-5-2）；electron-builder 配置从 `desktop/` 迁移到 `app/electron`。
- `test_zero_dependency_guard.py` 继续守 Python 侧；`app/` 的 Go 零 cgo 依赖守卫需在 1-5-8
  或后续补齐，否则 Go 侧偏离无机械验证。
- PolyForm NC（easy-stock 许可证）：本工作台**仅参考其架构并重写**，非原样分发其代码；
  个人非商业使用 OK；商业化前再处理授权。
- 若将来撤回 B（回到 Python 主运行时），恢复 ADR 0013 语义即可，`desktop/` 历史仍在。

## 未解决（不在本 ADR 范围）

- `app/`（Go）的等价零依赖守卫尚未建立——ADR 0013 的守卫只覆盖 Python 侧；需在 `app/`
  落地对 `go.mod` 无 cgo 依赖 / `app/electron` 仅 devDependency 的静态断言（关联 1-5-8）。
- macOS 签名/公证、Windows 构建、自动更新——属 `1-5-2` 及后续，不在本 ADR 定义。
- B2（CompositionOwner 的 Go 移植）是否执行、何时执行——待 1→100 阶段按证据决定。
