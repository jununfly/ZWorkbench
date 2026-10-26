# ADR 0019 (draft) — 编码证据 run 加 repo/branch/environment 上下文维度

- 状态：draft（grill 收敛中，待 zj 拍板后转正到 docs/zj-adr/）
- 来源：参照 ChatGPT Codex 桌面端「composer 上下文 chips」可借鉴点（见 docs/plans/ui-spec-chatgpt-codex-layout.md），映射到 ZW 编码证据域。
- 关联：ADR 0016（Go evidence B2-narrow owner）、AGENTS.md 所有权不变量。

## 1. 背景与动机

Codex 在 prompt 输入框上方用独立可点胶囊展示「仓库 / 本地 / 分支」三类上下文，语义是"这次执行跑在哪个语境里"。ZW 的编码证据 tab（`CodingEvidenceTab.tsx`）当前是 CompositionOwner 生命周期浏览器，**没有 composer 输入框**，且 Go evidence 后端**完全没有 repo/branch/environment 维度**。

经 grill 收敛，确定把"带语境的 run"真正搬进编码证据域：每次新建 run 携带其语境（在哪个被管理仓库、哪个分支、哪个环境），与 Codex 原意最贴合。

## 2. 决策

1. **runs 表加三列** `repo` / `branch` / `environment`（TEXT NOT NULL DEFAULT ''），SchemaVersion 1 → 2，Open 时做 v1→v2 迁移（`ALTER TABLE ... ADD COLUMN ... DEFAULT ''`）。
2. **配置层加 `ManagedRepos`**：`RepoSpec{Name, Path, Environments[]}`，持久化进 config.json 新段，`ZW_MANAGED_REPOS`(JSON) 覆盖；空配置时 `/api/context` **自动把 cwd 的 git 仓注册为默认仓库**（fallback，使本仓库 ZWorkbench 开箱即有上下文，无需手动配置），无 git 仓时返回空列表（前端回退 unknown）。
3. **新增 `GET /api/context`**：返回被管理仓库列表（含每仓 `current_branch`，非 git 仓返回 `"unknown"`）与默认选择；绝不 500。
4. **`POST /api/evidence/runs` 接收 `repo`/`branch`/`environment`**，落新列；缺省空串（显示层按 unknown 处理）。
5. **后端先行、前端后续**：本 ADR 只落地后端（配置 + 端点 + run 字段 + 单测）；前端「chips 表单」为独立后续节点，不在本 ADR 范围。

## 3. 约束（invariants）

- **单一 durable owner 不变式**：run 的语境字段由 evidence Owner 唯一拥有，不散落全局状态；schema 升级须保留 owner 写路径。
- **fail-closed**：git 不可用 / 非仓库 / 超时 → `current_branch="unknown"`，不返 500、不 panic。
- **零迁移风险**：旧 v1 内存/文件库必须能安全升到 v2（ALTER 加列带 DEFAULT）。
- **a11y 门禁**（前端后续节点）：chips 必须键盘可达，交互元素带 label（沿用 web a11y 门禁 G-V4）。
- **向后兼容**：`CreateRun` 原签名保留（委托），不破坏现有 40+ 测试。

## 4. 验收（本节点）

- `go build ./...` 通过；`go test ./app/internal/evidence/... ./app/internal/config/... ./app/internal/api/...` 通过。
- `GET /api/context`：git 仓返回真实分支；临时非 git 目录返回 `current_branch:"unknown"` 且 HTTP 200。
- `POST /api/evidence/runs` 带 `repo/branch/environment` → `GET /api/evidence/runs/{id}` 回显三字段。
- v1 旧库经 `Open` 迁移后 `CreateRunWithContext` 可写新列。
- 前端（tsc/eslint）本节点不动。

## 5. 风险与缓解

- **R1 git 运行时可用性**：容器内/远程环境可能无 git 二进制 → CurrentBranch 失败封闭为 unknown；不阻塞启动。
- **R2 范围膨胀**："多仓库 + 多环境"本质接近 epic → 严格按节点切分，本节点仅后端；前端 chips 独立。
- **R3 environment 真多环境**：ZW 当前无 container/remote 执行能力 → environment 本节点仅为**声明/展示字段**，不与真实执行耦合；真执行能力留待后续。
- **R4 路径安全**：repo.Path 来自配置（可信），非用户请求输入；仍作 exec 参数传入（非 shell 字符串拼接）。
- **R5 旧 config.json 兼容**：新增 persistFile 段缺失时 load 静默忽略，沿用默认。

## 6. 与 Codex 的映射

| Codex 元素 | ZW 落地 | 节点 |
|---|---|---|
| 仓库 chip | ManagedRepos + run.repo 列 | 本 ADR（后端） |
| 环境 chip（本地） | run.environment 列（多环境声明） | 本 ADR（后端） |
| 分支 chip | git current_branch + run.branch 列 | 本 ADR（后端） |
| chips 可点表单 | 编码证据新建 run 表单（`ChipSelect` popover 胶囊：仓库/环境用可点菜单，分支用原生 input；M3 主色 #6750A4） | 已实现（前端节点） |
| 空态织入上下文 | 工作台空态 | 后续（不在本 ADR） |
| 权限显式化（完全访问） | 不映射（ZW 本地优先） | 不采纳 |

## 7. 未决 / 后续

- ~~前端 chips 表单（独立节点）~~ **已实现**：`CodingEvidenceTab.tsx` 的「新建 run」按钮展开表单，仓库/环境用 `ChipSelect`（可点胶囊 + 下拉 menu popover，M3 主色 #6750A4），分支用原生 `<input>`；从 `/api/context` 预填可改，提交走 `POST /api/evidence/runs`；run 卡片与详情显示 `repo · branch · environment`。`ChipSelect` 用 `role="menu"/"menuitem"` 满足 G-V4（无 error 级违规，选中态用视觉高亮 + `✓` 表达，不依赖 `aria-selected`）。通过 check-web.sh 门禁（tsc + eslint a11y G-V4 + vite build 全绿）。
- ~~`/api/context` 空配置回退~~ **已实现 fallback**：无配置仓库时自动把 cwd 的 git 仓注册为默认仓库（含真实 `current_branch`），使本仓库 ZWorkbench 开箱即有上下文；非 git 目录仍返回空列表（前端回退 unknown）。单测 `TestContextAPIDefaultsToCwdRepo` 覆盖。
- 是否需按 repo 过滤 runs 列表（若要，现有列即可，无需再加索引，按需评估）。
- environment 真执行能力（container/remote）启用时，需补充真实执行接线 + 权限模型（本节点 environment 仍为声明字段）。
