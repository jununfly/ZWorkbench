---
doc-kind: design
authority: supporting
axis: product-feature
status: implemented
implementation-status: implemented
source: ../prds/workbench-ui-interactive.md
source-id: prd-workbench-ui-interactive
authority-id: design.workbench-features
---

# 产品功能：完整工作台功能目录（F1–F19）

本页是 workbench-ui-interactive §3 的**产品功能实体**，沉淀可交互完整工作台暴露的原子功能清单（F1–F19）及其交付状态。

## Question

完整工作台 Web-UI 对外暴露哪些原子功能？各自交付状态与依赖边界是什么？

## Scope（功能目录）

| ID | 功能 | 状态 | 依据 / 说明 |
|---|---|---|---|
| F1 | IA 方向（A 会话优先 / B 画布 / C 日记） | ✅ A 已决 | D1 拍板先 A；B/C 转后续 gate |
| F2 | 顶栏 shell（brand/crumb/tags/pills） | 🔨 构建 | 原型 token 对齐 `ui_style` |
| F3 | 侧栏工作记录导航 | 🔨 构建（A） | 纯导航壳，数据来自 owner-backed 投影 |
| F4 | 会话消息流（message/avatar/meta/plan-card） | 🔨 构建（A） | 只读渲染既有工作记录 |
| F5 | 计划卡（working plan 步骤态） | 🔨 构建 | 投影驱动 |
| F6 | composer 由只读 → 真实发送 | ✅ 已交付 | Issue #1 实现规格「Interactive write seams」；POST /api/runs 真实建 Run（ADR 0003） |
| F7 | 运行事实检查器 | ✅ 已交付 | 渲染壳 + 实时值（每次轮询经 resolve_view 重投影，只读无副作用） |
| F8 | 命令画布（?variant=B） | ✅ 已交付 | canvas 变体布局（?variant=B） |
| F9 | 项目日记（?variant=C） | ✅ 已交付 | journal 变体布局（?variant=C） |
| F10 | 运行轨道栏（含可执行 Run） | ✅ 已交付 | 渲染壳 + 可执行 Run（宿主注入 command facade） |
| F11 | 场景状态机 UI（empty/planning/approval/stopped） | ✅ 已交付 | 四态渲染 + 真实控制（宿主注入 scenario facade → POST /api/scenario-state） |
| F12 | 审批执行 UI（apply/Approval/retry/effect receipt） | ✅ 已交付 | POST /api/approvals；deny 强制非空理由（宿主注入 approval facade，ADR 0003） |
| F13 | 安全停止 / reconcile UI | ✅ 已交付 | 横幅/stopped + 越界判定 + reconcile 路由（宿主注入 reconcile facade → POST /api/reconcile 触发 owner.reconcile_identity） |
| F14 | DSH 对齐只读 surface（`/session-references`） | ✅ 部分已落地 | Host Capability Facade + DSH 身份投影，不引运行时 |
| F15 | r2-ui-reference-skills 协同 UI | 🔨 构建 | 把 skills 状态检查可视化（F15） |
| F16 | 响应式 & 降级（≤760px / reduced-motion） | ✅ 已落地 | Issue #1 已覆盖 |
| F17 | 本地运行/调试接入（loopback + CDP harness） | ✅ 已落地 | 仅扩展新交互测试 |
| F18 | 证据 live replay | ⛔ 不做 | 原型 "no live replay"；记录视图是只读投影，不可伪装确定性回放（ADR 0004） |
| F19 | 三变体调试切换器（`?variant=A/B/C`） | 🔨 开发期工具 | D3 保留为开发期工具，纯 client 端 query 分支，不接入 `ui_build` |

## 写 seam 不变式

所有真实写入 / 审批 / reconcile 仅在宿主注入对应 facade 时暴露；只读宿主（CLI `ui-host`）disabled 占位 + POST 404（见 [ep-write-seam-journey](ep-write-seam-journey.md)）。

## Status

IMPLEMENTED（除 F18 ⛔ 不做；F2/F3/F4/F5/F15/F19 为构建/开发期工具态）。F1–F13 除 F18 外均已交付（review_note 2026-09-27 确认）。

## Source map

- `../prds/workbench-ui-interactive.md` §3 原子化 Features 清单、§3b Round 1 范围、§3c 已交付写 seam、§4 决策(D1–D4)。

## Related authority

- 产品设计：[pd-interactive-workbench](pd-interactive-workbench.md)
- 体验路径：[ep-write-seam-journey](ep-write-seam-journey.md)
- 真实能力事实源：[Issue #1 实现规格](issue-1-workbench-ui-implementation.md)「Interactive write seams」
