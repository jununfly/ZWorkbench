---
doc-kind: product-requirements
source: https://github.com/jununfly/ZWorkbench/issues/1
source-id: github-issue-1
status: target
---

# Issue #1：Owner-backed Workbench UI and capability integration

> 来源：[GitHub Issue #1](https://github.com/jununfly/ZWorkbench/issues/1)。本文保存该 Issue 的 R1 spec；它描述目标与验收合同，不证明能力已实现。

## Problem

当前只能通过受控 CLI、owner snapshot 和分散运行产物理解工作状态，缺少一个能恢复上下文、呈现运行事实、证据和下一步的本地优先工作台。UI 不得把 DSH/Codex/Provider session 变成第二个 durable owner，也不得伪造 approval、写入、Provider 切换或 live replay。

## Target outcome

R1 的界面协作定位需求见补充规格：[界面引用注册表与本地评审标注模式](r1-ui-reference-registry.md)。采用代码生成的 UI Reference Manifest，不维护 docs 元素映射表。

交付三个协作视图：会话优先的工作台首页、以 `intent → preflight → run / child run → result | failed | safe-stopped` 为中心的任务详情，以及只读 recorded view。所有 UI 读写通过 Workbench Control Plane façade；它投影脱敏 Owner 数据并把允许的动作交回既有 owner policy/effect 流程。

## Required boundaries

- `CompositionOwner` 是唯一 durable source of truth；UI、DSH、Codex、Provider 和前端缓存不能生成 canonical state。
- 未知 identity、effect、权限、Provider、workspace 或外部结果必须显示 `unknown` / `safe-stopped`，不得推断成功或自动 retry。
- 副作用遵循 `request → policy → decision → claim → execute → complete/reconcile`；未知类别默认 deny。
- 初始能力限于 case-local `local_read_only_run`、只读搜索/筛选、recorded view、sealed simulated replay、export、backup 和显式确认的 restore 准备。
- live replay、真实 Provider、主工作区写入、apply diff、Git push、部署、Webhook 和不可逆操作默认不可用。
- 不在浏览器持久化 owner snapshot、prompt、凭证、approval token 或 event payload。

## State and presentation

支持 `draft → preflight(pass|deny) → created → running → completed|failed|safe-stopped|recovering`；缺少必要身份或 evidence 时为 `unknown`。状态必须有文本、来源和非颜色线索。draft 没有 `run_id`，不得伪装为可恢复 Run。

## Acceptance

Control Plane façade、UI 集成、脱敏/来源合同、命令语义、replay 隔离、生命周期、artifact/backup/restore、可访问性和响应式布局均需有可重复验证。验收需覆盖空、加载、拒绝、失败、safe-stop、unknown、缺失 identity、effect reconcile、approval-required 和 replay provenance 失败路径。

DSH/Worker/Provider/schema/policy/fixture 变化后须重跑受影响验证；证据区分 `native`、`plugin-composed`、`outer-composed`、`owner-backed`，并固定版本、digest、environment、policy、workspace、owner schema 与 cassette identity。关键结论为 unknown 时保持 `HOLD`，记录下一证据、owner 和回滚路径。

## Out of scope

替换 CompositionOwner、浏览器 durable state、新 in-browser agent loop、隐式 scheduler、真实凭证和远端账户生命周期、多用户协作、云同步、移动原生应用及无关的视觉分析。
