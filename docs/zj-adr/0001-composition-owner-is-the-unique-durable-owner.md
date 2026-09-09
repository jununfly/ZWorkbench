---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.composition-owner.unique-durable-owner
---

# ADR 0001：CompositionOwner 是唯一 durable owner

## Context

一个 Workbench 同时连接 Harness、Worker、Provider、workspace 与观测系统。它们都可能保存
session、日志、缓存或运行结果；若任一外部系统成为第二份跨 Run 状态真相，replay、恢复、
approval、effect reconcile 与退出将无法一致解释。

## Decision

CompositionOwner 持有所有 durable 的 run、attempt、event、effect、result、approval、replay metadata
与 backup/restore。DSH、Codex、Provider 和 observability 系统通过带 identity 的输入、事件或
receipt 与 owner 关联，但不直接写 owner 存储，也不成为 canonical state。

## Consequences

- 每条跨边界消息必须能关联 parent/child identity；不可关联即 `unknown` 并 safe-stop。
- effect 只通过 owner 的 request/policy/decision/claim/complete-reconcile 流程执行。
- Harness session、plugin state、Codex rollout 和 Provider 日志可以备份或引用，但不能替代
  owner backup/restore。
- 新增 adapter、plugin 或 Provider 时，必须证明其不创建第二个 durable owner。
