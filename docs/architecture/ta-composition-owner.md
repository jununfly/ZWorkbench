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

## 执行层基本功能讨论结论（2026-10-07）

> 以下为 zj-discuss「执行层应实现哪些基本功能」讨论的耐久沉淀（sub-01 Run 生命周期编排、sub-03 唯一 owner 持久化与恢复）。过程讨论稿已删除，本段为唯一权威结论。

### sub-01：Run 生命周期编排

- **Run 七态状态机（created/running/waiting_approval/recovering/completed/failed/safe_stopped）+ 5 转换 + begin_recovery 已由 CompositionOwner 实现并锁死 allowed 转换表**，且 `create/start/complete/fail/safe_stop/begin_recovery` 是 DSH/Worker 必须调用的唯一控制面（IMPLEMENTED）。
- **effect 级 retry 预算由 owner 唯一拥有、默认 `max_attempts=2`、耗尽即 safe_stop（reason=retry_budget_exhausted）**（IMPLEMENTED，可证）。
- **缺口（UNKNOWN / backlog）：**
  - `complete_run` 当前只拒绝「未决 effect」；「未决 approval」与「关键 identity 缺失」两条拒绝路径缺位（P0，无 schema 变更；须在 `complete_run` 内调 `detect_identity_violations` 并查 `approvals` pending）。
  - run 级 restart 预算缺位，跨层（DSH/Worker/Provider）retry 无单一 owner 计账（UNKNOWN）。
  - caller-auth 缺口（`ZW_OWNER_SANDBOX=1` 弱化 fail-closed）属真实架构前硬前置，须登记 backlog。
- **控制面归属钉死**：run 生命周期方法是唯一状态机入口，DSH/Worker 不得自管第二套状态机（对应 ta-overview 的 Control Plane 责任）。

### sub-03：唯一 owner 持久化与恢复

- **9 张 canonical 表、harness-neutral、幂等（`already_completed` + `physical_effect_count` 单点守卫 + 并发 `in_flight` 兜底）、uncertain→reconcile→unknown 三态 fail-closed、backup/restore 四重交叉校验 + 默认拒绝覆盖 + approval 仅存 token_hash**（IMPLEMENTED，基本可证）。
- **缺口（UNKNOWN / backlog）：**
  - Q4「secret 不入 owner」当前**不成立**——`_reject_raw_credentials` 仅键名启发式，`complete_effect` 写 `external_receipt_json` 不经拒密，值级密钥可直落 owner 并被整库备份扩散（P0 backlog：external_receipt 必经拒密 + 值级扫描）。
  - run 级 attempt 非一等实体（仅 effect_attempts），须决策（P1）。
  - 「无第二 canonical」靠纪律而非技术护栏，须升为可审计契约（P1：`audit_owner_isolated()` + CI 断言）。
  - unknown 术语须拆两层（远端/委托侧存字面 unknown；内部 identity 缺失 safe-stop 不存值）。
- **sub-03 是 sub-04（effect 授权）与 sub-06（证据/回放）的硬前置**，须先稳定。

### 交叉引用

- [执行层 effect 授权](ta-execution-effect-authorization.md)
- [证据与回放](ta-evidence-replay.md)
- [Provider 适配与降级](ta-provider-adaptation.md)
- [终止与资源生命周期](ta-termination-resource-lifecycle.md)
