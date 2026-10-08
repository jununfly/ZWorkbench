---
doc-kind: architecture-subsystem
authority: primary
authority-id: architecture.subsystem.evidence-replay
---

# 证据与回放（Evidence / Replay）

## Question

ZWorkbench 如何在不引入第二份 canonical state 的前提下，保证 recorded / simulated / live 三模式隔离、provenance 绑定与 live replay 默认拒绝，使 replay 是 owner-backed 的只读消费而非新的写入面？

## Scope

本页覆盖 replay.py 的三模式隔离、provenance 11-identity 绑定、field-level unknown、live replay 默认拒绝与零外部执行计账、以及 evidence 来源分类（native / plugin-composed / outer-composed）。replay 是只读消费，与 sub-03（owner 持久化）和 sub-04（effect 授权）正交：它依赖 sub-03 的 `replays` 表，但不产生新的 durable 副作用。

## Boundaries

- replay 不得创建第二份跨 Run canonical state；所有 replay 结果必须回溯到 CompositionOwner 记录的事实。
- recorded / simulated / live 三模式必须隔离；live 模式默认拒绝任何外部执行。
- provenance 必须绑定到 owner 的 identity 链；字段缺失记为 unknown，不猜测填值。
- unknown / safe-stop 不被 replay 重新解释为成功。

## Responsibility

replay 模块负责：按模式选择 replay 入口、绑定 provenance、对 live 模式默认拒绝外部执行、对 evidence 来源分类，并把 replay 结果作为 owner-backed 的只读视图返回。

## Owned state

replay 不持有 canonical state；它消费 owner 记录的事实并产出只读视图。replay metadata 由 CompositionOwner 记录。

## Interface

`replay.py` 暴露 `recorded_results` / `simulated_results` / `live_results`（三个独立方法），`_base_result` 硬编码为零值基线；Worker 侧 `replay_mode != normal` 作为次级阻断。provenance 绑定到 11 段 identity。

## Failure behavior

live 模式触发外部执行 → 默认拒绝（fail-closed）；provenance 不完整 → 记 unknown；空字符串伪完整 → 已检测（1-2-2）：_is_missing 覆盖空/纯空白，四个 identity 面统一。

## TARGET / IMPLEMENTED / UNKNOWN 矩阵（执行层基本功能讨论 2026-10-07）

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| Q1 三模式隔离（replay.py 三个独立方法 + `_base_result` 硬编码零 + Worker 侧 `replay_mode!=normal` 次级阻断） | IMPLEMENTED（模块内） | replay.py |
| Q1 DSH Harness 端到端收口 | UNKNOWN | 编排层未把三模式串成端到端契约 |
| Q2 provenance 11-identity 绑定 + field-level unknown | IMPLEMENTED | replay.py |
| Q2 与 IdentityChain 会话级关联 / 空串伪完整风险 | IMPLEMENTED（1-2-2） | ReplayIdentity 增 identity_chain: IdentityChain 字段并进入 provenance；missing_fields 含 identity_chain.*；_is_missing 覆盖 None/\"unknown\"/空/纯空白；owner 仍只到 run 级（会话链绑定进 provenance，未耐久存储，见 Known gaps） |
| Q3 live 默认拒绝 + 零外部执行计账 | IMPLEMENTED / fail-closed | replay.py |
| Q3 「零」是结构性而非断言式 | IMPLEMENTED（1-2-3） | replay.py 增 `assert_zero_external_execution` 守卫 + `live_replay` 返回结果附 `zero_external_execution` 计账块（断言式、非结构性、fail-closed）；原结构性不执行保留为兜底，守卫把其升级为可测失败信号；不替代 1-8 host sandbox |
| Q4 owner-backed 来源分类（native/plugin-composed/outer-composed 枚举字段） | IMPLEMENTED（1-2-4） | composition.py 增 `evidence_source` 枚举（native/plugin-composed/outer-composed）+ `_validate_evidence_source` 校验；`record_result`/`record_event` 公共 seam 强制 `evidence_source` 必填（fail-closed）；`results`/`events` 表加列，SCHEMA_VERSION 1→2 迁移存量库（NULL=unknown 不撒谎）；owner 内部事件默认 native，外部 adapter/ fixture/ runner 分类 outer-composed，plugin-aware runner 分类 plugin-composed |

## Known gaps

- DSH Harness 端到端未把三模式收口为可验证契约（模块内能隔离，编排层未接）。
- provenance 与 IdentityChain 的会话级关联已闭合（1-2-2）：ReplayIdentity 绑定 identity_chain 进 provenance，空串/纯空白识别为缺失（四个 identity 面统一）。残留：owner 持久层仍只到 run 级，会话链未耐久存储——属 1-5 Run 生命周期或独立节点范围，1-2-2 选 A 不动 owner schema。
- ~~live 的「零外部执行」是结构性的（方法不执行），没有断言守卫，重构时可能静默失效~~ — 已解决（1-2-3）：`assert_zero_external_execution` 把该不变量升级为可测失败信号，重构误执行会 fail-closed，`live_replay` 结果附 `zero_external_execution` 计账块。
- evidence 来源分类缺 native / plugin-composed / outer-composed 枚举字段，无法在 owner 层区分三类来源。

## Backlog（实现前须登记，不阻塞本结论）

1. P0 DSH Harness 端到端三模式收口：在编排层把 recorded/simulated/live 串成契约并加回归测试。
2. ~~P1 provenance 与 IdentityChain 会话级关联；把空字符串识别为缺失~~ — 已完成（1-2-2）：ReplayIdentity 绑定 identity_chain，四个 identity 面（IdentityChain / ComponentIdentity / ProviderIdentity / ReplayIdentity）统一空串识别。
3. ~~P1 live 零外部执行加断言守卫（断言式计账，非结构性）~~ — 已完成（1-2-3）。
4. P1 owner 增 evidence 来源枚举字段（native/plugin-composed/outer-composed）并强制分类。

## Source map

- `../../src/zworkbench/replay.py`
- `../../src/zworkbench/composition.py`
- `../../tests/test_replay.py`
- `../../tests/test_w8_evidence_replay.py`
- `../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md`
- [CompositionOwner](ta-composition-owner.md)（依赖其 `replays` 表）

## Related authority

- [系统概览](ta-overview.md)
- [CompositionOwner](ta-composition-owner.md)
- [执行层 effect 授权](ta-execution-effect-authorization.md)
- [Provider 适配与降级](ta-provider-adaptation.md)
- [终止与资源生命周期](ta-termination-resource-lifecycle.md)
