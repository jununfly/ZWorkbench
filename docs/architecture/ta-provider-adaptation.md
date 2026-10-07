---
doc-kind: architecture-subsystem
authority: primary
authority-id: architecture.subsystem.provider-adaptation
---

# Provider 适配与降级

## Question

ZWorkbench 在单一 Provider 边界内如何实现 capability 路由、failure class 归一、identity↔transport 绑定，以及 fail-closed 的 fallback / 降级，且绝不静默替换 Provider identity？

## Scope

本页覆盖 Provider 适配层的 baseline 能力：单 Provider 下的 capability 路由、failure class 分类、Provider identity 与 transport 的绑定、fallback 目标 + 原因 + 降级模式 + attempt 计账，以及 reason-required / 不静默切换的 fail-closed 语义。多 Provider 路由、真实 Provider 计费、跨 Provider 的 retry 预算不在当前 baseline 内（见 Known gaps / Backlog）。

## Boundaries

- Provider identity 是 owner-backed 的一等身份；任何 fallback / 重试都不得把 identity 静默替换成另一个 Provider（呼应 AGENTS.md 的 Provider identity 不变式）。
- fallback 必须显式携带 target、reason 与 degradation mode；attempt 计账必须可审计。
- baseline 仅含 loopback / fake Provider；真实 Provider 路由与计费属后续受控 gate。
- 未知 failure class、未知 capability、identity 漂移一律 fail-closed。

## Responsibility

Provider adapter 负责：按 capability 选择 transport、把 Provider 侧 failure 归一到 owner 的 failure class、把 Provider identity 绑定到 transport、记录 fallback 的 target/reason/degradation/attempt，并在 reason 缺失或 identity 漂移时拒绝。

## Owned state

adapter 不持有跨 Run canonical state。fallback / attempt 计账由 CompositionOwner 记录（见 Known gaps 中 attempt 计账当前缺口）。

## Interface

`provider_facade.py`、`provider_vocabulary.py` 暴露 capability 路由与 failure class；`codex_adapter.py` 是 baseline 内的具体 Provider 实现（loopback / fake）。fallback 决策点须返回 `(target, reason, degradation_mode)`。

## Failure behavior

reason 缺失 → 拒绝（reason-required）；Provider identity 与请求不一致 → fail-closed；未知 failure class → 归一到 unknown 并 safe-stop 关联 run。

## TARGET / IMPLEMENTED / UNKNOWN 矩阵（执行层基本功能讨论 2026-10-07）

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| capability 路由 + failure class 归一 + identity↔transport 绑定 | IMPLEMENTED | provider_facade / provider_vocabulary |
| fallback 决策（target/reason/degradation + attempt 上下文） | IMPLEMENTED | owner-backed `provider_fallback_ledger`（node 1-1-1） |
| attempt 原始计账（per provider per run，可计数审计） | IMPLEMENTED | owner-backed `provider_attempt_ledger`（node 1-1-2） |
| reason-required + 不静默切换 fail-closed | IMPLEMENTED（deny 已单测 + fixture 回归验证） | `provider_fallback_ledger` reason-required；真实触发面仍待 1-10 真实 gate |
| Run 级 retry 预算 | IMPLEMENTED | CompositionOwner 已有界 |
| Provider 级 retry 预算（上限/约束） | UNKNOWN | 原始 attempt 计账已 owner-backed（1-1-2），但单一 owner 上限/约束仍待 1-1-3 |
| 真实 Provider 路由 / 计费 | 超出 baseline（backlog） | 需独立 gate |

## Known gaps

- ~~fallback 的 attempt 计账只存在于 fixture，未进入 owner~~（已解决，node 1-1-1）：现由 owner-backed `provider_fallback_ledger` 记录 target/reason/degradation/attempt，可跨 Run 审计。
- reason-required 与 no-silent-switch 的 fail-closed 在当前 baseline 下是真空真的（没有第二个真实 Provider 可 fallback 到），端到端未被真实触发验证。
- Provider 级 retry 预算没有单一 owner 与上限，与 DSH/Worker retry 一样属于「跨层 retry 无单一 owner 记账」的 UNKNOWN 面。

## Backlog（实现前须登记，不阻塞本结论）

1. P0 fallback 审计硬化（<1.5 人日）：把 fixture 中的 fallback target/reason/degradation/attempt 计账落为 owner-backed，并加回归测试证明 reason 缺失即拒绝。
2. ~~P1 在 owner 中记录 attempt 计账（扩展 provider_exit_ledger 或新增 retry_budget_ledger）~~（已解决，node 1-1-2）：现由 owner-backed `provider_attempt_ledger` 记录每次尝试的终态（failed/succeeded），可按 provider/run 计数审计，供 1-1-3 的 Provider 级预算引用。
3. P1 Provider 级 retry 预算表（~2.5 人日）：声明 owner + 上限 + 每次跨 Provider retry 的 attempt/failure_class/target/reason。
4. P1 真实 Provider gate 收口（~2 人日）：把真实路由 / 计费接入受控 gate，明确与 loopback/fake baseline 的边界。

## Source map

- `../../src/zworkbench/provider_facade.py`
- `../../src/zworkbench/provider_vocabulary.py`
- `../../src/zworkbench/codex_adapter.py`
- `../../tests/test_provider_facade.py`
- `../../tests/test_provider_vocabulary.py`
- `../../tests/test_provider_exit_receipt.py`
- `../../tests/test_w8_remote_provider_failover.py`
- `../../tests/test_optional_provider_probe.py`
- `../../tests/test_w8_capability_broker.py`
- `../../tests/test_real_codex_provider_staging.py`
- `../zj-adr/0008-host-enforcement-is-fail-closed-and-testable.md`

## Related authority

- [系统概览](ta-overview.md)
- [分层与依赖](ta-layers.md)
- [CompositionOwner](ta-composition-owner.md)
- [本地只读运行流](ta-local-read-only-flow.md)
- [执行层 effect 授权](ta-execution-effect-authorization.md)
- [证据与回放](ta-evidence-replay.md)
