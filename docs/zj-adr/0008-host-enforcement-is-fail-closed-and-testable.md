---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.host-enforcement.fail-closed-and-testable
---

# ADR 0008：host enforcement 必须 fail-closed 且可测试

> 状态为 `accepted`：2026-09-27 H6–H8 scope 收敛讨论中，zj 拍板"S0 host-enforcement spike 提为下一节点"并采纳 fail-closed 三判据；enforcer 技术选型（候选见 Decision）留 spike 内定，不预判。

## Context

写边界（`ta-reversible-write-boundary`）的硬要求是：OS/host 层**实际强制**路径 / 进程 / 网络边界，配置声明不算数。代码事实核验（2026-09-27）：host enforcement 载体（`seatbelt` / `sandbox-exec` / `bubblewrap` / `firejail` / 容器）在 `src/`、`scripts/`、`evaluation/runner/` **0 命中**——连技术选型都未做。这意味着"真实写副作用"（R3 最核心缺口）的 acceptance 在 enforcer 落地前是空中楼阁：approval、receipt、幂等 key 全部建立在"被约束的 Worker 无法越界"这一未证明的前提上。

## Decision

- **真实写副作用的第 0 个切片是 S0 host-enforcement spike**：先证明"一个被沙箱约束的 Codex Worker 子进程无法越界写 / 联网"，再谈 apply / commit / push。先 macOS 单机，跨平台后置。
- **fail-closed 三判据（spike 出口 = 可测试断言，非 demo / 截图）**：
  1. 默认拒绝**全部**写 + 网络，白名单显式开启；
  2. enforcer 自身不可用 / 初始化失败 → Worker **拒绝启动**，绝不降级为无沙箱运行；
  3. 每次越界尝试产出**可复核 violation 事件**并进入 receipt。
- **候选**：macOS `sandbox-exec`(seatbelt) / 容器 / VM；Linux bubblewrap。spike 内定，不预判。
- **与 owner-backed approval 的关系**：enforcer 是 fail-closed 的机器强制层，approval 是人的授权层；二者独立生效——approval 通过不豁免 enforcer，enforcer 放行不代表 approval 已授权。violation 事件入 receipt 使越界尝试可审计。

## Consequences

- S0 未出证前，S2（写 seam）的 acceptance 不得标 `implemented`；真实写链路的一切安全声明须挂 enforcer 证据。
- 三判据直接进入 R3 的真实可用判定门槛；acceptance 证据须带 `exercises_default_product_path=true`。
- spike 有真实技术风险（seatbelt 配置面、容器开销 / 网络 deny 语义、VM 重量级），若某候选无法满足三判据，如实记录并换候选，不为进度放宽判据。
- 关联负约束（见 R3"产品定位与架构约束"节）：S1/S2 不得绕过 Host Capability Facade、不得引入第二个 durable owner——防止 H7/H8 `deferred-until-demand` 期间实施性堵死未来开工权。
