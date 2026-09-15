---
doc-kind: architecture-subsystem
authority: primary
authority-id: architecture.subsystem.composition-owner
---

# CompositionOwner

## Question

哪个组件持有跨 Run 的事实、审批和副作用状态，并如何避免未知状态被误判为成功？

## Scope

CompositionOwner 是本地 SQLite-backed durable owner。它记录 run、attempt、event、effect、
result、approval、replay metadata、backup/restore 与 safe-stop；它不执行模型、shell、Provider
或 replay。

## Boundaries

- 所有可能产生副作用的动作经过 `request → policy → decision → claim → execute → complete/reconcile`。
- `read-only` 和 `idempotent` 是已知 class；未知 effect class、资源或审批结果直接 deny/safe-stop。
- approval 必须精确绑定 operation、action、resource、idempotency key，并只保存 token hash。
- `complete_run` 拒绝仍有未决 effect 的 run；不确定外部结果先 reconcile，不能把“未观察到”
  当成“未发生”。

## Responsibility

Owner 创建和推进 run，关联 parent/child identity，记录事件和结果，裁决 approval/effect，
处理 uncertain/reconcile，提供 recorded state view、state digest、export、backup 和 restore。

## Owned state

唯一 canonical state 包括 run、attempt、event、effect、result、approval、replay metadata、
backup/restore receipt 和 safe-stop 状态。DSH session、plugin state、Codex rollout、Provider
router state 和观测投影都只能通过 identity 作为输入或 evidence。

## Interface

当前接口包括 `create_run`、`start_run`、`complete_run`、`fail_run`、`safe_stop_run`、
`request_approval`、`approve`、`deny_approval`、`claim_effect`、`complete_effect`、
`mark_effect_uncertain`、`reconcile_effect`、`record_replay_metadata`、`events`、`snapshot`、
`state_digest`、`export_state`、`backup` 和 `restore`。

## Failure behavior

已完成的 operation/idempotency key 返回 `already_completed`，不产生第二次物理副作用。
`not-applied` 只允许 owner 预算内的有界重试；`applied` 记为完成；`unknown` safe-stop。
restore 默认拒绝覆盖已有目标，必须显式 replace；关键 identity 或 schema 不完整时保留
`unknown`，不得完成 run。

## Source map

- `../../src/zworkbench/composition.py`
- `../../src/zworkbench/composition_cli.py`
- `../../src/zworkbench/codex_adapter.py`
- `../../src/zworkbench/replay.py`
- `../../tests/test_composition.py`
- `../../tests/test_replay.py`
- `../../tests/test_codex_adapter.py`
- `../../evaluation/fixtures/w8_evidence_replay/v1/README.md`
- `../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md`

## Related authority

- [系统概览](ta-overview.md)
- [分层与依赖](ta-layers.md)
- [Codex Worker bridge](ta-codex-worker-bridge.md)
- [本地只读运行流](ta-local-read-only-flow.md)
