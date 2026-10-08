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
  - run 级 attempt 非一等实体（仅 effect_attempts）：**已决策（1-6-2）不升一等实体**——runs 表无 attempt 列，run 级 retry 由 effect_attempts 间接表达（一次 run 重试 = 重新 claim effect，attempt 自增）。owner 不持有 run 级 attempt 一等实体表。run 级 restart 预算仍是 sub-01 backlog（line 81）的独立 UNKNOWN 项。
  - 「无第二 canonical」已升为可审计契约（**1-6-3**）：`audit_owner_isolated()` 枚举 owner 持有的全部用户表，断言恰为 14 张 canonical 表（`_CANONICAL_TABLES`），任何额外用户表即判为第二 canonical state 并 fail；该审计测试即 CI 断言载体（仓库暂无 CI yaml，测试套件为契约执行点）。
  - unknown 术语已拆两层（**1-6-4**）：① 远端/委托侧（remote/delegated，如 provider/endpoint/account_scope、`provider_remote_zero_residue`）缺失→存字面 `unknown`（或 `unknown/delegated` caliber），表达"远端状态未知"；② 内部 identity（owner 的 durable 身份图交叉引用）缺失→**不**存字面 `unknown` 值，而是 `safe_stop_run(reason="identity_unresolved")`（F13 已实现并测试）。两层已分离且行为正确，本节点将其固化为术语约定 + 聚焦测试。
- **sub-03 是 sub-04（effect 授权）与 sub-06（证据/回放）的硬前置**，须先稳定。

### 交叉引用

- [执行层 effect 授权](ta-execution-effect-authorization.md)
- [证据与回放](ta-evidence-replay.md)
- [Provider 适配与降级](ta-provider-adaptation.md)
- [终止与资源生命周期](ta-termination-resource-lifecycle.md)
