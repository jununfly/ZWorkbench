---
doc-kind: design
authority: supporting
axis: product-design
status: implemented
implementation-status: implemented
source: ../prds/workbench-ui-interactive.md
source-id: prd-workbench-ui-interactive
authority-id: design.interactive-workbench
---

# 产品设计：可交互完整工作台 Web-UI

本页是「完整工作台 Web-UI（含交互）」的**产品设计实体**，沉淀已拍板的 IA/交互深度/宿主边界决策。

## Question

如何把 Issue #1 已交付的只读三视图切片推进为可交互的完整工作台主界面，同时不引入第二份 canonical state 或 dsh-web 运行时依赖？

## Scope

- **IA 方向**：A 会话优先（工作记录即对话流），复用现有三视图内容；B 画布 / C 日记留后续独立 gate。
- **交互深度**：纯 UI 壳 + 只读投影 + disabled/stopped 态；真实写入/审批/reconcile 仅当宿主注入对应 facade 时可用（否则 POST 404）。
- **三变体切换器**：保留为开发期调试工具（`?variant=A/B/C`），纯 client 端 query 分支，不接入 `ui_build` 生产构建管线。
- **宿主边界**：server-rendered HTML over loopback（ADR 0003/0006 单构建身份）；dsh-web 仅作外部能力参考，只复用最小只读 surface，绝不整包吸纳（ADR 0007）。

## Boundaries（不覆盖）

- 不重建 Issue #1 已实现模块（`ui_style` / 三视图 server-render / Host Capability Facade / review 骨架 / ui_ref 管线）。
- 真实写入能力的事实源是 issue-1 实现规格「Interactive write seams」小节与 ADR 0003，本页不另设路线图为事实源。
- F18 证据 live replay 明确 ⛔ 不做（ADR 0004）。

## Design decisions（durable）

- **D1 — IA 方向**：✅ A 会话优先；B/C 留后续 gate。
- **D2 — 交互深度**：✅ 本轮只交付纯 UI 壳 + 只读投影 + disabled/stopped 态；F6/F12 触碰 Run/Approval/Effect 转后续 product scope gate。
- **D3 — 三变体切换器**：✅ 保留为开发期调试工具，不向最终用户暴露。
- **D4 — 交互深度 gate 已开并交付**：✅ D2 原留 gate（F6/F12 product scope、F7-live/F10-exec/F13-logic 🚧）与 D1 留后 B/C 变体（F8/F9），经交互路线图 1-2 / 1-3 全部 completed。真实副作用仅在宿主注入对应 facade 时暴露；只读宿主仍守 Round-1 契约（POST 404）。

## Status

IMPLEMENTED — 交互写 seam 经 CDP 端到端 `tests/test_ui_interactive_cdp.py`（12 项）与可写宿主冒烟 `tests/test_ui_dogfood_cli.py` 验证通过；只读宿主不暴露任何写触发。

## Source map

- `../prds/workbench-ui-interactive.md` §1 意图与边界、§4 决策(D1–D4)、§5 dsh-web 对齐、§9 跨文档口径。
- 写 seam 事实源：[issue-1-workbench-ui-implementation](issue-1-workbench-ui-implementation.md)「Interactive write seams」小节。

## Related authority

- [Issue #1 实现规格](issue-1-workbench-ui-implementation.md)
- [宿主只读边界 ADR](../zj-adr/0003-workbench-host-is-server-rendered-html-over-loopback.md)
- [dsh-web 外部参考 ADR](../zj-adr/0007-dsh-web-treated-as-external-capability-reference.md)
- 体验路径见 [ep-write-seam-journey](ep-write-seam-journey.md)；功能目录见 [pf-workbench-features](pf-workbench-features.md)
