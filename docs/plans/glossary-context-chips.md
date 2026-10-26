# Glossary — 编码证据上下文维度（与 ADR 0019 配套）

> grill 过程中沉淀的术语片段，待 ADR 转正时并入 docs/zj-adr/ 或 ZJ-CONTEXT.md。

## 术语

- **被管理仓库 (Managed Repo)**：ZW 配置中登记、编码证据 run 可关联的 git 仓库。由 `RepoSpec{Name, Path, Environments}` 描述；同一 ZW 实例可登记多个。
- **上下文 chips (Context Chips)**：Codex 借用的 UI 范式——在 composer 上方用独立可点胶囊展示「仓库 / 环境 / 分支」等执行语境。ZW 落地为编码证据新建 run 表单的 repo/branch/environment 选择控件（后续前端节点）。
- **current_branch**：被管理仓库当前的 git 分支（由 `git rev-parse --abbrev-ref HEAD` 读取）；非 git 仓或 git 不可用时回退 `"unknown"`（fail-closed）。
- **environment（执行环境）**：run 声明运行的宿主环境，枚举含 `local`（本地，恒存在）/ `container` / `remote`。本节点仅为声明字段，ZW 尚无 container/remote 真实执行能力。
- **run 上下文维度 (Run Context Dimensions)**：runs 表新增的 `repo` / `branch` / `environment` 三列，使每个 CompositionOwner run 携带其产生语境。
- **后端先行节点 (Backend-First Slice)**：本次 grill 收敛出的交付切片——先落地配置 + `/api/context` + run 字段 + 单测，前端 chips 表单延后。

## 不变量

- **单一 durable owner**：run 上下文字段归 evidence Owner 唯一拥有。
- **fail-closed git 探测**：git 探测失败一律 unknown，不 500。
- **向后兼容 CreateRun**：原签名保留，新增 `CreateRunWithContext` 供 router 调用。
