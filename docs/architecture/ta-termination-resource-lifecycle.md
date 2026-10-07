---
doc-kind: architecture-subsystem
authority: primary
authority-id: architecture.subsystem.termination-resource-lifecycle
---

# 终止与资源生命周期

## Question

ZWorkbench 如何保证 parent 停止向完整进程树传播、无孤儿 Worker、本地退出不等于 Provider 侧退出账本、以及所有外部资源在 run 终止时被拆除？

## Scope

本页覆盖 run 终止时的进程树清理（Worker 进程组 kill + 孤儿核对）、本地退出账本与 Provider 侧退出账本的分离（unknown / delegated 口径）、资源拆除，以及 SIGTERM→SIGKILL→UNKNOWN 的升级语义。DSH adapter 对称记账、setsid 逃逸、ledger 混合编排接线、≤3 常驻服务的运行时强制、fail-stop 升级契约均不在当前 baseline 内（见 Known gaps）。

## Boundaries

- parent 停止必须传播到完整进程树；不允许孤儿 Worker 残留。
- 本地退出 ≠ Provider 侧退出；两边必须各自记账，unknown / delegated 口径明确。
- 外部资源在 run 终止时拆除；但常驻服务数量受运行时约束（当前无强制）。
- SIGTERM 超时须升级 SIGKILL；再不可处理才标 UNKNOWN，不得降级为成功。

## Responsibility

终止路径负责：向 Worker 进程组发 killpg、核对孤儿进程、分别记录本地与 Provider 侧退出账本、拆除外部资源、按 SIGTERM→SIGKILL→UNKNOWN 升级。

## Owned state

退出账本（本地 / Provider 侧）由 CompositionOwner 记录（provider_exit_ledger）。进程树与资源状态是宿主/Worker 侧的运行时事实，只能作为 evidence。

## Interface

`worker_bridge.py` / `subprocess_supervisor.py` 暴露进程组 kill 与 exit receipt；`composition.py` 的 `record_provider_exit_ledger` 记录 unknown / delegated 口径；`safe_stop_run` / `fail_run` 是终止入口。

## Failure behavior

进程组 kill 失败、孤儿残留、账本缺失、资源未拆除 → 记 unknown / safe-stop，绝不标成功。SIGTERM 超时升级 SIGKILL；仍不可处理 → UNKNOWN。

## TARGET / IMPLEMENTED / UNKNOWN 矩阵（执行层基本功能讨论 2026-10-07）

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| Q1 Worker 进程组 killpg + 孤儿核对 | IMPLEMENTED（Worker 侧） | worker_bridge / subprocess_supervisor |
| Q1 DSH adapter 缺 `process_group_clean` / `orphan` 字段；setsid 逃逸 | UNKNOWN | adapter 无对称记账字段 |
| Q2 本地 vs Provider 退出账本分离、unknown/delegated 口径 | IMPLEMENTED | composition.py provider_exit_ledger |
| Q2 调用点配对（谁在何时记哪边） | UNKNOWN | 编排层未把两端账本对称接线 |
| Q3 资源拆除 | IMPLEMENTED | worker_bridge / subprocess_supervisor |
| Q3 ≤3 常驻服务运行时强制 | UNKNOWN | 无运行时 registry 强制 |
| Q4 SIGTERM→SIGKILL→UNKNOWN 升级 | IMPLEMENTED（fail-closed） | subprocess_supervisor |
| Q4 无 fail-stop 升级契约 | UNKNOWN | 无契约把「不可处理」升级为 fail-stop |

## Known gaps

- DSH adapter 没有 `process_group_clean` / `orphan` 字段，setsid 创建的子进程可能逃逸出 killpg 范围（UNKNOWN）。
- 本地与 Provider 侧退出账本虽分离，但调用点配对未定义——哪条终止路径记哪边账本不清楚（UNKNOWN）。
- 资源拆除已实现，但没有「≤3 常驻服务」的运行时强制（无 registry），只能靠约定。
- SIGTERM→SIGKILL→UNKNOWN 升级已实现 fail-closed，但没有把「不可处理」升级为 fail-stop 的契约（UNKNOWN）。

## Backlog（实现前须登记，不阻塞本结论）

1. P1 DSH adapter 增 `process_group_clean` / `orphan` 字段并验证 setsid 子进程不被误报为 0。
2. P1 在编排层对称接线两端退出账本（调用点配对）。
3. P1 引入常驻服务运行时 registry，强制 ≤3 上限。
4. P1 定义 fail-stop 升级契约（不可处理 → fail-stop，而非 silent unknown）。

## Source map

- `../../src/zworkbench/worker_bridge.py`
- `../../src/zworkbench/subprocess_supervisor.py`
- `../../src/zworkbench/composition.py`
- `../../tests/test_worker_lifecycle.py`
- `../../tests/test_w8_worker_lifecycle.py`
- `../../tests/test_worker_bridge.py`
- `../../tests/test_worker_contract.py`
- `../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md`

## Related authority

- [系统概览](ta-overview.md)
- [Codex Worker bridge](ta-codex-worker-bridge.md)
- [CompositionOwner](ta-composition-owner.md)
- [证据与回放](ta-evidence-replay.md)
- [Provider 适配与降级](ta-provider-adaptation.md)
