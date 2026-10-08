---
doc-kind: design
authority: supporting
axis: product-scenario
status: implemented
implementation-status: partial
source: ../prds/r1-ui-reference-registry.md
source-id: prd-r1-ui-reference-registry
authority-id: design.safe-stop-unknown
---

# 产品场景：unknown → safe-stop 失败关闭语义

本页是 R1 + R3 的**产品场景实体**，沉淀「未知即安全停止」的失败关闭语义这一贯穿全局的不变量。

## Question

当 identity / effect / permission / Provider / workspace / replay 状态为 unknown 时，产品应如何行为，才能既不推断成功、也不自动 retry？

## Scope（失败关闭语义）

- **状态机**：`draft → preflight(pass|deny) → created → running → completed|failed|safe-stopped|recovering`；缺少必要身份或 evidence 时为 `unknown`。状态必须有文本、来源和非颜色线索；`draft` 没有 `run_id`，不得伪装为可恢复 Run。
- **unknown 必须可见**：未知 identity / effect / permission / Provider / replay 须显式显示 `unknown` / `safe-stopped`，不得推断成功或自动 retry（沿用 AGENTS.md §6 判定规则）。
- **副作用契约**：`request → policy → decision → claim → execute → complete/reconcile`；未知类别默认 deny。
- **写边界 fail-closed**：真实写副作用必须带 host enforcement 证明（须独立于配置声明真正约束路径/进程/网络），enforcer 失效时 Worker 拒绝启动，绝不降级为无沙箱运行（ADR 0008）。
- **Provider-side 退出记账**：对真实 Provider 发请求即产生远端 retention / 任务，沿用 staging runbook 的 `unknown / delegated` 口径如实记账、不假装已清除。

## 关键设计约束

- 任何 fallback 必须来自显式规则；CSS、坐标、DOM 顺序和「当前首项」不是合法隐式 fallback（与 pd-ui-reference-system 同源）。
- 关键结论为 unknown 时保持 `HOLD`，记录下一证据、owner 与回滚路径；证据区分 `native` / `plugin-composed` / `outer-composed` / `owner-backed` 并固定版本/digest/environment/policy/workspace/owner schema/cassette identity。

## Status

IMPLEMENTED（fail-closed 不变量与 unknown→safe-stop 语义已落地并测试）；C7 真实世界部分（远端账户 / retention / 账单 / 本地退出 ≠ Provider 退出）的**产品补齐 seam 已落地**（`composition.py` 的 `provider_exit_ledger` 增 `evidence_class` 枚举 `local-inventory` | `owner-backed`，默认 loopback/fake 路径保持 `local-inventory` + `unknown/delegated`；新增 `attach_provider_exit_receipt` 校验 v2 owner receipt 并追加 `owner-backed` 条目，强制 `provider_remote_zero_residue='unknown/delegated'`，绝不升级为 Provider 清零证明）。**真实世界证据本身仍由账户 owner 在官方控制台采集、保持 `unknown/delegated`**——产品只补齐可复核的 durable 记账 seam，不声称远端零残留。

## Source map

- `../prds/r1-ui-reference-registry.md` §Required boundaries、§State and presentation。
- `../prds/r3-real-usability-roadmap.md` §工程判据、§风险。

## Related authority

- [Provider 适配降级](ta-provider-adaptation.md)
- [终止与资源生命周期](ta-termination-resource-lifecycle.md)
- [host enforcement ADR](../zj-adr/0008-host-enforcement-is-fail-closed-and-testable.md)
- 场景框架：[ps-solo-real-provider](ps-solo-real-provider.md)
