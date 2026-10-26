---
status: partially-accepted
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

## 首刀落地决策（2026-10-26，zj 拍板三项）

首刀刻意只做「能真跑、真记账、真门控」的最小闭环，把范围面和风险面都收窄：

1. **执行对象 = 预置档位白名单（execution profile）**，不是任意 argv。
   `config.json` 的 `execution_profiles`（env `ZW_EXEC_PROFILES` 覆盖）声明
   `name` + 固定 `command` + 固定 `args` + `timeout_sec` + 可选 `workdir`；
   HTTP 面只接受**档位名**，请求体没有 command/args/dir 字段可填。
   理由：通用 argv 执行器等于给这个 loopback 服务开一个任意命令执行端口，
   而审批门本身也是 HTTP 打开的，安全边界会退化成「有 token + 点一次同意」。
2. **首刀环境 = local only**。`ExecutionProfile.Validate` 主动拒绝
   `container` / `remote` —— 不静默声称支持尚未实现的能力。
3. **审批门 = 复用 approvals 表**，开放 `RequestApproval` / `Approve` /
   `DenyApproval` 三个写路径（此前 `router_evidence.go` 明确不开放）。

### 实现上两处值得记下的判断

- **编排层不重写 token 校验，进程内复用 `ClaimEffect`。**
  ADR 0020 前提 3 要求的「显式 approval 才起进程」，owner 的 `ClaimEffect`
  已经完整实现：approval 缺失/未批准 → 自动把 run 推 `waiting_approval` 并
  denied；token 走常量时间比对、防重放（`consumed_at`）、过期检查、scope 匹配。
  在编排层重写一遍只会多一处能悄悄偏离的实现。因此 API **不暴露**
  `ClaimEffect`（不是对外写路径），但 `internal/execution` 在进程内调用它。
  这同时满足「单一 durable owner」与「不重复实现 C28」两条约束。
- **执行是同步的**。`POST .../execute/confirm` 阻塞到进程结束，响应即结论。
  本地单用户工具里「点执行 → 直接看到退出码和输出」最好懂；为假想的并发长任务
  引入作业表 + 异步，会让证据链多一个「执行中」中间态而收益为零。若将来真需要
  跑超长任务，再引入作业表，而不是现在预留。

### 为什么首刀不触发前提 4（exit_ledger 断言修正）

`exit_ledger` 的硬编码断言是「本地/owner 证据不能声称 Provider 清场」
（`provider_remote_zero_residue` 强制 `unknown/delegated`）。**local 执行器
不产生任何远程 provider 残留**，这条断言依然正确，无需修改。只有 container /
remote 执行器落地后，才需要按证据 caliber 修正它 —— 届时「起过容器」本身
就是需要单独记账的副作用面。

## Invariants（约束，沿用 ADR 0019 / AGENTS.md）

- **单一 durable owner 不变式**：执行结果（退出码、日志、副作用）由 evidence Owner 唯一记账，执行器不得自成第二事实源。
- **fail-closed**：执行器不可用 / 超时 / 取消 → run 进入 safe 终态或 `failed`，绝不静默标记 completed，绝不 500/panic 掩盖。
- **零依赖守卫**：不引入 docker/containerd/k8s SDK；仅标准库 `os/exec` + 网络，CI 中 `ZW_ZERODEP_BUILD=1` 仍须过。
- **审批不静默**：真实副作用前必须显式 approval，不得为「方便」默认放行。

## Acceptance（验收）

首刀（local）已验项，逐条对应可复核证据：

| 验收项 | 状态 | 证据 |
|---|---|---|
| local 环境驱动 run 生命周期，退出码正确记账 | ✅ | e2e：`git rev-parse --short HEAD` → `exit=0` / `run.completed`；`sh -c 'exit 7'` → `exit=7` / `run.failed` |
| 超时路径不挂死、进 safe 终态、日志可复核 | ✅ | e2e：`sh -c 'sleep 5'` + `timeout_sec=1` → `timed_out=true` / `run.safe_stopped`；单测 `TestLocalRunTimeout` / `TestConfirmTimeoutSafeStopsRun` |
| 取消路径 | ✅ | 单测 `TestLocalRunCancel` / `TestConfirmCancelSafeStopsRun` |
| 未 approve 前不触真实副作用 | ✅ | 单测 `TestConfirmWithoutApprovalDoesNotExecute`（断言 executor 调用次数为 0）；e2e 步骤 3 `executed=false / denied: approval_missing_or_not_approved` |
| approve 后才起进程 | ✅ | e2e 步骤 4-5；单测 `TestConfirmWithApprovalExecutesAndCompletes` |
| 一次性 token 不可重放 | ✅ | 单测 `TestConfirmTokenReplayIsDenied`；e2e 步骤 6 `denied: run_terminal:completed` |
| 零依赖守卫（含 `CGO_ENABLED=0 go build`） | ✅ | `go test ./internal/buildguard/` 全绿；`go mod` 无新增依赖 |
| container / remote 环境 | ⬜ 待后续切片 | `ExecutionProfile.Validate` 现主动拒绝这两类，不静默声称支持 |
| `exit_ledger` 断言按证据 caliber 修正 | ⬜ 待 container/remote 切片 | local 执行不产生远程残留，当前断言仍正确 |

已知限制（诚实标注，不当作已解决）：

- **输出未做脱敏**：`execution.stdout` / `execution.stderr` 原样落本地证据库
  （文件权限 0600、不出本机），事件里显式写 `redaction=none`。执行输出可能含
  密钥或个人信息 —— 这是「不猜也不改，但绝不假装已清洗」的取舍。
- **子进程树不被整组回收**：超时用 `context` 取消主进程，孙进程理论上可能残留。
  这与 `exit_ledger` 的「unknown 不默认升级为已清场」同源 —— 不声称清场。
- **服务重启会留下 running 的 run**：同步执行期间进程被杀时，run 停在
  `running`，需走既有的 `BeginRecovery` / `safe-stop-on-violation` 收口。

## Risks（风险与缓解）

- **R1 依赖膨胀**：引 SDK 会破零依赖守卫 → 强制 `os/exec` 调 CLI，不引库。
- **R2 副作用不可复核**：真实环境清理状态难证 → 保持 unknown 而非默认声称清场；证据 caliber 对齐。
- **R3 审批疲劳**：每次执行都审批会拖慢 → 可设受信环境/会话级一次性授权，但仍非静默全局放行。
- **R4 远程安全**：连远程需凭证 → 凭证走环境变量/配置，不入证据库，不落 git。

## Codex 映射（首刀已填）

| 能力 | ZW 落地 | 状态 |
|---|---|---|
| 真实执行（本地） | `internal/executor`（`Executor` 接口 + `Local`，`os/exec` 不经 shell） | ✅ 首刀 |
| 白名单档位 | `config.ExecutionProfile` / `ExecutionProfiles`（`ZW_EXEC_PROFILES`） | ✅ 首刀 |
| 执行日志 / 退出码记账 | `internal/execution`（`execution.*` 事件 + `CompleteEffect` + 终态映射） | ✅ 首刀 |
| 执行审批门 | `evidence.WaitForApproval` + `ListApprovals` + `ClaimEffect`（进程内复用） | ✅ 首刀 |
| 执行 API | `internal/api/router_execution.go`（profiles / execute / confirm / approve / deny） | ✅ 首刀 |
| 前端执行面板 | `CodingEvidenceTab`（档位选择 + 待审批 + 一次性 token + 结果） | ✅ 首刀 |
| 真实执行容器 | `docker` CLI 执行器 | ⬜ 后续切片 |
| 真实执行远程 | SSH / API 起进程 | ⬜ 后续切片 |

## Status

PARTIALLY ACCEPTED 2026-10-26（zj 拍板三项后首刀落地）。

- **已落地（首刀）**：local 环境的真执行 + 白名单档位 + 审批门 + owner 记账 +
  API + 前端面板。三条终态路径（completed / failed / safe_stopped）均经真实
  server 的 e2e 验证，零依赖守卫全绿。
- **仍 open**：container / remote 执行器（前提 1 的另两类环境），以及随之而来的
  `exit_ledger` 断言修正（前提 4）。这两个是同一条依赖链上的后续切片，
  未完成前 `ExecutionProfile.Validate` 会主动拒绝声明这两类环境。
