---
status: proposed
doc-kind: adr
authority: primary
authority-id: adr.coding-evidence.real-executor
---

# ADR 0020：编码证据 真执行器（epic）

- 来源：从 ADR 0019 Follow-up「真执行器（仍未实现）」拆分为独立 epic（zj 2026-10-26 指令「拆真执行器为一个新 epic」）。ADR 0019 仅落地「上下文维度 + 授权/可达性前置契约」，真执行器不在其范围。
- 关联：ADR 0019（上下文维度 + 授权/可达性）、ADR 0016（B2 Go evidence owner）、AGENTS.md 所有权不变量、零依赖守卫（buildguard）。

## Context

ADR 0019 把 `environment` 字段做成了**声明 + 两层前置契约**（授权＝白名单强制 400 fail-closed；可达性＝`envprobe` 只读探测仅提示）。但 ZW 当前**没有任何执行器**：`internal/evidence` 是记账侧（CompositionOwner 状态机 + `exit_ledger` 注释明确默认无真实远程 provider），run 生命周期完全由 UI 手动 `transition` 驱动，没有「真正在某个环境里跑起来并把结果记回去」的能力。

「真执行器」＝起容器 / 连远程并**驱动 run 生命周期**（start → 执行 → 退出码记账 → complete/fail）。它是比 ADR 0019 大得多的能力面，继续挂在某条 ADR 的 Follow-up 里会模糊 scope 与验收边界，因此独立成 epic 级追踪。

## Decision（范围定义，非实现决策）

本 ADR 界定真执行器 epic 的**范围与落地前提**，不在此拍板实现排期（排期待 zj 单独确认）。真执行器必须同时满足以下 4 项前提，任一未决都不应默认「已清场」：

1. **执行器抽象**：本地 `os/exec` 调 docker CLI（或等效），**不引 SDK**，过零依赖守卫（go.mod 仅 modernc.org/sqlite 纯 Go）。远程 = 经 SSH/API 拉起；抽象层对 owner 暴露统一 `Start/Wait/Cancel` 接口。
2. **超时 / 取消与日志采集**：执行须可设超时、可取消（context cancel），stdout/stderr 落证据（event 或独立日志表），owner 可复核「跑过什么、产出什么」。
3. **审批门**：沿用 `waiting_approval` 状态，**非静默放行**；真实副作用（起容器/连远程）前须显式 Human approval，与证据 caliber 一致。
4. **与 `exit_ledger` 断言对齐**：当前 `exit_ledger` 注释假设「默认无真实远程 provider、口径硬编码 unknown/delegated」。**真执行后该断言必须按证据 caliber 修正**——不得默认升级为「已清场 / 零残留」，真实环境的清理状态须有可复核证据，否则保持 unknown。

## Invariants（约束，沿用 ADR 0019 / AGENTS.md）

- **单一 durable owner 不变式**：执行结果（退出码、日志、副作用）由 evidence Owner 唯一记账，执行器不得自成第二事实源。
- **fail-closed**：执行器不可用 / 超时 / 取消 → run 进入 safe 终态或 `failed`，绝不静默标记 completed，绝不 500/panic 掩盖。
- **零依赖守卫**：不引入 docker/containerd/k8s SDK；仅标准库 `os/exec` + 网络，CI 中 `ZW_ZERODEP_BUILD=1` 仍须过。
- **审批不静默**：真实副作用前必须显式 approval，不得为「方便」默认放行。

## Acceptance（验收，待排期后细化）

- 真执行器在 `local` / `container` / `remote:<endpoint>` 三类环境均能驱动 run 生命周期，退出码正确记账为 complete/fail。
- 超时 / 取消路径验证：超时不挂死、取消后 run 进入 safe 终态，日志可复核。
- 审批门验证：未 approve 前不触真实副作用；approve 后才起容器/连远程。
- 零依赖守卫：`ZW_ZERODEP_BUILD=1 go test ./internal/buildguard/` 通过（含 `CGO_ENABLED=0 go build`）。
- `exit_ledger` 断言修正为「按证据 caliber 记录真实清理状态，unknown 不默认升级为已清场」。

## Risks（风险与缓解）

- **R1 依赖膨胀**：引 SDK 会破零依赖守卫 → 强制 `os/exec` 调 CLI，不引库。
- **R2 副作用不可复核**：真实环境清理状态难证 → 保持 unknown 而非默认声称清场；证据 caliber 对齐。
- **R3 审批疲劳**：每次执行都审批会拖慢 → 可设受信环境/会话级一次性授权，但仍非静默全局放行。
- **R4 远程安全**：连远程需凭证 → 凭证走环境变量/配置，不入证据库，不落 git。

## Codex 映射（待实现后填）

| 能力 | ZW 落地 | 状态 |
|---|---|---|
| 真实执行容器/远程 | 真执行器 epic | 未实现（本 ADR 范围） |
| 执行日志/退出码记账 | evidence Owner | 未实现（本 ADR 范围） |
| 执行审批门 | waiting_approval | 未实现（本 ADR 范围） |

## Status

PROPOSED 2026-10-26（zj 指令拆分为独立 epic；范围与 4 落地前提已界定，实现排期待 zj 单独确认）。
