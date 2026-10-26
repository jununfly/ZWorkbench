---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.coding-evidence.run-context
---

# ADR 0019：编码证据 run 加 repo/branch/environment 上下文维度

- 来源：参照 ChatGPT Codex 桌面端「composer 上下文 chips」可借鉴点（见 docs/plans/ui-spec-chatgpt-codex-layout.md），映射到 ZW 编码证据域。
- 关联：ADR 0016（Go evidence B2-narrow owner）、AGENTS.md 所有权不变量。

> 状态 `accepted`：经 grill 收敛（zj-grill-with-docs 技能被 override 禁用，按协议手动跑 scoping），zj 确认切片=Composer 上下文 chips、落点=编码证据「新建 run 表单」方案 A、repo=可切换被管理仓库、environment=真多环境声明、交付=后端先行分步；前端 chips 表单与 cwd fallback 作为后续节点已落地并随实现提交。

## Context

Codex 在 prompt 输入框上方用独立可点胶囊展示「仓库 / 本地 / 分支」三类上下文，语义是"这次执行跑在哪个语境里"。ZW 的编码证据 tab（`CodingEvidenceTab.tsx`）是 CompositionOwner 生命周期浏览器，**没有 composer 输入框**，且 Go evidence 后端**完全没有 repo/branch/environment 维度**。

确定把"带语境的 run"搬进编码证据域：每次新建 run 携带其语境（在哪个被管理仓库、哪个分支、哪个环境），与 Codex 原意最贴合。

## Decision

1. **runs 表加三列** `repo` / `branch` / `environment`（TEXT NOT NULL DEFAULT ''），SchemaVersion 1 → 2，`Open` 时做 v1→v2 幂等迁移（`ALTER TABLE ... ADD COLUMN ... DEFAULT ''`，按 `PRAGMA table_info` 存在性判定，避免重复列）。
2. **配置层加 `ManagedRepos`**：`RepoSpec{Name, Path, Environments[]}`，持久化进 config.json 新段，`ZW_MANAGED_REPOS`(JSON) 覆盖；空配置时 `/api/context` **自动把 cwd 的 git 仓注册为默认仓库**（fallback，使本仓库 ZWorkbench 开箱即有上下文，无需手动配置），无 git 仓时返回空列表（前端回退 unknown）。
3. **新增 `GET /api/context`**：返回被管理仓库列表（含每仓 `current_branch`，非 git 仓返回 `"unknown"`）与默认选择；绝不 500。空配置回退 cwd 仓（含真实 `current_branch`）。
4. **`POST /api/evidence/runs` 接收 `repo`/`branch`/`environment`**，落新列；缺省空串（显示层按 unknown 处理）。
5. **前端「新建 run」表单**：`CodingEvidenceTab.tsx` 的「新建 run」按钮展开表单，仓库/环境用 `ChipSelect`（可点胶囊 + 下拉 menu popover，M3 主色 #6750A4），分支用原生 `<input>`；从 `/api/context` 预填可改，提交走 `POST /api/evidence/runs`；run 卡片与详情显示 `repo · branch · environment`。`ChipSelect` 用 `role="menu"/"menuitem"` 满足 G-V4（无 error 级违规，选中态用视觉高亮 + `✓` 表达，不依赖 `aria-selected`）。

## Invariants（约束）

- **单一 durable owner 不变式**：run 的语境字段由 evidence Owner 唯一拥有，不散落全局状态；schema 升级须保留 owner 写路径。
- **fail-closed**：git 不可用 / 非仓库 / 超时 → `current_branch="unknown"`，不返 500、不 panic。
- **零迁移风险**：旧 v1 内存/文件库必须能安全升到 v2（ALTER 加列带 DEFAULT）。
- **a11y 门禁**：chips 必须键盘可达，交互元素带 label（沿用 web a11y 门禁 G-V4）。
- **向后兼容**：`CreateRun` 原签名保留（委托 `CreateRunWithContext`），不破坏现有 40+ 测试。

## Acceptance（验收）

- `go build ./...` 通过；`go test ./internal/api/... ./internal/vcs/... ./internal/evidence/... ./internal/config/...` 通过（含 `TestContextAPIDefaultsToCwdRepo` cwd fallback 覆盖）。
- `GET /api/context`：git 仓返回真实分支；临时非 git 目录返回 `current_branch:"unknown"` 且 HTTP 200；空配置时自动返回 cwd 仓。
- `POST /api/evidence/runs` 带 `repo/branch/environment` → `GET /api/evidence/runs/{id}` 回显三字段。
- v1 旧库经 `Open` 迁移后 `CreateRunWithContext` 可写新列。
- 前端 check-web.sh 门禁（tsc + eslint a11y G-V4 + vite build）全绿。

## Risks（风险与缓解）

- **R1 git 运行时可用性**：容器内/远程环境可能无 git 二进制 → CurrentBranch 失败封闭为 unknown；不阻塞启动。
- **R2 范围膨胀**："多仓库 + 多环境"本质接近 epic → 严格按节点切分，后端先行、前端 chips 独立。
- **R3 environment 真多环境**：ZW 当前无 container/remote 执行能力 → environment 仅为**声明/展示字段**，不与真实执行耦合；真执行能力留待后续。
- **R4 路径安全**：repo.Path 来自配置（可信），非用户请求输入；仍作 exec 参数传入（非 shell 字符串拼接）。
- **R5 旧 config.json 兼容**：新增 persistFile 段缺失时 load 静默忽略，沿用默认。

## Codex 映射

| Codex 元素 | ZW 落地 | 状态 |
|---|---|---|
| 仓库 chip | ManagedRepos + run.repo 列 | 已实现（后端 + 配置） |
| 环境 chip（本地） | run.environment 列（多环境声明） | 已实现（后端） |
| 分支 chip | git current_branch + run.branch 列 | 已实现（后端） |
| chips 可点表单 | 编码证据新建 run 表单（ChipSelect popover，M3 #6750A4） | 已实现（前端） |
| 空态织入上下文 | 工作台空态 | 后续（不在本 ADR） |
| 权限显式化（完全访问） | 不映射（ZW 本地优先） | 不采纳 |

## Follow-up（后续 / 未决）

- 是否需按 repo 过滤 runs 列表（若要，现有列即可，无需再加索引，按需评估）。
- environment 真执行能力（container/remote）启用时，需补充真实执行接线 + 权限模型（本 ADR environment 仍为声明字段）。
- 工作台空态织入上下文（见上表「空态织入上下文」）。

## Status

ACCEPTED 2026-10-26（zj，grill 收敛 + 实现提交确认）。后端 + 前端 chips 表单 + cwd fallback 均已随实现提交落地。
