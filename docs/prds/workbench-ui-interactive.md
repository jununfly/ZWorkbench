---
title: 完整工作台 Web-UI（含交互）
status: draft
type: prd
depends_on:
  - docs/prds/issue-1-workbench-ui.md
  - docs/designs/issue-1-workbench-ui-implementation.md
  - docs/plans/research/dsh-web-capability-fit/2026-09-19-conclusion-report.md
  - docs/zj-adr/0007-dsh-web-treated-as-external-capability-reference.md
  - docs/prds/r2-ui-reference-skills.md
style_reference: docs/designs/assets/zworkbench-workbench-prototype.html
decisions_resolved:
  - D1: IA 方向 = A 会话优先（B 画布 / C 日记 留后续 gate）
  - D2: 交互深度 = 本轮只交付纯 UI 壳 + 只读投影 + disabled/stopped 态（F6 发送 / F12 审批执行 另开 product scope gate）
  - D3: 三变体切换器 = 保留为开发期调试工具（?variant=A/B/C）
  - Q4: ?variant= 调试切换器 = 纯 client 端 query 参数分支，不接入 ui_build 生产构建管线
review_note: DRAFT，存于 docs/prds/ 供 review 后修改。
review_note: 本文档为 DRAFT，保存于 docs/prds/ 便于 review 后直接修改；尚未发布到 issue tracker。所有已决决策见 frontmatter decisions_resolved 与 §4。
---

# 完整工作台 Web-UI（含交互）

## 1. 意图与边界

把 Issue #1 已交付的**只读三视图切片**推进为**可交互的完整工作台主界面**。

已决方向（见 §4）：
- **IA 方向 = A 会话优先**（工作记录即对话流），复用现有三视图内容；B 命令画布 / C 项目日记留后续独立 gate，本轮不构建。
- **本轮交互深度 = 纯 UI 壳 + 只读投影 + disabled/stopped 态**；真实发送（F6）/ 审批执行（F12）触碰 CompositionOwner / Run / Approval，留独立 product scope gate，本轮只渲染其 disabled 壳。
- **三变体切换器保留为开发期调试工具**（`?variant=A/B/C`），不向最终用户暴露，用于对照原型三变体。

两条硬约束（来自既有决策，不可越过）：

- **ADR 0003 / 0006**：仍是 server-rendered HTML over loopback，单一构建身份；交互用**渐进增强的小段 JS**，不引入 SPA 框架。
- **ADR 0007 + 结论报告**：dsh-web 仅作**外部能力参考**，只选择性复用其**最小只读 surface**（如 `/session-references` 身份投影），**绝不整包吸纳、绝不引入 dsh-web 运行时依赖**。本工作台交互连接的是**本地 CompositionOwner**，不是 dsh-web。

## 2. 已落地——明确不要重复实现

以下在 Issue #1 已实现，本次只可"调整"不可"重建"：

| 模块 / 文件 | 内容 |
|---|---|
| `src/zworkbench/ui_style.py` | 暖色调 CSS token（与原型 `--ink/--canvas/--jade/--amber/--rose` 一致） |
| `ui_home.py` / `ui_task_detail.py` / `ui_record_view.py` | 三视图（home / task-detail / record-view）server-render |
| `ui_view_model.py` | owner-backed 状态只读投影；**已落地 Host Capability Facade 与 DSH 身份投影**（dsh-web 对齐的部分已在此） |
| `ui_review.py` / `ui_script.py` | Review-mode 交互骨架（ADR 0005） |
| `ui_ref/ui_manifest/ui_build/ui_declare/ui_runtime/ui_matrix/ui_token` | 构建/声明/运行时/验收矩阵/视觉 token 管线 |
| `tests/test_ui_style.py` `test_ui_no_horizontal_scroll.py` `test_ui_no_side_effects.py` `test_ui_redaction_host.py` `test_ui_ref.py` `test_ui_viewport.py` `test_ui_home_surface.py` `test_ui_host.py` `test_ui_lifecycle.py` `test_ui_review.py` `test_ui_matrix.py` | 验收测试（含 reduced-motion、双视口无横向滚动、host 脱敏） |
| 响应式与降级 | ≤760px 单栏、`prefers-reduced-motion` 禁用过渡——已覆盖，勿重建 |

## 3. 原子化 Features 清单

分类图例：
- ✅ 已落地（勿重复）
- 🔨 本轮构建（纯 UI，仅 server-render + 渐进 JS，不碰运行时）
- 🚧 需 product scope gate（触碰 CompositionOwner / Run / Approval / Effect，**非纯 UI**，须按 AGENTS.md Step 1 另开 gate）
- ⏭ 后续 gate（本轮不做，方向已定但留独立 gate 推进）
- ⛔ 明确不做

| ID | 功能 | 分类 | 依据 / 说明 | 依赖 |
|---|---|---|---|---|
| F1 | 信息架构（IA）方向选定：A 会话优先 / B 画布 / C 日记 / 混合 | ✅ 已决（A 优先） | **D1 已拍板：先 A 会话优先**；B 画布、C 日记转为 ⏭ 后续 gate，不本轮构建 | 决定 F3–F9 形态 |
| F2 | 顶栏 shell（brand / crumb / tags / pills / icon-button） | 🔨 构建 | 原型 token 已对齐 `ui_style`；Issue #1 顶栏偏简，补齐 tags(pill) 状态语义 | `ui_style` |
| F3 | 侧栏工作记录导航（side-panel：新建 / 近期工作 / 工作区） | 🔨 构建（A 已定） | 纯导航壳，数据来自 owner-backed 投影 | `ui_view_model` |
| F4 | 会话消息流（message / avatar / meta / plan-card） | 🔨 构建（A 已定） | 只读渲染既有工作记录消息；plan-card 步骤态来自 `ui_view_model` | `ui_view_model` |
| F5 | 计划卡（working plan：done/current/pending 步骤） | 🔨 构建 | 同 F4 内聚，状态由投影驱动 | `ui_view_model` |
| F6 | 输入 composer 由只读 → 真实发送 | ⏭ 后续 gate | **D2 已拍板：本轮只渲染只读壳 + disabled 态**；真实发送（触发 agent Run）留独立 product gate | CompositionOwner/Run |
| F7 | 运行事实检查器（inspector：mode/workspace/approval/worker、effect/approval、evidence links） | 🔨 渲染 + ⏭ 实时值 | 壳与态纯 UI（本轮做）；实时值来自投影/运行时，**留 gate** | `ui_view_model` |
| F8 | 命令画布（canvas-layout：command-path 节点 / decision notes / artifact panel / run-rail） | ⏭ 后续 gate（B 留后续） | **D1 已拍板：B 留后续**，本轮不构建 | `ui_view_model` |
| F9 | 项目日记（journal-layout：index / reading / evidence-table） | ⏭ 后续 gate（C 留后续） | **D1 已拍板：C 留后续**，本轮不构建 | `ui_view_model` |
| F10 | 运行轨道栏（run-rail：状态 / 可执行 Run / Owner 记录 / 证据时间线） | 🔨 渲染 + ⏭ 实时 | 渲染壳纯 UI（本轮做）；"可执行 Run"按钮触发 🚧，**留 gate** | CompositionOwner |
| F11 | 场景状态机 UI（empty / planning / approval / stopped） | 🔨 渲染 | 四态切换纯 UI；映射到真实 safe-stop/approval 逻辑属 🚧 | `ui_review` |
| F12 | 审批执行 UI（apply diff / Approval / retry / effect receipt） | ⏭ 后续 gate | **D2 已拍板：写能力交互留独立 gate**；Issue #1 明确 NON-GOAL | Approval/Effect |
| F13 | 安全停止 / reconcile UI（identity unresolved → 停 + 请求 reconcile） | 🔨 渲染 + ⏭ 逻辑 | 横幅/停止卡壳 + stopped 态纯 UI（本轮做）；越界判定逻辑部分已在 `ui_review`，**留 gate** | `ui_review` |
| F14 | DSH 对齐只读 surface（`/session-references` 身份投影） | ✅ 部分已落地 | `ui_view_model` 已有 Host Capability Facade + DSH 身份投影；本轮仅**扩展只读投影**，不引 dsh-web 运行时 | ADR 0007 |
| F15 | r2-ui-reference-skills 协同 UI（profile_status / runtime_status 可视化调用与结果呈现） | 🔨 构建 | 元 UI：把 `skills/ui-reference-*` 的状态检查可视化，提升 human↔agent 协同 | `ui_reference` skills |
| F16 | 响应式 & 降级（≤760px / reduced-motion） | ✅ 已落地 | Issue #1 已覆盖，勿重建 | — |
| F17 | 本地运行/调试接入（loopback server + CDP harness） | ✅ 已落地 | `local_run.py` / `cli.py` / `tests` 已有；仅扩展新交互测试 | — |
| F18 | 证据 live replay（伪装 deterministic replay） | ⛔ 不做 | 原型明确 "no live replay"；记录视图是只读投影，不可伪装确定性回放 | ADR 0004 |
| F19 | 三变体调试切换器（`?variant=A/B/C` 开发期工具） | 🔨 开发期工具 | **D3 已拍板：保留为开发期调试工具**，不向最终用户暴露；用于对照原型三变体（A 会话 / B 画布 / C 日记）。**Q4 已拍板：纯 client 端 query 参数分支，不接入 `ui_build` 构建管线**，避免污染生产构建 | `ui_style` |

## 3b. 本轮交付范围（Round 1）

**In-scope（🔨 本轮构建）：**
- F1 方向落定（A 会话优先的壳与内容组织）
- F2 顶栏状态语义 shell
- F3 侧栏工作记录导航（A 向）
- F4 会话消息流（只读渲染）
- F5 计划卡（投影驱动）
- F7 渲染壳 + F10 渲染壳 + F13 横幅/停止卡壳（仅渲染，不含实时值/可执行/判定逻辑）
- F11 场景四态渲染
- F14 扩展只读投影（dsh-web 对齐，不引运行时）
- F15 r2 协同可视化
- F19 `?variant=` 开发期切换器

**Out-of-scope（⏭ 后续 gate）：**
- F6 真实发送、F12 审批执行（D2 明确留独立 product gate）
- F7/F10 的实时值/可执行 Run、F13 的越界判定逻辑（🚧 触碰运行时，留 gate）
- F8 命令画布（B）、F9 项目日记（C）（D1 明确留后续 gate）

**不做（⛔）：**
- F18 live replay

## 4. 决策（D）—— 已拍板

- **D1 — IA 方向**：✅ **A 会话优先**。B 画布 / C 日记 留后续独立 gate，本轮不构建。
- **D2 — 交互深度**：✅ **本轮只交付纯 UI 壳 + 只读投影 + disabled/stopped 态**。F6（发送）与 F12（审批执行）触碰 Run/Approval/Effect，转为 ⏭ 后续 product scope gate；F7/F10/F13 的运行时部分（实时值 / 可执行 Run / 越界判定）同理留 gate。
- **D3 — 三变体切换器**：✅ **保留为开发期调试工具**（`?variant=A/B/C`），不向最终用户暴露。

## 5. dsh-web 对齐映射（只读，不引入运行时）

| dsh-web 概念 | 在本工作台的处理 |
|---|---|
| 会话/能力 surface | 仅复用其 `/session-references` 式的**只读身份投影**思路，已在 `ui_view_model` Host Capability Facade 落地 |
| 运行时 / 依赖 | ⛔ 不引入；本工作台连接本地 CompositionOwner |
| 整包吸纳 | ⛔ 不采纳（ADR 0007） |

## 6. 协同 Skills 使用与改进

- **`r2-ui-reference-skills`**（ui-reference-protocol 做设计 ratify / ui-reference-runtime 做真实浏览器验收）：本轮用其 profile_status / runtime_status 把"界面是否对齐规格"可视化（对应 F15）。
- **`zj-roadmap-driven`**：把 F1–F19 落成 roadmap 节点，逐节点推进（本轮节点 = In-scope 的 🔨 项）。
- **`zj-docs-ontology`**：本 spec 与 ADR 0007、issue-1 实现规格的引用保持地图一致。
- **改进钩子**：实际使用中若发现 `r2-ui-reference-skills` 的 status catalog 不足以表达"场景态（empty/planning/approval/stopped）"或"IA 变体（A/B/C）"，回流扩写其 `status_catalog` 与 skill 文案——这是用户明确要求"在使用中改进 skills"的落点。

## 7. 验收方式

- 复用 `ui_matrix.py` 覆盖清单（从 R1 PRD 转录），新增交互项回填覆盖矩阵。
- 扩展既有测试：横滚动/reduced-motion（`test_ui_no_horizontal_scroll.py` / `test_ui_style.py`）、Review/safe-stop 态（`test_ui_review.py`）。
- 新交互（composer disabled、scenario 切换、safe-stop 横幅、`?variant=` 切换）补 CDP 驱动断言（复用 `tests/browser.py` 的 `reduced_motion` 机制）。

## 8. 开放问题

1. 三视图（Issue #1）与 A 会话优先 IA 如何共存——替换还是嵌套？（建议：A 会话流作 home 主区，三视图作 task-detail / record-view 子投影，不替换。）
2. `ui_view_model` 的 DSH 身份投影是否需扩展字段满足 F14「对齐」诉求？（F14 实现时确认。）
