---
doc-kind: design
authority: supporting
axis: experience-path
status: implemented
implementation-status: implemented
source: ../prds/workbench-ui-interactive.md
source-id: prd-workbench-ui-interactive
authority-id: design.write-seam-journey
---

# 体验路径：交互写 seam 旅程（UI → 真实写入/审批/reconcile）

本页是 workbench-ui-interactive §3c 的**体验路径实体**，描述用户经 UI 完成真实副作用的闭环。

## Question

用户如何经工作台 UI 发起真实写入 / 审批 / reconcile，同时保证只读宿主绝不暴露任何写触发？

## Scope（写 seam 步骤）

不变式（沿用 Round-1 + ADR 0003）：**所有真实写入 / 审批 / reconcile 仅在宿主注入对应 facade 时暴露**；只读宿主（CLI `ui-host`）一律 disabled 占位 + POST 404。

| 能力 | 路线图节点 | 宿主契约（facade 注入） |
|---|---|---|
| F6 composer 真实发送 / F10 可执行 Run | 1-2-1 / 1-2-4 | 宿主注入 command facade → POST `/api/runs` 真实建 Run；无 facade 则 404 |
| F11 场景真实控制 | 1-2-7 | 宿主注入 scenario facade → POST `/api/scenario-state`（`request_stop` / `request_approval`）；无 facade 则 404 |
| F12 审批执行 | 1-2-2 | 宿主注入 approval facade → POST `/api/approvals`（`approve` / `deny`）；`deny` 强制非空理由；无 facade 则 404 |
| F13 越界判定 + reconcile | 1-2-5 / 1-2-8 | 宿主注入 reconcile facade → POST `/api/reconcile` 触发 `owner.reconcile_identity`；无 facade 则 404 |
| F7 实时值 | 1-2-3 / 1-2-6 | 每次轮询经 `resolve_view` 重投影，只读无副作用 |

## 验收

- CDP 端到端 `tests/test_ui_interactive_cdp.py`（12 项，真实 headless Chrome 经 loopback 驱动）覆盖 composer 发送 / scenario 切换（`request_stop` / `request_approval`）/ safe-stop 横幅 / `?variant=B·C`，加 F12 approval `approve`·`deny` 真实点击，以及**只读宿主不暴露任何写触发**的不变式。无 Chrome 时按 ADR 0004 自动 skip。
- 可写宿主冒烟 `tests/test_ui_dogfood_cli.py`（2 项）：起真实 `ui --db` 子进程验证 GET /home 200、composer 触发 live、POST /api/runs 201；并断言 `--host 0.0.0.0` 被拒（loopback-only）。

## Boundaries

- 写 seam 的 receipt / approval 数据模型不得引入第二个 durable owner（ADR 0001 不变量）。
- `ui --db` 为 dogfood 可写宿主，接真实 CompositionOwner + 四 facade；`ui-host` 为只读宿主，永不变为可写。

## Status

IMPLEMENTED — 交互写 seam 经 CDP 与可写宿主冒烟验证通过。

## Source map

- `../prds/workbench-ui-interactive.md` §3c 越过 Round-1 的已交付项、§7 验收方式。

## Related authority

- 产品设计：[pd-interactive-workbench](pd-interactive-workbench.md)
- 功能目录：[pf-workbench-features](pf-workbench-features.md)
- [Issue #1 实现规格](issue-1-workbench-ui-implementation.md)「Interactive write seams」小节
- [唯一 durable owner ADR](../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md)
