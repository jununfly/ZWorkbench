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
6. **environment 拆成「授权」与「可达性」两条互不耦合的路径**（Follow-up ② 的前置契约）：
   - **授权＝白名单强制（硬约束，fail-closed）**：`POST /api/evidence/runs` 校验 `environment` 必须落在该仓库 `NormalizedEnvironments()` 内，否则 400；`repo` 非空但不在生效仓库列表（含 cwd fallback）同样 400。校验与 `/api/context` **共用 `resolvedRepos()`**，保证「前端能选到的」与「后端愿意接受的」口径不漂移。
   - **可达性＝只读探测（软提示，不阻断记账）**：新增 `internal/envprobe`（纯标准库，过零依赖守卫），按环境名归一化种类（`local` / `container`（或 `docker`）/ `remote:<endpoint>`），`GET /api/context` 每仓返回 `environment_status`（`available` + 可读 `reason`）。探测失败只影响提示文案，**不影响 run 能否记账**。
   - 分离理由：证据包是记账侧（durable owner），职责是「记下发生了什么」而非「决定能不能发生」。把执行可用性耦合进证据链会破坏 fail-closed 边界。

## Invariants（约束）

- **单一 durable owner 不变式**：run 的语境字段由 evidence Owner 唯一拥有，不散落全局状态；schema 升级须保留 owner 写路径。
- **fail-closed**：git 不可用 / 非仓库 / 超时 → `current_branch="unknown"`，不返 500、不 panic。
- **零迁移风险**：旧 v1 内存/文件库必须能安全升到 v2（ALTER 加列带 DEFAULT）。
- **a11y 门禁**：chips 必须键盘可达，交互元素带 label（沿用 web a11y 门禁 G-V4）。
- **向后兼容**：`CreateRun` 原签名保留（委托 `CreateRunWithContext`），不破坏现有 40+ 测试。
- **environment 白名单 fail-closed**：声称未授权环境即 400，且被拒请求**不得落库**（无半成品 run）。
- **授权与可达性不耦合**：可达性探测失败（docker 未装 / 端点不可达）只影响提示，绝不影响 run 记账；反之白名单通过也不代表环境可用。

## Acceptance（验收）

- `go build ./...` 通过；`go test ./internal/api/... ./internal/vcs/... ./internal/evidence/... ./internal/config/...` 通过（含 `TestContextAPIDefaultsToCwdRepo` cwd fallback 覆盖）。
- `GET /api/context`：git 仓返回真实分支；临时非 git 目录返回 `current_branch:"unknown"` 且 HTTP 200；空配置时自动返回 cwd 仓。
- `POST /api/evidence/runs` 带 `repo/branch/environment` → `GET /api/evidence/runs/{id}` 回显三字段。
- 白名单：`environment` 不在该仓库枚举内 → 400 且 `ListRuns()` 仍为空（`TestCreateRunRejectsUnlistedEnvironment`）；未知 `repo` → 400；`repo` 已声明但 `environment` 留空 → 200 且环境字段留空（`TestCreateRunAllowsEmptyEnvironment`）。
- 可达性：`GET /api/context` 的 `environment_status` 里 `local` 恒 `available:true`，未知种类（如 `staging`）为 `false` 且带可读 `reason`（`TestContextAPICarriesEnvironmentStatus`）。
- 零依赖守卫：`internal/envprobe` 仅用标准库，`ZW_ZERODEP_BUILD=1 go test ./internal/buildguard/` 通过（含 `CGO_ENABLED=0 go build`）。
- v1 旧库经 `Open` 迁移后 `CreateRunWithContext` 可写新列。
- 前端 check-web.sh 门禁（tsc + eslint a11y G-V4 + vite build）全绿。

## Risks（风险与缓解）

- **R1 git 运行时可用性**：容器内/远程环境可能无 git 二进制 → CurrentBranch 失败封闭为 unknown；不阻塞启动。
- **R2 范围膨胀**："多仓库 + 多环境"本质接近 epic → 严格按节点切分，后端先行、前端 chips 独立。
- **R3 environment 真多环境**：ZW 当前无 container/remote 执行器 → environment 仍为**声明字段**，但已补「授权（白名单强制）+ 可达性（只读探测）」两层前置契约；**真执行器本身**（起容器/连远程并驱动 run 生命周期）仍未实现，见 Follow-up。
- **R4 路径安全**：repo.Path 来自配置（可信），非用户请求输入；仍作 exec 参数传入（非 shell 字符串拼接）。
- **R5 旧 config.json 兼容**：新增 persistFile 段缺失时 load 静默忽略，沿用默认。

## Codex 映射

| Codex 元素 | ZW 落地 | 状态 |
|---|---|---|
| 仓库 chip | ManagedRepos + run.repo 列 | 已实现（后端 + 配置） |
| 环境 chip（本地） | run.environment 列（多环境声明）+ 白名单强制 + `envprobe` 可达性 | 已实现（后端 + 探测） |
| 分支 chip | git current_branch + run.branch 列 | 已实现（后端） |
| chips 可点表单 | 编码证据新建 run 表单（ChipSelect popover，M3 #6750A4） | 已实现（前端） |
| 空态织入上下文 | 工作台空态 | 后续（不在本 ADR） |
| 权限显式化（完全访问） | 不映射（ZW 本地优先） | 不采纳 |

## Follow-up（后续 / 未决）

- ~~按 repo 过滤 runs 列表~~ **已实现**：前端 `CodingEvidenceTab` 用已加载 runs 的 `repo` 字段做客户端过滤（原生 `<select>` + 关联 `<label>`，现有列即可，无需后端/索引）；选项取 runs 中去重 repo，含「全部」+「清除」，计数显示 `可见/总数`。
- ~~environment 真执行能力（container/remote）的前置契约~~ **已实现（决策 6）**：`environment` 拆成「授权＝白名单强制（400 fail-closed）」+「可达性＝`envprobe` 只读探测（`/api/context.environment_status`，仅提示不阻断记账）」两条路径。配套：`config.RepoSpec.NormalizedEnvironments/AllowsEnvironment`、`config.ManagedRepos.FindRepo`、`api.resolvedRepos`（与 `/api/context` 共用）、`internal/envprobe`（纯标准库）；前端在环境 chip 下显示「当前不可用：<reason>（仍可记账）」。
- **真执行器（仍未实现）**：起容器/连远程并**驱动 run 生命周期**（start → 执行 → 退出码记账 → complete/fail）。落地前提已明确：① 执行器抽象（`os/exec` 调 docker CLI 可过零依赖守卫，不引 SDK）；② 超时/取消与日志采集；③ 审批门（沿用 `waiting_approval` 状态，非静默放行）；④ 与 `exit_ledger`「无真实远程 provider」断言对齐（真执行后该断言需按证据 caliber 修正，不得默认升级为「已清场」）。
- 工作台空态织入上下文（见上表「空态织入上下文」）。

## Status

ACCEPTED 2026-10-26（zj，grill 收敛 + 实现提交确认）。后端 + 前端 chips 表单 + cwd fallback 均已随实现提交落地。
