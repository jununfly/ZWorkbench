---
doc-kind: architecture-cross-cutting
authority: primary
authority-id: architecture.cross-cutting.execution-effect-authorization
---

# 执行层 effect 授权管线

## Question

ZWorkbench 的 baseline 内，哪些 effect 集合是允许的、它们如何经 request→policy→decision→claim→execute→complete/reconcile 六段式管线授权，以及越界 effect 如何 fail-closed？

## Scope

本页覆盖 baseline effect 集合决策、六段式授权管线、approval 绑定粒度与重签语义、S2 可恢复写入的消费边界，以及 owner 级 deny 的边界分层（owner 强制类 vs preflight 类）。真实 Provider 路由 / 真实主工作区写入 / Git push / deploy / Webhook / live replay 属后续受控 gate（S4+），非永久禁止。

## Boundaries

- baseline effect 集合 = {read-only（采用 (a) preflight 准入即授权、不进 claim seam；二选一中的 (b) read-only effect class 路径未采用）、loopback / fake Provider 调用、S2 可恢复写入（approval-required，case-local，单一 owner commit，不 push）}。read-only 的授权由 `LocalReadOnlyRunOrchestrator.preflight` 静态准入承载，**不调用 `CompositionOwner.claim_effect`、不创建 claimed effect 行**：admission 即授权，无外部副作用，故无需六段式 claim 记账。
- 未知 effect class / token / scope 不匹配由 owner 强制 safe-stop（已落）。
- 越界 workspace / 未声明网络·凭证·子进程由 owner 级 safe-stop 强制（Q4 preflight 类，已在 1-4-1 落地：`CompositionOwner.declared_exposure` 表记录 per-run `declared_side_effects` / `exposure`，`claim_effect` 在声明存在时强制边界，缺失声明走既有行为）。
- 重复请求幂等由 owner 层强保证；approval token 仅存 hash。

## Responsibility

授权管线负责：把每个 effect 请求经六段式裁决、把 approval 精确绑定到四元组、在 owner 层强制未知/越界 safe-stop，并把 S2 写入收敛到单一 owner commit。

## Owned state

effect / approval / claim / reconcile 状态由 CompositionOwner 记录。declared_side_effects / exposure 由 `declared_exposure` 表（per-run）记录，经 `claim_effect` 的 Q4 preflight 校验强制（见 Backlog #1）。

## Interface

- effect 类 → 入口方法 → 出口动作 → 信任边界 映射表（见下方）。
- `request_approval` / `approve` / `deny_approval` / `claim_effect` / `complete_effect` / `mark_effect_uncertain` / `reconcile_effect`。
- policy 阶段当前内联于 `claim_effect`，须抽为显式 `evaluate_policy(effect_request, context) -> (allow, reason)`。

## Failure behavior

未知 effect class / token / scope → safe-stop；越界 workspace / 未声明网络·凭证·子进程 → safe-stop（owner 级 deny 已落地，见 Backlog #1）；approval 不匹配 → deny；重复请求 → already_completed，无第二次物理副作用。

## baseline effect 清单 + gate 映射

| effect 类 | 入口 | 出口动作 | 信任边界 |
| --- | --- | --- | --- |
| read-only | (a) preflight 准入即授权 | 不进 claim seam / 不创建 claimed effect 行 | 只读，无外部副作用；authorization 由 local_run.preflight 静态准入承载，非 claim_effect 六段式 |
| loopback / fake Provider 调用 | claim_effect | adapter 执行 | 仅回环 / fake，无真实外部 |
| S2 可恢复写入 | claim_effect（approval-required） | 单一 owner commit，不 push | case-local worktree，用户手动 merge 回主仓库 |

## 六段式管线 + Q4 deny 边界分层

1. request → 声明 operation/action/resource/idempotency_key。
2. policy → `evaluate_policy()` 返回 (allow, reason)；owner 强制类（未知 class/token/scope）在此拒绝。
3. decision → approval 精确绑定四元组，token 一次性、hash-only、不可续期/不可重签（重签=新建 request）。
4. claim → owner 记账，幂等守卫。
5. execute → 在信任边界内执行（loopback/fake/case-local）。
6. complete / reconcile → uncertain→reconcile→unknown fail-closed。

Q4 deny 分层：
- **owner 强制类（已实现）**：未知 effect class / token / scope 不匹配 / approval 不匹配 → safe-stop。
- **preflight 类（须进 backlog）**：越界 workspace、未声明网络·凭证·子进程 → 功能已决策必须 deny，但 owner 级缺 `declared_side_effects` / `exposure` 形参，0% 可强制，须加 schema 字段。

## 产品语义落文（solo 场景）

- S2 消费边界：commit 后由用户在隔离 worktree 内 review，merge 回主仓库为显式、用户手动触发，不属本管线。
- solo 场景 approver = 同一本地操作者 CLI 显式同意。

## Backlog（实现前须登记，不阻塞本结论）

1. ~~owner schema 增 `declared_side_effects` / `exposure` 字段 + deny 逻辑（Q4 preflight 类）。~~ **已落文（1-4-1）**：新增 `declared_exposure` 表（per-run，`declared_side_effects_json` + `exposure_json{workspace_root,network,credentials,subprocess}`）+ `CompositionOwner.declare_exposure` / `get_declared_exposure`；`claim_effect` 加 `required_exposure` 形参，在声明存在时 safe-stop 拦截四类越界（`side_effect_not_declared` / `workspace_out_of_bounds` / `exposure_not_declared`）；声明缺失走既有行为（按需校验、向后兼容）。write_seam.apply_diff 在 claim 前声明 workspace=case_root、required_exposure={workspace}。由 `tests/test_composition.py::DeclaredExposureTests` 证明四因可强制。
2. `create_worktree` case-local 校验；`apply_diff` 加 `resource == worktree_path` 断言 + repo 指纹校验。
3. `complete_run` 在 read-only 路径 `finally` 显式调用，统一 run 闭合锚点。
4. ~~read-only 二选一（建议 (a) preflight 准入即授权、不进 claim seam）写入 doc + 补测试。~~ **已落文（1-4-4）**：采用 (a) preflight 准入即授权、不进 claim seam；二选一中的 (b) read-only effect class 路径未采用。local_run 的 read-only run 不调用 `claim_effect`、不创建 claimed effect 行（由 `tests/test_local_run_orchestration.py::test_read_only_run_does_not_create_claimed_effect_rows` 证明：completed run 与 denied preflight 均零 `effects` 行）。

## Source map

- `../../src/zworkbench/composition.py`
- `../../src/zworkbench/codex_adapter.py`
- `../../src/zworkbench/write_seam.py`
- `../../src/zworkbench/write_run.py`
- `../../tests/test_composition.py`
- `../../tests/test_write_seam.py`
- `../../tests/test_write_run.py`
- `../zj-adr/0008-host-enforcement-is-fail-closed-and-testable.md`
- `../zj-adr/0009-v1-codex-only-fallback-and-write-boundary-sequencing.md`

## Related authority

- [系统概览](ta-overview.md)
- [CompositionOwner](ta-composition-owner.md)
- [可恢复写入边界](ta-reversible-write-boundary.md)
- [Provider 适配与降级](ta-provider-adaptation.md)
- [本地只读运行流](ta-local-read-only-flow.md)
