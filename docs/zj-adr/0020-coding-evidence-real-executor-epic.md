---
status: accepted
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
   （`container` / `remote` 已分别于 container / remote 切片放开，见下节。）
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
不产生任何远程 provider 残留**，这条断言依然正确，无需修改。

（原文此处预测「container / remote 落地后需修正它」。container 切片落地后该预测被
收窄为**仅 remote 触发** —— 容器是本机资源，与「远程 provider 残留」正交，
详见下文「前提 4 的修正」。）

## container 切片落地（2026-10-26）

环境维度从「local only」扩到 `local + container`。范围仍是**白名单档位**，
没有引入任意 argv —— 容器只改变「在哪跑」，不改变「允许跑什么」。

### 新增面

- `config.ContainerConfig`（挂在 `ExecutionProfile.Container`）：`image` 必填，
  另有 `workdir`（**容器内**绝对路径，默认 `/workspace`）、`network`（`none`/`bridge`）、
  `user`、`env`、`name`。环境声明与容器段**必须成对**：
  声明 container 却没容器段（不知道跑哪个镜像）、给了容器段却没声明 container
  环境（配置读起来和跑起来不一致），两个方向都当场拒绝。
- `executor.Docker`：走 `docker run` CLI（不引 SDK，零依赖守卫不变）。
  argv 由纯函数 `buildRunArgs` 产出并被逐字断言 —— 「容器里到底跑什么」
  完全由这段 argv 决定，必须能被精确测试。
- `execution` 按 `envprobe.Kind` 路由：`local` → `Local`，`container` → `Docker`。
  容器执行器缺位时**在审批之前**拒绝：不烧 token，也不留下一张注定执行不了的待批单。
- 证据：`execution.started` 记 `image` / `container_name` / `container_workdir` /
  `container_network`；`execution.finished` 与 effect 摘要记 `container_name` /
  `container_cleanup`。请求阶段（批准前）就能看到镜像与容器内目录 —— 否则是让人盲签。

### 五个值得记下的判断

1. **不用 `--rm`，改成显式 `docker rm -f`。** `--rm` 把清场交给 daemon 且不可观测：
   成功与否都不会回到我们这里。自己调用才有 `container_cleanup` 可写。
2. **清场结论是三态，不是 bool**：`removed` / `absent`（docker 报 `No such container`，
   即无残留）/ `failed: <原因>`。「没清干净」与「本来就没建」压成同一个 false，
   证据就无法回答「要不要人去手动清场」。
3. **杀 docker CLI ≠ 杀容器。** `exec.CommandContext` 只杀我们起的客户端进程，
   容器仍在 daemon 里跑。所以超时/取消后必须显式 `docker rm -f`，且用**独立
   context**（原 ctx 此刻已作废，拿它清场等于不清）。
4. **`network` 只允许 `none` / `bridge`，拒绝 `host`。** `host` 让容器直接共享宿主
   网络栈，实质削弱隔离，与「档位是受限执行」的定位冲突。默认 `none`：
   需要联网的档位必须显式写 `bridge`，让边界保持可读。
5. **宿主目录必须先存在。** docker 对不存在的 `-v` 源会**静默创建空目录**，命令于是
   跑在空仓库上并返回成功 —— 这是最危险的假成功。执行器起容器前 `os.Stat` 校验。

另外两条执行器层判定：

- docker CLI 退出码 **125 = `docker run` 自身失败**（daemon 不可用、参数非法），
  **不是**容器内程序的结论。当程序退出码处理会在证据里留下读不出真假的
  「exit 125」，因此返 error。
- 每个容器打 `--label zworkbench.execution=1`。服务被 SIGKILL 时清场代码没机会跑，
  label 是事后用 `docker ps -a --filter label=zworkbench.execution=1` 找出残留的
  唯一手段（而不是靠人记得起过哪些容器）。

### 前提 4 的修正：container 落地**也不该**改 `exit_ledger`

本 ADR 早先预测「container / remote 落地后需按证据 caliber 修正 exit_ledger」。
container 切片落地后逐行核对，这个预测**部分不成立**：

`provider_remote_zero_residue` 的语义是「**远程 provider** 是否留下残留」，硬编码
`unknown/delegated`。容器是**本机资源**：既不涉及远程 provider，也不产生 provider 侧
状态。把容器残留塞进这个字段，会让 `unknown/delegated` 从「provider 侧不确定」被读成
「容器也没清干净」—— 语义被污染，正是该 ADR 前提 4 自己反对的「默认升级」。

因此本切片**不修改** `exit_ledger`，而是为容器残留新开一条**正交**证据面
（`container_cleanup` 三态）。前提 4 当时仍 open，且只在 **remote 执行器**落地时
才真正触发——这是对原预测的收窄，不是漏做。remote 切片已于同日落地并正式收口前提 4，
见下文「remote 切片落地 → 前提 4 的修正」。

### container 的已知限制（诚实标注）

- 容器默认用户多为 root，写进挂载目录的文件在宿主上属主是 root。配置提供
  `container.user` 但**默认不设**：强行改 uid 会让 golang / node 这类镜像直接跑不起来，
  于是选择「显式优于默认」。
- 未设 `--memory` / `--cpus` 上限（配置面未开）。
- `network=none` 只约束容器**运行时**；镜像本地不存在时 docker 会 `pull`，
  那一步仍有网络出口。
- 无构建缓存卷，每次执行都是冷启动（`go test` 这类命令会明显变慢）。
- 服务进程被 SIGKILL 时容器会残留，需按 label 人工 `docker rm -f`。

## remote 切片落地（2026-10-26）

环境维度从 `local + container` 扩到 `local + container + remote`。范围仍是**白名单档位**，
没有改变「允许跑什么」—— 只是再回答一个问题：「能不能在某台远端机器上拉起这个档位」。

### 新增面

- `config.RemoteConfig`（挂在 `ExecutionProfile.Remote`）：`host` 必填，另有
  `port`（0=22 回退 22）、`user`、`identity_file`。环境声明与 remote 段**必须成对**：
  声明 remote 却没 remote 段（不知道连哪台机器）、给了 remote 段却没声明 remote
  环境（配置读起来和跑起来不一致），两个方向都当场拒绝。
- **端点不拼进环境名**：环境名用 bare `remote`，host/port 写在 `remote` 段里。
  `remote:host:port` 这种前缀形式被显式拒绝——避免「环境名」和「remote 段」变成
  两个真相源（`EnvRemote` 一个枚举值，`RemoteConfig` 一个配置段，语义唯一）。
- `executor.Remote`：走 `ssh` CLI（不引 SDK，零依赖守卫不变）。argv 由纯函数
  `buildSSHArgs` 产出并被逐字断言——「远端到底跑什么」完全由这段 argv 决定。
- `execution` 按 `envprobe.Kind` 路由：`remote` → `Remote`。remote 执行器缺位时
  **在审批之前**拒绝：不烧 token，也不留下一张注定执行不了的待批单。
- 证据：`execution.requested` 暴露 `remote_host` / `remote_port` / `remote_user`
  （批准前可见连哪台机器）；`execution.finished` 与 effect 摘要记 `remote_endpoint`
  （实际连的 host:port）。

### 五个值得记下的判断

1. **fail-closed 的 SSH 连接**：固定 `-o BatchMode=yes` + `-o StrictHostKeyChecking=accept-new`。
   缺密钥立即失败（不卡口令交互提示）、首次连接自动收录主机密钥（不交互也不跳过校验）。
   绝不 `-o StrictHostKeyChecking=no`——那等于把远端机器准入交给第一次连接的运气。
2. **远端执行不声称任何清场结论**。这是前提 4 真正落地点：本地/容器跑完可以说
   「容器清掉了」，但远程进程是我们 `ssh` 拉起来的，它的退出码归我们，而**远端机器上
   的残留（孤儿进程、临时文件）我们并没有去核实**。所以 `provider_remote_zero_residue`
   在真实远程执行后记为 `unknown`（诚实 caliber），**绝不**升级成「已清场」。
   `loopback` / 默认无真实远程 provider 的路径仍保持 `unknown/delegated`，口径不变。
3. **两阶段超时/取消判定序**：先判父 ctx 取消（用户/服务主动停）→ 再判本次超时 →
   最后才看 ExitError。超时文案明确「远端进程可能已成孤儿」——因为 SSH 通道断了
   不代表远端进程一定死，这与本地 `os/exec` 的 kill 语义不同，必须诚实标出来而非
   假装清理了。
4. **`hostPart()` = `user@host`，port 单独 `-p`**。OpenSSH 不支持 `host:port` 写法
   （会整个失败），所以 port 走独立 `-p <port>`，user 拼进 host 段，argv 完全由纯函数
   拼出可测。
5. **`ssh` 二进制缺失即 fail-closed**。解析 ssh bin 失败（系统无 ssh）直接返 error，
   不静默降级到本地跑——那等于「remote 档位实际在宿主执行」，是环境维度和安全边界的
   双重失效。

另外两条执行器层判定：

- ssh 自身退出码（如 255 = 连接/认证失败、缺密钥）是**正常结果**不是 error：
  `Run` 返回 nil error + `ExitCode=255`，由证据层照常记账。只有「连不到 ssh 二进制」
  才算执行器层 error。这把「远端命令跑挂了」和「执行器基础设施挂了」分开记账。
- `sshRun` 包级 var 便于测试注入假 ssh CLI：测试写假 ssh 记录 argv 到 log，可逐字
  断言 `buildSSHArgs` 的拼法（BatchMode / accept-new / `-p` / `-i` / `user@host` /
  command 顺序），不依赖真 ssh 或真网络。

### 前提 4 的修正：remote 落地**触发** `exit_ledger` 断言修正

原 ADR 前提 4：「真执行后该断言必须按证据 caliber 修正——真实环境的清理状态须有可复核
证据，否则保持 unknown」。container 切片落地后我们收窄为「仅 remote 触发」。现在 remote
落地，前提 4 正式收口：

新增 `RecordRemoteProviderExitLedger(runID, endpoint, provider)`：真实远程执行后记录
`provider=ssh` + 真实 `endpoint`（host:port）+ `provider_remote_zero_residue=unknown`。
这是**收窄**而非**放宽**——之前 blanket `unknown/delegated` 把「没有真实远程 provider」
和「有真实远程 provider 但没去核实」混为一谈；现在前者仍是 `unknown/delegated`
（loopback / 默认路径），后者是带真实 endpoint 的 `unknown`（诚实承认没核实残留）。
文件头「永远 unknown/delegated」的注释同步修订，不再一刀切。

### remote 的已知限制（诚实标注）

- 远端残留（孤儿进程、临时文件）未经核实即记为 `unknown`。若未来需要「真清场证明」，
  须在远端跑一段清理脚本并把结果回传证据层，那是一刀独立切片——不在本 epic 内。
- 不在远端做身份校验重写：复用 owner 的 `ClaimEffect` 审批门（前提 3），API 不暴露它。
- 无 ssh config / ProxyJump / 多跳支持；复杂网络拓扑的远端接入是后续切片。
- 凭证（identity_file / 私钥）走配置文件或环境变量，不入证据库、不落 git（R4）。

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
| 零依赖守卫（含 `CGO_ENABLED=0 go build`） | ✅ | `go test ./internal/buildguard/` 全绿；`go.mod` 无新增依赖（docker 走 CLI，未引 SDK） |
| container 环境驱动 run 生命周期，退出码正确记账 | ✅ | e2e（真 docker / `python:3.13-slim`）：`cat /etc/os-release` → `exit=0` / `run.completed`，输出为容器内 Debian（宿主是 macOS）；`sh -c 'exit 7'` → `exit=7` / `run.failed` |
| container 超时不挂死、进 safe 终态 | ✅ | e2e：`sleep 30` + `timeout_sec=2` → `timed_out=true` / `run.safe_stopped`；单测 `TestDockerTimeoutCleansUp` |
| container 执行后不留残留 | ✅ | e2e 每次执行后 `docker ps -a --filter label=zworkbench.execution=1` 为空；`container_cleanup=removed`；单测 `TestDockerSuccessRecordsCleanup` / `TestDockerCleanupFailureIsRecorded` / `TestDockerCleanupAbsentIsDistinct` |
| 容器网络隔离默认生效 | ✅ | e2e：`network=none` 下容器内 `urlopen` 报 `Network is unreachable`（exit 1）；配置层拒绝 `host` |
| 环境维度不被降级（container 档位不会落到宿主执行） | ✅ | 单测 `TestConfirmContainerRoutesToContainerExecutor` / `TestConfirmLocalProfileHasNoContainerSpec`；e2e 步骤 5：container 档位 + local run → 400 |
| remote 环境驱动 run 生命周期，退出码正确记账 | ✅ | 单测 `TestRemoteSuccess` / `TestRemoteNonZeroExitIsResult` / `TestRemoteTimeout` / `TestRemoteBatchModeFailsFast` / `TestRemoteMissingBinary` / `TestRemoteSpecDefaults`；config 成对校验（`validRemote` / `withRemote` / 端口回退 / `Endpoint` 回退）；envprobe bare `remote` → 检查 ssh CLI 可用性；e2e 可经真 ssh 拉起（CI 不跑，依赖真凭证与真网络） |
| 环境维度不被降级（remote 档位不会落到宿主执行） | ✅ | 单测 `TestRemoteRejectsBadSpec`（host 空 / host 含 shell 元字符 / port 越界 / user 含 `@`）；`executorFor` 路由 `KindRemote` → `Remote`；缺 ssh 二进制 fail-closed |
| `exit_ledger` 断言按证据 caliber 修正 | ✅ remote 切片触发 | 新增 `RecordRemoteProviderExitLedger`（provider=ssh + 真实 endpoint + `provider_remote_zero_residue=unknown`，诚实 caliber 非 blanket）；文件头「永远 unknown/delegated」注释已修订；单测 `TestRecordRemoteProviderExitLedger_HonestCaliber` / `_RequiresEndpoint` / `_Once_Idempotent` |

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
| 真实执行容器 | `executor.Docker`（`docker run` CLI + 显式 `docker rm -f` 清场）+ `config.ContainerConfig` | ✅ container 切片 |
| 真实执行远程 | `executor.Remote`（`ssh` CLI + `BatchMode=yes` + `StrictHostKeyChecking=accept-new` fail-closed）+ `config.RemoteConfig` | ✅ remote 切片 |

## Status

ACCEPTED 2026-10-26（zj 拍板三项后首刀落地；同日补 container 切片；同日补 remote 切片并收口前提 4）。

- **已落地（首刀）**：local 环境的真执行 + 白名单档位 + 审批门 + owner 记账 +
  API + 前端面板。三条终态路径（completed / failed / safe_stopped）均经真实
  server 的 e2e 验证，零依赖守卫全绿。
- **已落地（container 切片）**：`container` 环境真执行（docker CLI，不经 SDK）+
  容器参数校验（image / workdir / network / user / env）+ 按环境路由执行器 +
  显式清场与三态清场证据 + 前端暴露镜像与清场结论。真 docker e2e 30 项全通过。
- **已落地（remote 切片）**：`remote` 环境真执行（ssh CLI，不经 SDK）+ remote 参数
  校验（host / port / user / identity_file）+ 端点不拼进环境名（bare `remote` +
  `RemoteConfig` 段成对校验）+ 按环境路由执行器 + fail-closed SSH 连接
  （`BatchMode=yes` + `StrictHostKeyChecking=accept-new`）+ 前端暴露远端信息与
  `remote_endpoint`。`executor.Remote` 单测 8 项全过（成功 / 非 0 退出 / 超时 /
  缺密钥快速失败 / 缺二进制 / 默认值），config / evidence / execution / envprobe
  配套单测全过。
- **前提 4 收口**：remote 切片落地后 `exit_ledger` 断言正式按证据 caliber 修正——
  新增 `RecordRemoteProviderExitLedger`（provider=ssh + 真实 endpoint +
  `provider_remote_zero_residue=unknown`，诚实 caliber 非 blanket）；
  `loopback` / 默认路径仍保持 `unknown/delegated` 不变。文件头注释同步修订。
- 本 epic 四前提（执行器抽象 / 超时取消日志 / 审批门 / exit_ledger 对齐）全部满足。
