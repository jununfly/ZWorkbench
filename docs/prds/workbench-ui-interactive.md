---
title: 完整工作台 Web-UI（含交互）
status: active
type: prd
depends_on:
  - docs/prds/issue-1-workbench-ui.md
  - docs/designs/issue-1-workbench-ui-implementation.md
  - docs/zj-adr/0007-dsh-web-treated-as-external-capability-reference.md
  - docs/prds/r2-ui-reference-skills.md
style_reference: docs/designs/assets/zworkbench-workbench-prototype.html
decisions_resolved:
  - D1: IA 方向 = A 会话优先（B 画布 / C 日记 留后续 gate）
  - D2: 交互深度 = 本轮只交付纯 UI 壳 + 只读投影 + disabled/stopped 态（F6 发送 / F12 审批执行 另开 product scope gate）
  - D3: 三变体切换器 = 保留为开发期调试工具（?variant=A/B/C）
  - Q4: ?variant= 调试切换器 = 纯 client 端 query 参数分支，不接入 ui_build 生产构建管线
  - D4: 交互深度 gate 已开并交付——F6/F8/F9/F12 的 product scope gate 与 F7-live/F10-exec/F13-logic 的 🚧 部分，经 Issue #1 实现规格「Interactive write seams」全部 completed 交付（不再是"留 gate"待办）；真实写入/审批/reconcile 仅当宿主注入对应 facade 时可用，否则沿用 Round-1 只读契约（POST 404）
review_note: 2026-09-27 刷新——原 DRAFT 的 §3 分类与 §3b Round-1 范围已与 issue-1 实现规格的「Interactive write seams」小节对齐；除 F18 外 F1–F13 均已交付。本文档反映已交付状态，仍可按 review 意见修订。
review_note: 本 PRD 与 issue-1 实现规格对"交互/写入能力"的口径已对齐；交互/写入能力的 durable 事实源是 issue-1 实现规格「Interactive write seams (post-Round-1)」小节与 ADR 0003（宿主只读边界），本 PRD 在 §3c / §9 登记已交付写 seam。
---

# 完整工作台 Web-UI（含交互）

> 设计层（IA 决策 D1–D4、dsh-web 对齐边界、写 seam 宿主契约、F1–F19 功能目录）已沉淀为长期设计实体，见文末「相关设计实体」。本 PRD 保留需求/范围/验收与跨文档口径。

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

完整 F1–F19 功能目录（ID / 功能 / 分类 / 依据 / 依赖）已沉淀为设计实体 [pf-workbench-features](../designs/pf-workbench-features.md)，本 PRD 不再复制该表。

分类图例（与 [pf-workbench-features](../designs/pf-workbench-features.md) 一致）：
- ✅ 已落地（勿重复）
- 🔨 本轮构建（纯 UI，仅 server-render + 渐进 JS，不碰运行时）
- 🚧 需 product scope gate（触碰 CompositionOwner / Run / Approval / Effect，**非纯 UI**，须按 AGENTS.md Step 1 另开 gate）
- ⏭ 后续 gate（本轮不做，方向已定但留独立 gate 推进）
- ⛔ 明确不做

交互/写入能力的 durable 事实源是 `docs/designs/issue-1-workbench-ui-implementation.md` 的「Interactive write seams (post-Round-1)」小节（四写 seam + 宿主契约）与 ADR 0003（宿主只读边界）；本 PRD 的 §3c 与之对齐，不再另设路线图为事实源。

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

> 上述 ⏭ / 🚧 原标"留 gate"项，已在下方 §3c 全部交付。

## 3c. 越过 Round-1 的已交付项（交互写 seam）

D2/D1 原把以下项标为"留 gate"，已由后续 product gate 全部交付（落地于 issue-1 实现规格「Interactive write seams」小节与对应宿主契约）。完整写 seam → facade → POST 合同见设计实体 [ep-write-seam-journey](../designs/ep-write-seam-journey.md)。

| 项 | 路线图节点 | 写 seam / 宿主契约 |
|---|---|---|
| F6 composer 真实发送 | Issue #1 实现规格「Interactive write seams」 | 宿主注入 command facade → POST /api/runs 真实建 Run；无 facade 则 404 |
| F10 可执行 Run | Issue #1 实现规格「Interactive write seams」 | 复用 command facade |
| F11 场景真实控制 | Issue #1 实现规格「Interactive write seams」 | 宿主注入 scenario facade → POST /api/scenario-state（request_stop / request_approval）；无 facade 则 404 |
| F12 审批执行 | Issue #1 实现规格「Interactive write seams」 | 宿主注入 approval facade → POST /api/approvals（approve / deny）；deny 强制非空理由；无 facade 则 404 |
| F13 越界判定 + reconcile | Issue #1 实现规格「Interactive write seams」 | 宿主注入 reconcile facade → POST /api/reconcile 触发 owner.reconcile_identity；无 facade 则 404 |
| F7 实时值 | Issue #1 实现规格「Interactive write seams」 | 每次轮询经 resolve_view 重投影，只读无副作用 |
| F8 ?variant=B | Issue #1 实现规格「Interactive write seams」 | canvas 变体布局 |
| F9 ?variant=C | Issue #1 实现规格「Interactive write seams」 | journal 变体布局 |

不变式（沿用 Round-1 + ADR 0003）：**所有真实写入 / 审批 / reconcile 仅在宿主注入对应 facade 时暴露**；只读宿主（CLI `ui-host`）一律 disabled 占位 + POST 404。可写宿主由 CLI `ui --db <path>`（dogfood）提供，接真实 CompositionOwner + 四 facade。

## 4. 决策（D）—— 已拍板

设计决策 D1–D4 与 Q4 的完整表述已沉淀为设计实体 [pd-interactive-workbench](../designs/pd-interactive-workbench.md)，本 PRD 仅保留结论：

- **D1 — IA 方向**：✅ **A 会话优先**。B 画布 / C 日记 留后续独立 gate，本轮不构建。
- **D2 — 交互深度**：✅ **本轮只交付纯 UI 壳 + 只读投影 + disabled/stopped 态**。F6（发送）与 F12（审批执行）触碰 Run/Approval/Effect，转为 ⏭ 后续 product scope gate；F7/F10/F13 的运行时部分（实时值 / 可执行 Run / 越界判定）同理留 gate。
- **D3 — 三变体切换器**：✅ **保留为开发期调试工具**（`?variant=A/B/C`），不向最终用户暴露。
- **D4 — 交互深度 gate 已开并交付**：✅ D2 原留的 gate（F6/F12 product scope、F7-live/F10-exec/F13-logic 🚧）与 D1 留后续的 B/C 变体（F8/F9），经 Issue #1 实现规格「Interactive write seams」全部 completed 交付，不再是"留 gate"待办。真实副作用仅在宿主注入对应 facade 时可用，只读宿主仍守 Round-1 契约（POST 404）。

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

- 复用 `ui_matrix.py` 覆盖清单（从 R1 PRD 转录），新增交互项已回填覆盖矩阵（home.scenario-state / home.composer / home.approval-console / task-detail.reconcile）。
- 既有测试：横滚动/reduced-motion（`test_ui_no_horizontal_scroll.py` / `test_ui_style.py`）、Review/safe-stop 态（`test_ui_review.py`）、宿主脱敏/边界（`test_ui_host.py` / `test_ui_redaction_host.py`）。
- **CDP 端到端断言已交付**：`tests/test_ui_interactive_cdp.py`（12 项，真实 headless Chrome 经 loopback 驱动）覆盖 PRD 点名的 composer 发送 / scenario 切换（request_stop / request_approval）/ safe-stop 横幅 / ?variant=B·C，加 F12 approval approve·deny 真实点击，以及只读宿主不暴露任何写触发的不变式。无 Chrome 时按 ADR 0004 自动 skip。
- 可写宿主冒烟测试：`tests/test_ui_dogfood_cli.py`（2 项）起真实 `ui --db` 子进程验证 GET /home 200、composer 触发 live、POST /api/runs 201；并断言 --host 0.0.0.0 被拒（loopback-only）。

## 8. 开放问题

1. 三视图（Issue #1）与 A 会话优先 IA 如何共存——替换还是嵌套？（建议：A 会话流作 home 主区，三视图作 task-detail / record-view 子投影，不替换。）
2. `ui_view_model` 的 DSH 身份投影是否需扩展字段满足 F14「对齐」诉求？（F14 实现时确认。）

## 9. 进一步说明 / 跨文档口径

- **事实源**：交互 / 写入能力的 durable 事实源是 `docs/designs/issue-1-workbench-ui-implementation.md` 的「Interactive write seams (post-Round-1)」小节（四写 seam + 宿主契约）与 ADR 0003（宿主只读边界）；本 PRD 的 §3c 与之对齐，不再另设路线图为事实源。
- **F18 仍为 ⛔ 不做**：证据 live replay 明确排除，未交付也不计划交付。

## 相关设计实体

- [pd-interactive-workbench](../designs/pd-interactive-workbench.md) — IA 决策 D1–D4、dsh-web 对齐边界、跨文档口径
- [pf-workbench-features](../designs/pf-workbench-features.md) — F1–F19 功能目录与分类
- [ep-write-seam-journey](../designs/ep-write-seam-journey.md) — 写 seam → facade → POST 宿主契约旅程
