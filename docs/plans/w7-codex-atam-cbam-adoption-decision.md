# W7 Codex C1–C7 ATAM/CBAM 采用姿态决策

评审状态：`acceptance/evaluation` · 评审日期：`2026-08-31` · 决策 owner：个人开发者/小团队负责人

## One-page overview

### Decision

Decision: defer production adoption; conditionally retain Codex as the single primary Harness for a controlled implementation/pilot.

未解决发现分为两类：

- `blocking`（对生产采用/不可逆真实副作用阻断）：C4 组合式 approval path 已通过，
  但 Codex 原生 approval boundary 仍为 `unknown`；C7 真人安装、升级/回滚和人工时间尚未完成；source-to-binary provenance、
  NOTICE 与商业边界尚未完成审查；C2 宿主级强制边界仍未签字。
- `non-blocking`（对受控、无真实副作用的继续评估不阻断）：没有第二 Harness 的
  C2–C7 增量证据；Codex `app-server` 帮助标记为 experimental；C3/C5/C6 已有的
  composition 结果仍需随版本回归。

因此“保留为主候选”不等于“已经采用”。在 blocking findings 关闭前，只允许固定版本、
case-local 或经明确批准的受控试点；不允许把 Codex、薄 adapter 或测试 fixture 宣称为
完整生产工作台。

### Summary

W7 的证据支持“Codex 执行内核 + 一个必要的外部薄 composition owner”的最小路线：
Codex 复用代码执行能力，composition owner 统一承接安全账本、定时/幂等、Provider
故障切换、canonical event/replay 和生命周期证据。C1、C2 scripted path、C3、C5、C6
的局部合同已经通过；C4 的组合 owner 已明确，但 Codex 原生 approval 语义与 C7 真实生命周期成本仍未关闭，所以当前是
“条件保留、延迟生产采用”。

### Platforms and scope

- 候选：Codex Harness，`codex-cli 0.139.0`。
- 固定 identity：release `rust-v0.139.0`，peeled commit
  `a7dff904308535e965aee87680c1fc5ef1d19eec`，本机 Darwin arm64。
- 评估入口：本机 `/opt/homebrew/bin/codex` 与 `codex app-server` over stdio。
- 数据/代码面：C1–C7 evaluation fixtures、candidate manifest、run summaries、
  event/effect/replay/operation ledgers；本轮不改 ZWorkbench 产品代码。
- 明确排除：真实生产项目、真实 Provider/凭证、全局 `CODEX_HOME`、真实外网升级、
  不可逆外部副作用；C7 的真实安装/升级/回滚尚未被本轮执行。

### Ownership and tracking

| 责任面 | 暂定 owner | 采用前必须确认 |
|---|---|---|
| Agent execution loop / app-server | Codex Harness | 固定版本和入口回归；不把外部 adapter 结果算作 Codex 原生能力 |
| Run identity、schedule、幂等、retry、effect/result ledger | 单一 composition owner | 不能由多个组件各自生成 truth；C3/C4 关联字段必须保持兼容 |
| approval、危险动作和凭证 | 一个明确的 policy/approval owner | 在 C4 中证明 request/decision/effect 关联；在关闭前 fail-closed |
| Provider routing、capability、fallback/degradation | composition owner | 记录 provider/model/endpoint/reason；不得 silent switch |
| canonical events、replay mode、环境快照 | composition owner | `recorded_view`、`simulated_replay`、`live_replay` 分离，live 默认 deny |
| 版本、许可证、发布 provenance | 候选供应链/项目维护者 | 完成 NOTICE、商业边界和 artifact provenance 审查 |
| 人工运维与最终采用 | 个人开发者/小团队负责人 | 完成 C7 runbook、stopwatch 和 rollback/exit 签核 |

证据总索引：`evaluation/runs/` 下的 C1–C7 summaries，以及
[`W7 roadmap`](./personal-workbench-w7-roadmap.md)。

## Problem and goals

### User/job and baseline

目标是建立一个个人工作台，用于完成代码与通用任务、自动/定时运行、集成个人项目、
观测/回放/评测/调试、多 Provider 和高质量代码开发。W6 的候选无关 fixture 证明了
评估合同可执行，但不能直接证明某个 Harness 的完整采用；W7 将同一合同接到固定
Codex 版本，形成了候选级证据。

当前基线事实：

- C1：Codex 在 fake-a/fake-b 上各 `5/5`，即候选 smoke `10/10`；这是代码闭环局部
  证据，不是安全、恢复或运维通过。
- C2：W6 C2 adapter 在 Codex scripted path 上 `15/15` 无人审批动作被阻断，关键
  拦截率 `100%`，未授权执行 `0`；宿主级绕过、任意 plugin/MCP/子进程路径仍未签字。
- C3：固定 Codex 的外部 deterministic trigger + 单一 durable owner 为 `15/15
  pass-with-composition`；同 key 有效副作用为 `1`，重复额外副作用为 `0`，但
  Codex 原生 scheduler 未测量。
- C4：组合式 approval/recovery 为 `36/36 pass-with-composition`，状态丢失 `0`、
  危险副作用重复 `0`、最大 retry `1`，未授权/scope/token replay effect 均为 `0`；
  Codex 原生 approval request `0/36`，继续为 `unknown/not-required-for-composition`。
- C5：双 Provider fallback/capability/degradation 为 `19/19
  pass-with-composition`；silent semantic change `0`。
- C6：三种 replay mode 为 `15/15 pass-with-composition`；必需事件字段和 mode label
  `100%`，simulated replay 期望匹配 `5/5`，live replay side effect `0` 且默认拒绝。
- C7：六类 case-local 场景各重复 `3` 次，共 `18/18 machine pass`；exit 为 `3/3`
  零残留，但真人 stopwatch、真实 install、upgrade/rollback、NOTICE/商业审查和
  source-to-binary provenance 仍为 `unknown/stop`。

### Goals

- 基于同一 C1–C7 证据链决定 Codex 是继续保留、条件采用还是退出。
- 明确 Codex 原生能力与 composition-owned 能力的边界及唯一责任人。
- 用 ATAM 识别阻断风险、敏感点和权衡点；用 CBAM 比较最小组合与新增组件成本。
- 给出可自动持续评估的指标、回归信号、停止条件和恢复/退出路径。
- 保持个人开发者或小团队约束：维护服务 ≤3、无需额外专家、人工操作阈值可测。

### Non-goals

- 不在本节点实现 ZWorkbench 产品功能、adapter、broker、scheduler 或观测后端。
- 不把测试 fixture 的 pass 当作生产安全、商业合规或真实 Provider 质量保证。
- 不为“功能更多”引入第二 Harness、Temporal/LangGraph、LiteLLM、Langfuse/Phoenix/
  Inspect AI/OTel 或从零重写 Agent loop。
- 不在没有明确批准和安全 owner 的情况下执行真实凭证、真实部署、外网升级或不可逆
  副作用。

### Assumptions and constraints

- 评估对象是个人工作台，优先单一操作者和小团队可维护性，而非多租户平台。
- C3–C6 的通过必须标记 `pass-with-composition`，不能提升为 Codex 原生通过。
- C4 native approval boundary、C7 真人时间、法律边界和 provenance 的未知不会被平均分抵消。
- 任何新增组件都必须重新计算 C2–C7 的服务、依赖、升级、备份、排障和退出成本。

## Design

### Alternatives considered

| 选项 | 价值 | 主要代价/风险 | 决定 |
|---|---|---|---|
| Codex + 一个薄 composition owner | 复用已验证的代码执行内核；一个 owner 统一 durable、policy、routing、replay 和 evidence | adapter schema、版本回归、ledger 备份与退出责任集中在小团队 | **保留为条件主路线** |
| Codex + 第二 Harness | 可能增加另一种代码/工具能力 | 复制状态、权限、Provider、事件、升级和退出矩阵；没有 C2–C7 非重复收益证据 | 暂缓 |
| Codex + Temporal/LangGraph/scheduler | 可能增强 durable workflow、schedule、retry | 新常驻服务、状态迁移、备份、排障和学习成本；当前轻量 composition 尚未证明不足 | 暂缓 |
| Codex + LiteLLM/router | 可能减少 Provider 接入与 fallback 代码 | 网关单点、secret、协议转译、能力等价性和 C7 运维成本；C5 当前 router 仍是 fixture/composition | 暂缓，除非有增量成本证据 |
| Codex + 独立观测/评测后端 | 查询、数据集或评测可能更方便 | 存储、隐私、retention、许可证、退出；C6 自有 ledger contract 尚未被证明不够 | 暂缓 |
| 从零自建 Agent loop | 最大控制权 | 最大实现/测试/模型/工具兼容与长期维护成本；没有 C1–C7 的必要性证据 | 排除 |

### Chosen design and seams

选择“一个主 Harness + 一个薄 composition owner”，但只作为受控试点架构基线：

```text
schedule / manual trigger
          │
          ▼
single composition owner
  ├─ run/schedule/idempotency/effect/result ledger
  ├─ policy/approval boundary (composition gate pass; native/host boundary remains fail-closed)
  ├─ Provider capability/fallback ledger
  ├─ canonical events + replay mode policy
  └─ backup/restore/export/diagnosis/exit metadata
          │ stdio app-server
          ▼
Codex 0.139.0 execution loop
          │
          ▼
case-local worktree / explicitly approved side effects
```

边界约束：

1. Codex 负责执行循环和其原生工具/沙箱表面；外部 owner 不复制 Agent loop。
2. composition owner 负责跨 Run 的 identity、durable state、幂等、Provider 和 replay
   ledger；所有 C3–C6 的 `composition` 标签必须保留。
3. approval 必须只有一个可追责的控制 owner。组合式 gate 已在 C4 通过；在 Codex
   原生/宿主边界被单独接受前，危险或 approval-required 路径仍只能经该 gate 并在
   未知时 safe-stop；C2 的 scripted pass 不能填补原生 request 缺失。
4. replay 必须显式标注 mode：记录查看、cassette-only simulated replay、live replay。
   live replay 默认 deny；禁止用 trace/view 冒充执行回放。
5. 先保持 case-local、可导出、可删除的 ledger；不引入独立观测平台作为第二 truth。

### Compatibility, failure handling, migration and ownership

- **版本兼容**：绑定 release tag、peeled commit、wrapper/package/platform/binary
  digest、tool schema、Provider 配置和 runner/fixture hash；任一变化触发 C1–C7
  回归。`app-server` 帮助当前标记为 experimental，不能假设协议无漂移。
- **失败处理**：未授权或 approval owner 不可见时 deny/safe-stop；中断恢复先 reconcile
  effect ledger，再 bounded retry；Provider fallback 必须记录 reason/target；replay
  没有显式批准不得 live 执行。
- **迁移/回滚**：保留旧 candidate identity、composition ledger schema 和 backup；
  先在 case-local 或复制环境验证新版本，再切换；若失败，停止新触发、恢复 ledger、
  回到上一固定 release。当前真实升级/回滚尚未演练，这仍是计划而非证据。
- **退出**：导出 canonical metadata、ledger schema、Provider/策略引用和 artifact
  identity；独立 re-import 校验；删除本地与外部资源并检查 retention。当前仅有
  case-local exit 机器证据，真实账户和远端 retention 仍需审计。

## Metrics and experiments

以下把“观察到的事实”“推断”和“未知”分开。各项的 `baseline`、`unit`、`method`、
`target/threshold` 和 owner 均明确记录；未知不作为零或通过。

| 指标 | baseline | unit | method | target/threshold | owner | 解锁的决定 |
|---|---|---|---|---|---|---|
| C1 code-loop pass rate | Codex fake-a/b 各 `5/5` | cases | 固定 fixture、Provider、允许 diff、test/result ledger | 继续评估要求 `100%`；版本变更不得回退 | execution/evaluation owner | 代码执行内核可保留 |
| C2 critical interception | `100%` scripted；未授权执行 `0` | rate/count | 五类危险动作各 `3` 次，核对 sink、secret、remote、deploy oracle | rate `100%`，count `0`；宿主级边界仍需单独证据 | policy owner | 可进入受控试点；不签完整安全 |
| C3 effective effect per key | `1`；duplicate extra `0` | effects/key | deterministic trigger + durable ledger，五场景各 `3` 次 | exactly `1` effective effect/key；extra `0` | composition owner | 允许轻量 durable seam；不签原生 scheduler |
| C4 critical state loss | composition run `36/36`；state loss `0`；unsafe duplicate `0`；native approval `unknown` | count/cases | 四故障点 × 三工具类 × 三次；中断后 reconcile/resume/retry + token controls | state loss `0`、unsafe duplicate `0`、retry ≤`1`；composition approval evidence complete `100%`；native approval unknown 不得提升 | approval/composition owner | composition path 可继续；native approval 与 C7 关键门仍保持 stop |
| C5 silent semantic change | `0`；`19/19` composition pass | cases/events | normal A/B 各 `5`，三类故障各 `3`，记录 capability/fallback | silent change `0`；fallback reason/target `100%` | Provider owner | 允许显式降级；不默认 LiteLLM |
| C6 replay safety | `15/15` composition pass；live side effect `0` | cases/effects | 三 mode 各 `5`；字段、mode、Provider/tool counter、effect guard | required fields/mode `100%`；simulated match `5/5`；live side effect `0` | replay/evidence owner | 保留自有 replay contract |
| C7 machine contract | `18/18` pass；exit `3/3` zero residue | cases/residue | 六场景各 `3` 次；隔离目录、事件、服务和退出 oracle | machine cases `100%`；services ≤`3` | operations owner | 仅证明评估资产可运行 |
| C7 human operation time | `unknown`，未提供 stopwatch | minutes | 单一操作者按固定 runbook 实测，不能使用 subprocess time | install ≤`90`；upgrade/restore/diagnosis 各 ≤`30` | single operator | 关闭 C7/G7 签核 |
| maintained services | `2`（candidate runtime + one composition owner） | services | service/dependency manifest；明确排除 host OS、Node、fake test service | ≤`3`；额外专家 `false` | operations owner | 超限时重做 CBAM |
| release provenance | tag/commit 和 local digest pass；source→binary `unknown` | identity/build attestations | 固定 commit、package/binary digest、release/build attestation 和独立重建 | 可复核 source-to-binary provenance；当前未满足 | supply-chain owner | 关闭发布/升级阻断 |

### Continuous evaluation policy

在以下任一变化后重跑受影响的 C1–C7，并保留新的 immutable run identity：Codex release/
binary、app-server schema、sandbox/approval 配置、Provider/模型/endpoint、composition
schema、policy、replay mode、依赖或常驻服务拓扑。

自动停止条件：事件完整率低于 `100%`、关键拦截率低于 `100%`、任何未授权执行、状态
丢失、危险副作用重复、live replay 未批准执行、Provider silent semantic change、
service count 超过 `3`、需要额外专家、人工时间超阈值或 artifact identity 漂移。
停止后只能输出 `unknown/stop` 或 `fail`，不能用其他场景平均值抵消。

## Rollout, recovery, and lifecycle

### Rollout stages

1. **Stage 0 — evaluation only（当前）**：固定 Codex `0.139.0`，case-local fixture，
   fake/loopback Provider，禁止真实凭证和不可逆副作用。当前 C7 审计在此阶段完成。
2. **Stage 1 — controlled pilot（条件允许）**：仅在显式绑定单一 approval owner、
   C2/C4 关键门和最小 composition owner 后，用可恢复、可审计的个人任务验证；每个
   Run 关联 schedule/run/thread/turn/effect/result identity，并保留 replay/backup。
3. **Stage 2 — private daily use（待门关闭）**：完成真实单人 C7 runbook、人工时间、
   升级/回滚、许可证/NOTICE 和 provenance 审查后，才考虑个人工作台的日常真实数据。
4. **Stage 3 — broader release（本路线不自动承诺）**：若涉及分发、团队共享、商业
   使用或生产外部系统，必须重新做法律、凭证、数据保留、宿主隔离和多用户运维评审。

### Pause and rollback triggers

- 任意 C2/C4/C6 自动停止条件触发；未知不能被解释为安全。
- Codex、Provider、tool schema 或 composition schema digest 与已签核 identity 不一致。
- 升级后 ledger 无法恢复、replay mode 边界变化、fallback 原因缺失或事件字段缺失。
- C7 人工时间超阈值、维护服务超过 `3`、需要额外专家，或真实退出无法导出/删除。

恢复动作：停止新 schedule/trigger，禁止 live replay 和危险 tool，reconcile effect/result
ledger，保留故障 run，恢复最后已知固定版本和备份；不能安全确认副作用状态时
safe-stop 并人工处理。由于真实 rollback 尚未演练，Stage 2 前必须先完成一次可复核
rollback rehearsal。

### Lifecycle and cleanup

每个 release 保留：候选 manifest、源码/二进制 identity、依赖与许可证清单、policy/
tool/provider/replay schema、run summary 和 failure evidence。退出时先导出可读且版本化
的 metadata/ledger，再独立导入验证，最后删除本地、远程和 retention 范围内资源；删除
动作必须有 scope 和结果记录。C7 当前只证明 case-local 零残留，不能替代真实退出演练。

## Principle considerations

### Performance

本节点不做 Token、Provider 延迟或资源容量结论。W6/W7 C1 的候选执行时间只可作为
局部命令基线，不能充当人工运维时间或生产成本。后续需在同一评测集、固定模型和
Provider 下分别记录 wall time、token、fallback 次数、存储增长和人工介入；性能
回归不能抵消安全或恢复门失败。

### Simplicity and accessibility

“一个主 Harness + 一个薄 owner”减少个人开发者需要理解的运行时数量，并避免第二
Harness 复制权限/事件/升级责任；代价是 owner 的 schema、备份和故障诊断责任集中。
安装、升级、恢复、排障 runbook 必须由单一操作者可执行并按 stopwatch 验证。当前
没有证据证明已达到该目标；人工时间保持 `unknown`。

### Security and privacy

威胁面包括模型生成命令、任意 shell/plugin/MCP、Provider 请求、凭证、网络、Git/deploy
和 replay 误执行。信任边界是 composition policy/ledger、Codex app-server/sandbox、
宿主系统和外部 Provider/副作用系统；必须有唯一 approval owner、最小 scope、一次性
attempt/effect identity、凭证脱敏和 retention/deletion 规则。

C2 scripted path 的 `15/15` 阻断、C6 live replay default-deny 和 case-local 零副作用
是局部证据；它们不证明宿主级强制隔离、真实凭证安全或任意 tool surface 安全。C4
native/host approval boundary unknown 时，真实危险动作只能经组合 gate deny/safe-stop。

## Testing and validation

| 层 | 可复现场景/fixture | 当前结果 | 放行含义 |
|---|---|---|---|
| C1 | `evaluation/runs/w6-0.1-baseline-20260830T144245-541564Z/summary.json` 的 Codex fake-a/b | 各 `5/5` | 只放行代码闭环候选基线 |
| C2 | `evaluation/runs/w6-0.1-c2-20260830T144743-847310Z/summary.json` | scripted path：`15/15` blocked、100% interception | 受控负向路径通过；宿主强制边界未签核 |
| C3 | `evaluation/runs/w7-codex-c3-c4-20260830T162343-560708Z/summary.json` | `15/15 pass-with-composition` | 允许单一 durable owner 继续验证 |
| C4 | `evaluation/runs/w7-codex-c4-approval-20260831T032346-194000Z/summary.json` | `36/36 pass-with-composition`；native approval `unknown` | 组合 owner 已关闭；原生 approval 与 C7/合规仍为生产阻断 |
| C5 | `evaluation/runs/w7-codex-c5-c6-20260830T165759-141575Z/summary.json` | `19/19 pass-with-composition` | 允许显式 fallback；不宣称 Codex 原生 routing |
| C6 | `evaluation/runs/w7-codex-c5-c6-20260830T165822-636804Z/summary.json` | `15/15 pass-with-composition` | 允许 canonical ledger；live 默认拒绝 |
| C7 | `evaluation/runs/w7-codex-c7-20260831T032735-294299Z/summary.json` | `18/18 machine pass`；overall `unknown/stop`；exit `3/3`；绑定最新 C4 identity | 生产阻断；先补真人、真实生命周期和合规/供应链证据 |

测试规则：每个新 release/config/provider/schema 至少重跑受影响场景；每类 C7 操作
按既定重复次数执行；任何关键字段缺失、identity 漂移或副作用 oracle 非零均
`fail`/`unknown-stop`。本节点没有修改产品代码，因此这些测试只验证候选与评估资产，
不验证尚未实现的 ZWorkbench。

## Open decisions

| Question | Evidence needed | Owner | Due/exit condition |
|---|---|---|---|
| approval owner 最终由谁持有？ | 固定 Codex tool path 上由单一 composition owner 持有业务 approval，并关联 request/decision/effect；Codex native approval 单独记为 unknown | 个人工作台负责人 + policy owner | composition approval evidence `100%`；native approval unknown 不得被回填或隐藏 |
| 是否执行真实候选 install 与 upgrade/rollback？ | 隔离但真实的 runbook、版本/配置兼容、旧版本恢复和 artifact identity | 单一操作者 | install ≤`90` 分钟；upgrade/rollback 可复现且无 ledger 损坏 |
| C7 四类人工时间是否达标？ | 单一真实操作者 stopwatch、等待/介入/专家记录 | 小团队负责人 | install ≤`90`；upgrade/restore/diagnosis 各 ≤`30`；无额外专家 |
| Apache-2.0 之外的 NOTICE、依赖和商业边界如何签核？ | 发布包完整 license/NOTICE inventory、商标/API/商业使用审查 | 项目维护者/合规 owner | review 从 `unknown` 变为有签核记录；分发前必须完成 |
| 本机 binary 是否可追溯到固定源码？ | build recipe、source/artifact digest、attestation 或独立重建 | 供应链 owner | source-to-binary provenance 可复核；否则只允许 release-level 评估 |
| 是否需要第二 Harness、LiteLLM、Temporal 或观测平台？ | 同一 C2–C7 矩阵上的非重复收益、服务数、人工工时、退出成本 | 架构决策 owner | 只有明确收益超过增量成本才重开 CBAM；否则不引入 |
| app-server experimental surface 是否可接受？ | 版本回归、协议 schema diff、失败/回滚记录 | execution owner | 连续评估证明 schema/入口稳定，或将其隔离在可替换 seam |

## Review record

| Reviewer | Date | Concern | Response or decision | Remaining risk |
|---|---|---|---|---|
| Codex evaluation agent | 2026-08-31 | C1/C5/C6 局部通过可能被误读为完整采用 | 采用姿态设为 `defer`；仅条件保留 Codex 主候选和一个薄 owner | C4/C7/合规/provenance blocking |
| Codex evaluation agent | 2026-08-31 | 个人开发者无法承担多组件维护与重复 truth | 暂不引入第二 Harness、Temporal/LangGraph、LiteLLM 或独立观测平台；服务上限≤3 | 真实 C7 工时与服务拓扑仍未测 |
| Human owner | 待确认 | 是否接受“条件主候选、生产 defer” | 待 Human 确认；本文件不代替采用签字 | 所有 blocking findings |

### Short-read acceptance

本评审的当前决策是 `defer`，不是生产批准。下一验证动作是由单一真实操作者在固定
Codex `0.139.0` 上完成 install、upgrade/rollback、backup/restore、fault diagnosis
runbook 并记录 stopwatch，同时确认组合 approval owner 和原生/宿主边界不被混淆；硬阈值为安装 ≤`90` 分钟，
其余三项各 ≤`30` 分钟，维护服务 ≤`3`，无额外专家。完成前维持
`unknown/stop`，所有真实危险动作 fail-closed。
