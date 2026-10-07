---
doc-kind: design
authority: supporting
axis: product-scenario
status: target
implementation-status: partial
source: ../prds/r3-real-usability-roadmap.md
source-id: prd-r3-real-usability-roadmap
authority-id: design.solo-real-provider
---

# 产品场景：solo 真实可用（真实写副作用 + 真实 Provider）

本页是 R3「真实可用路线图」的**产品场景实体**，沉淀「真实可用」的判定门槛与最小切片。这是产品规划权威视角，不是实现事实；未由 owner-backed 证据证实的能力标 `target` / `unknown`。

## Question

对单人开发者，「真实可用」的终态判据是什么？最小可用切片与完整产品的边界在哪里？

## Scope（三层判据 AND 门）

`产品可用 = 工程判据 ∧ 用户信任判据 ∧ 价值判据`，任一不达标 → R3 维持 `target`；「可用」宣告不因工程闭环（S0–S3）完成而提前，须等价值基线出数。

- **工程判据（硬门）**：真实项目隔离 worktree 上 diff apply + local commit 成功（push 为单独门），CompositionOwner 出具可复核 receipt；真实单 Provider（Ark `ark-code-latest`）接入，失败分类记录率 100%，unknown→safe-stop，无 silent switch；未知状态仍 `safe-stop` 无自动 retry；host enforcement 按 ADR 0008 三判据出证；S3 dogfood 闸门连续 10 次默认入口全链路、acceptance 证据全部 `exercises_default_product_path=true`。
- **用户信任判据（硬门）**：zj「愿意每周交给它、不必盯着」——失败可预期/可复核/可回退，fail-safe 而非 fail-open；receipt 成为默认路径可复核证据。
- **价值判据（硬门·须等出数）**：价值基线测量给出量化结果（比裸 Codex 省 X% 时间 / 少 Y 次人工复查），作为继续投安全外壳的前置论证。

## 最小可用切片（门槛）vs 完整产品

- **最小 MVP（solo 可用）** = 两条并行 seam：**真实写副作用**（隔离 worktree diff apply + local commit，push 单独门 S4）+ **真实 Provider**（首版单 Provider Ark，无 failover）。
- **完整产品（"做完"门槛，非"可用"门槛）**：DSH 全 runtime（H7）/ 生产部署（H8）/ live replay 产品化 / C7 真实世界部分 —— 标 `deferred-until-demand`，不参与「可用」AND 门。

## 已锁定切片顺序（solo 真实可用路径）

`S0 host-enforcement spike → S1 单 Provider 产品化（无 failover）→ S2 写 seam（隔离 worktree + apply + local commit only + receipt）→ S3 dogfood N=10 闸门 → S4 push 单独门`；之后才谈 H6-full / H7-lite / H8 分层。

- S0 未出证 → S2 不得标 `implemented`（ADR 0008）。
- S1 第 0 步前置闸门（issue #39）：identity↔transport 单一来源绑定 + 删 `setdefault` 反向回填 + 4 条 fail-closed 测试。

## 架构负约束（防 foreclosure，适用于 S1/S2 及后续）

1. Provider 接入必经 **Host Capability Facade**，产品代码不得直连（否则 H6-full 多 Provider 与未来 DSH 均需返工）。
2. 写 seam 的 receipt / approval 数据模型不得引入**第二个 durable owner**（ADR 0001 不变量）。
3. 写操作爆炸半径分级：diff apply（可 revert）→ local commit（可 reset）→ push（难撤回）三级，分别配 approval 粒度与 receipt；首切片限定隔离 worktree / 可丢弃 repo。

## Status

TARGET / PARTIAL — S2（write seam，roadmap 1-7 completed）、S4（Git push 门控，1-9 completed）、真实 Ark 读路径（1-9-1~3）已落地并测试通过；H6-full / H7 / H8 仍 target / deferred-until-demand。评测脚手架（H1–H8 / C1–C7 runner）通过 ≠ 产品能力已实现，二者分开计账。

## Source map

- `../prds/r3-real-usability-roadmap.md` §最小可用切片、§已锁定的切片顺序、§S0–S4 切片 DoD、§产品定位与架构约束、§产品目标（PG）、§产品可用判定门槛（三层 AND 门）、§价值基线实证。

## Related authority

- [写边界 HOLD ADR](../architecture/ta-reversible-write-boundary.md)
- [Provider 适配降级](ta-provider-adaptation.md)
- [唯一 durable owner ADR](../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md)
- [host enforcement ADR](../zj-adr/0008-host-enforcement-is-fail-closed-and-testable.md)
- [显式授权 ADR](../zj-adr/0009-explicit-authz-for-real-provider-and-write-seam.md)
- 协同场景：[ps-safe-stop-unknown](ps-safe-stop-unknown.md)
