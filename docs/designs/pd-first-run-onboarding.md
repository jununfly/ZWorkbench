---
doc-kind: design
authority: supporting
axis: product-design
status: target
implementation-status: unknown
source: ../prds/r4-onboarding-first-run.md
source-id: prd-r4-onboarding-first-run
authority-id: design.first-run-onboarding
---

# 产品设计：首跑与 onboarding

本页是 R4「首跑与 onboarding 设计」的**产品设计实体**。本文件是产品规格，非实现事实；未由 owner-backed 证据证实的能力标 `target` / `unknown`。

## Question

如何让一个非作者用户（验收轨主语 = zj 本人）以零配置完成首跑，并在浏览器看到自己 run 的 recorded view，而绝不采集/持久化任何凭证？

## Scope

- **首跑最小形态**：`zworkbench run --prompt "..."` 自动在默认位置脚手架 `case-root + workspace + state` 子目录；`--codex` 缺省按 PATH 探测；Provider 默认 `fake-loopback`（零配置、恒真可达）。
- **onboarding = 只读自检 `doctor`**：只探测（Codex 可执行性、case 目录约定、loopback provider 可达性），输出 readiness 报告 + 每项失败 fix hint；不采集/不存储任何凭证。
- **价值演示缝合**：run 完成写 `--db` 后，stdout 末尾追加 `next_steps` 数组（可复制的 `ui-host` / `ui --db` 命令）；`--open` 子进程自动拉起 `ui-host`（仍 loopback、仍只读）。
- **fail-closed UX 成本回收**：`PreflightViolation` 增加 `hint` 字段（人类可读修复动作）；首跑场景区分 `timeout` 与 `failed` 并给重试提示。

## Boundaries（不覆盖）

- 真实 Provider 在首跑路径中改写为「显式旁路」：doctor 末行指向 staging runbook 引导，不产品化为首跑步骤。
- wizard（位于 `scripts/` 下 4 个 `/zj-wizard` 生成物）今天仅是路线外 owner 工具，禁止 onboarding 收集/持久化任何凭证（`no_credentials_in_config` deny 语义）；issue #39 关闭前 doctor 不得输出「配置真实 Provider 已完成」类表述。
- 「非作者陌生人 <5 分钟」降为 deferred-until-demand + UX 目标，不得写回验收判据。

## Design decisions（durable）

- **主语分轨（承接 C1 约束4）**：验收轨 = zj（机械判定：干净 venv + 空 `case_root` 下 `pip install .` → loopback UI 见 `recorded_view_present=true`，脚本退出码 0 且可重放）；UX 目标轨 = 非作者陌生人（非判据，仅登记代理指标）。
- **真实 Provider = 一次显式、可记账、进 receipt 的授权动作**，与 sub-02（ADR 0009）共用「显式授权」语义；onboarding 仅只读自检 + 定位回填，不代持/不代填凭证。

## Status

TARGET / UNKNOWN — 设计已收敛，但端到端首跑价值演示仍待 owner-backed 证据（依赖 #40 解后补测，见 R3 价值基线实证纪律）。

## Source map

- `../prds/r4-onboarding-first-run.md` §首跑最小形态、§onboarding = 只读自检 doctor、§价值演示缝合、§fail-closed UX 成本回收、§端到端回归脚本验收线、§约束与依赖。

## Related authority

- [R3 真实可用路线图](../prds/r3-real-usability-roadmap.md)（价值基线 / S0–S4 切片）
- [ADR 0009 显式授权](../zj-adr/0009-explicit-authz-for-real-provider-and-write-seam.md)
- 体验路径见 [ep-first-run-journey](ep-first-run-journey.md)
