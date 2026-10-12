---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.host-enforcement.active-read-path.boundary
supersedes: adr.host-enforcement.fail-closed-and-testable (applicability to the active Codex read-path under host_enforcement)
---

> ⚠️ **路线图节点引用勘误（非决策变更）**：本 ADR 撰写时 host-enforcement / 真实可用工作挂载于路线图分支 `1-9`。路线重组后该工作已迁至 `1-10`（R3 solo 真实可用）：
> - 本 ADR 中 `1-9-4`（B2 分层 fail-closed spike）→ 现行 `1-10-1`（S0 host-enforcement spike）；
> - `1-9-2` / `1-9-3`（direction (b) 真实 Codex 接入、尊重宿主 seatbelt）→ 现行 `1-10` 分支的真实 Codex 接入探索，其结论已固化为本 ADR 决策本身。
> 现行 `1-9` 已改作 R4 首跑/onboarding 分支（1-9-1 零配置首跑 / 1-9-2 doctor / 1-9-3 价值演示 / 1-9-4 fail-closed UX / 1-9-5 回归脚本），**与本 ADR 的 host-enforcement 主题无关**——请勿从本 ADR 的 `1-9-*` 引用跳转到现行 `1-9` 分支。

# ADR 0010：活动 Codex 读路径的 host enforcement 边界是外部宿主 seatbelt

> Supersedes ADR 0008 **仅限** active Codex 读路径（`host_enforcement=True`）的适用域。ADR 0008 的 S0 spike 意图与未来 B2 分层 fail-closed 仍完全有效（见 Consequences）。

## Context

ADR 0008 要求 host enforcement 必须 fail-closed（三判据：deny-all 白名单、enforcer 不可用→拒绝启动、violation 入 receipt），并以 S0 `host_enforcer.py` spike 为候选载体。roadmap 1-9-2 / 1-9-3 direction (b) 在真实接入 codex app-server 后发现：macOS 禁止嵌套 `sandbox_apply`——ZWorkbench 若用 seatbelt 包裹 codex（codex 内部又会对其 shell 工具跑 `sandbox-exec`），嵌套必 EPERM，阻断 workspace 读取。1-9-3 因此选择"不包裹、仅给 codex 加 `--dangerously-bypass-approvals-and-sandbox`，靠 codex 自身/外部宿主 seatbelt 作边界"，并已在非 App Sandbox 宿主（mac Terminal / CI）实证 codex 能正常读文件。该决策已落地，但 ADR 0008 从未修订，导致文档与实现不一致：active path 上 fail-closed 三判据**无一满足**。

关键事实（已核实）：`--dangerously-bypass-approvals-and-sandbox` 同时禁用 codex 内部 sandbox 与 approvals。因此在**非 seatbelt 宿主**（mac Terminal / CI / 大多数开发机）上，worker 实际**全程无沙箱**（可任意写文件、联网）= fail-open；仅在 **App Sandbox 宿主**（WorkBuddy.app）上，外部 App Sandbox 才是边界（read + 受限 write，非 deny-all）。S0 spike 模块 `host_enforcer.py` 自洽实现了 ADR 0008 三判据，但 `codex_adapter` 已不再 import 它，故未进入 active path。

## Decision

在 **active Codex 读路径**（`host_enforcement=True`）上，ADR 0008 的 wrap 模型与 fail-closed 三判据**不适用**，改为：

1. **App Sandbox 宿主**：外部 App Sandbox 为强制边界；ZWorkbench 不包裹，仅加 bypass flag 使 codex 停止嵌套 `sandbox-exec`。此为真实边界，但非 deny-all。
2. **非 seatbelt 宿主**：`host_enforcement=True` = approvals bypass + 无包裹 = **fail-open**；该开关在此类宿主上**不是安全控制**，仅是"App Sandbox 宿主下的便利开关"，不得宣称为沙箱权威。
3. ADR 0008 的 deny-all / refuse-to-start / violation-receipt 三判据在 active path **暂不落实**；residual risk = 非 seatbelt 宿主上 worker 无强制边界。

ADR 0008 的 **S0 spike 意图与未来 B2 分层 fail-closed 仍完全有效**；本 ADR 仅收窄其适用域。后续 B2 spike（探外部 seatbelt → 非 seatbelt 宿主包裹或拒绝启动）已排期（roadmap 1-9-4），恢复 criterion #2 于裸机。

## Consequences

- `host_enforcement` 的语义在文档层与实现层一致：它是"App Sandbox 宿主下的便利开关 + 外部边界依赖"，而非"强制沙箱权威"。
- 非 seatbelt 宿主上跑写 seam 前，必须先有 B2（或外部宿主提供边界），否则 worker 无强制约束；当前不得在裸机宣称写 seam 安全。
- ADR 0008 consequences 中"S2 acceptance 须带 enforcer 证据"对 active path 暂缓，待 B2 落地恢复。
- `host_enforcer.py` 曾作 S0 参考实现（其 `EnforcerUnavailable` / `spawn_sandboxed` 拟作 B2 候选载体）；B2 已据 roadmap **1-9-4** 探测判 `not-viable`（macOS 26 对普通进程整体禁用 `sandbox-exec`），且该模块 active path 从不 import。经决策**已删去**（`git rm src/zworkbench/host_enforcer.py tests/test_host_enforcer_s0.py`），避免误导后人以为包裹机制仍可用。
- 1-9-3 已记录的"尊重宿主 seatbelt"决策正式纳入 ADR 体系。

## Related decision: ZW_OWNER_SANDBOX（durable-owner 沙箱降级）

同一 macOS 沙箱根因族的另一处偏离（与 1-9 host_enforcement fail-open 同源）：macOS 沙箱（WorkBuddy.app App Sandbox / sandbox-center）阻断 WAL journal 的 fsync 写入 workspace，导致 durable owner 在沙箱宿主无法创建/写入。

- 决策（commit 3d11f08，**intended**）：opt-in `ZW_OWNER_SANDBOX=1`，`CompositionOwner._configure_connection` 降级为 `journal_mode = MEMORY` + `synchronous = OFF`，换取 drivability（`composition.py:1206-1216` 注释已写明 trade-off）。
- 偏离范围：production 路径（默认不设该 env）保持 `WAL` + `FULL`，不受影响。
- residual risk：opt-in 路径下进程崩溃可能丢失未刷盘的 owner 状态（runs / approvals / effects / replay metadata），safe-stopped 一致性边界弱化。当前 scope 仅本地 sandbox 宿主跑 harness，可接受；**但禁止在 production 环境设 `ZW_OWNER_SANDBOX=1`**。
- 与 1-9 系列"macOS 沙箱阻断 fsync / sandbox-exec"同根因，纳入同一次 review 审计。

## Amendment: coding Worker 的 host sandbox 前置契约（node 1-8-1）

Node 1-8-1 要求把"host sandbox"作为 coding Worker 真实 Workspace 写入的**前置条件**。本修正案不推翻 ADR 0010 的结论，而是在其之上为 **`WorkerBridge` 的 coding 子进程**补一个**独立、fail-closed 的前置契约**，与 `codex_adapter.host_enforcement`（本 ADR 判定为 fail-open）**语义隔离**。

### 为什么需要独立契约

- coding Worker 子进程与 codex 同样继承 macOS 禁止嵌套 `sandbox_apply` 的限制：`subprocess.Popen` 拉起的 Worker 在主力宿主（本机 Terminal / CI）上**包不住 OS 沙箱**。
- 但 1-8-1 的节点前提（"真实 Workspace 写入前置"）不能因此退化为"无前置"。ADR 0008 精神 #2（enforcer 不可用→拒绝启动）要求：**检不出边界就 refuse-to-start，绝不降级裸跑**。
- 因此采用 **operator-attested host-require 契约**：不重建 OS 包裹层（enforcer 已删、B2 判 not-viable），改由 operator 显式声明宿主提供边界；缺声明即拒绝启动。

### 契约内容（`src/zworkbench/host_sandbox.py`）

1. `WorkerBridge` 新增独立构造参数 `require_host_sandbox: bool = False`（**默认关**，保证 dev/test 路径零回归）与 `host_sandbox_attestation: Optional[str]`。
2. 当 `require_host_sandbox=True` 时，必须在 `read_only_coding` 启动子进程**之前**提供 attestation——来自构造参数 `host_sandbox_attestation` 或环境变量 `ZW_HOST_SANDBOX_ATTESTED`。**两者皆空 → `WorkerBridgeError(code="host_sandbox_absent", safe_stop=False)` 拒绝启动（fail-stop，非 safe-stop）**。
3. 辅助检测 `detect_os_sandbox()`（best-effort）：仅在能**确证**宿主无边界时返回 `False`（当前仅 macOS `APP_SANDBOX_CONTAINER_ID` 缺失不判 False，Linux `Seccomp:2` 判 True，其余返回 `None`）。当 operator 已 attest 但检测**确证**矛盾（`False`）时同样拒绝启动（conflict = fail-closed）；检测**无法判定**（`None`）时放行（warn-only），避免无法自省的主机被误杀。
4. 边界缺失属**前置条件失败**，不是 Worker 违规：`_verify_host_sandbox_boundary()` 在 `_activate_operation` 之前 raise，parent run 保持 `running`、child run 永不创建，错误以 fail-stop 语义外抛。

### 与 ADR 0010 / ADR 0008 的关系

- **不改变 ADR 0010 结论**：`codex_adapter.host_enforcement` 在非 seatbelt 宿主仍是 fail-open 的便利开关，文档语义不变。
- **落实 ADR 0008 精神 #2**：coding Worker 路径上"enforcer 不可用→拒绝启动"以 operator-attested 形式复活；代价是**安全控制依赖 operator 诚实声明**，故 residual risk 仍挂账（恶意/误配 operator 可伪造 attestation）。这是 macOS 包裹不可行下的诚实折中，已在 1-8-1 决策记录中固化。
- 错误码 `host_sandbox_absent` 已纳入 `worker_heartbeat.WORKER_ERROR_CODES` 词汇表；测试见 `tests/test_worker_coding.py`（absent → fail-closed / attested → 正常 / 默认关 → 不门控）。
- **不越界**：1-8-1 仅覆盖 coding Worker 子进程；write-seam apply/commit/push 的 host 边界属 node 1-10，本修正案不触及。

