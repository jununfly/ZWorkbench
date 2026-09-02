# W8：`dsh-config-migrate` dynamic-plugin adapter 设计审查

路线：`1-8-3` · 类型：`acceptance/evaluation` · 日期：2026-09-02
证据：[E1/E2 runner](/Users/bilibili/Documents/workspace/github/jununfly/ZWorkbench/evaluation/runner/run_deepseek_config_migrate_adapter.py) · [fixture manifest](/Users/bilibili/Documents/workspace/github/jununfly/ZWorkbench/evaluation/fixtures/w8-deepseek-config-migrate-adapter/v1/manifest.json) · [首轮四插件结论](./w8-deepseek-plugin-bundle-e1-e6-findings.md)

## One-page overview

### Decision

Decision: revise。本设计允许 `dsh-config-migrate` 作为 outer-composed、
fail-closed dynamic-plugin adapter 候选进入下一道 plugin-aware 验证；当前不批准
产品集成，也不把它改写成 `dsh.bundle`。本轮 E1/E2 的 blocking 约束是运行时
adapter 尚未实现/验证、任意 subprocess 必须有 pinned-script + OS sandbox、以及
插件写入必须经过 owner/policy gate。non-blocking 观察包括 client UI 不参与本轮
headless E3/E6、动态插件没有独立 package artifact。

### Summary

`dsh-config-migrate@1.0.0` 提供的是 Cordis `dsh.plugin.host/client` 函数体，能够
迁移 DSH_HOME 配置、凭据、profile 和 external plugin，但不是 DeepSeek Harness
标准 bundle。adapter 只把它作为受控能力提供者：加载和注册由 adapter 负责，配置
迁移数据使用独立 namespace，ZWorkbench composition owner 仍是 run/effect/event/
replay 的唯一 durable truth。

### Platforms and scope

- 输入：固定 checkout `24aa64188386181bdaf21f4b46fea02bddf77e71`、`1.0.0`、MIT；
  入口为 `host.js` / `client.js`。
- 本轮环境：case-local bundle root、case-local DSH_HOME、headless profile；不
  安装 npm、不启动 Harness、不访问网络、不使用真实 Provider/凭据/生产数据。
- 受影响的评估面：dynamic loader seam、capability facade、profile binding、
  adapter-owned registration 和 migration namespace。
- 明确排除：ZWorkbench 产品运行时修改、四插件 bundle 重写、真实 DSH_HOME 写入、
  E3–E6 执行、远端任务/Webhook/备份和真实 Provider 责任。

### Ownership and tracking

- 决策 owner：ZWorkbench 项目 owner（Human）。
- 评估 owner：当前 Codex agent；证据复核：Human。
- 运行时 owner：未来若实现，由 ZWorkbench adapter maintainer 负责；插件作者不
  取得 canonical owner 权限。
- 相关路线节点：`docs/plans/personal-workbench-w8-roadmap.json` 的 `1-8-3`。

## Problem and goals

首轮四插件组合因 `dsh-config-migrate` 不声明 `dsh.bundle` 而在 E1 fail-closed。
直接把它塞进标准 bundles 会隐藏 ABI 差异；直接执行其动态函数体又会把
`DSH_HOME` 写入、凭据处理、Node 子进程和链接重建带入 Harness 权限面。

Goals：

1. 固定并复核 package identity、commit、version、host/client 入口和 license。
2. 定义一个不改变插件源码合同的 outer-composed adapter seam。
3. 将 `ctx`、host/client bridge、文件系统、设置和 subprocess 收口到 allowlist。
4. 保持 migration state 与 ZWorkbench canonical state 分离，并给后续 E3–E6 留下
   可重现的 request/result/registration 记录边界。
5. 在隔离、parse-only 的 E1/E2 中证明“可进入下一轮”，但明确不虚报运行时安全。

Non-goals：

- 不把动态插件转换成 `dsh.bundle`，不修改上游 checkout。
- 不让插件拥有 run/effect/event/replay、backup manifest 或 provider ledger。
- 不在本轮实现 product adapter，不接真实 API key，不验证真实远端退出。
- 不因 E1/E2 通过而继承 Codex 或 ZWorkbench owner 的 E3–E6 证据。

约束：个人开发者/小团队可维护；常驻服务不增加；所有未知权限、未知 effect、
路径逃逸和未验证子进程都必须 fail-closed。验收基线和阈值来自 [W8 首轮
fixture](../evaluation/fixtures/w8-deepseek-plugin-bundle/v1/manifest.json)。

## Design

### Alternatives considered

| 选项 | 判断 | 原因 |
|---|---|---|
| 把动态函数体改写为 `dsh.bundle` | reject | 会改变上游 ABI，破坏 provenance，并把 adapter 责任伪装成插件能力。 |
| 直接让 DeepSeek Harness 执行 host/client | reject | 插件可请求配置写入、凭据处理和 Node 子进程；无法证明 owner/policy/OS 边界。 |
| outer-composed adapter + capability facade | chosen / revise | 保留生态差异化能力，新增一个可审查 seam；代价是 adapter 需要维护 ABI、权限和生命周期。 |
| 在 ZWorkbench 内重写全部配置迁移能力 | defer | 控制面更简单，但重复上游功能，失去本次生态挑战的验证价值；只有 CBAM 证明净收益时再考虑。 |

### Adapter seam

运行时实现（本轮只定义，不实现）应暴露以下逻辑接口：

```text
load(pinnedPlugin, caseContext) -> AdapterHandle
inspect() -> identity + contract + capabilities + provenance
callRpc(name, args, requestContext) -> adapter-owned request/result record
callTool(name, args, requestContext) -> adapter-owned request/result record
dispose() -> unregister everything + remove temporary resources
```

加载流程：

```text
pinned manifest
  → commit/package/version/path verification
  → parse-only host/client validation
  → create case-local facade
  → register wrapped RPC/tool/UI callbacks
  → record request/result under owner run identity
  → policy gate before every write
  → dispose and verify no registration/resource leak
```

adapter 不应把 dynamic plugin 放入 `dsh.profile.bundles`。profile 可以保留 local
dependency reference 作为输入，但 dynamic plugin 的存在必须在 adapter manifest
中显式登记；标准 bundle loader 不得静默接管它。

### Stage 1 runtime probe result

在相同 pinned checkout 和 case-local root 上，runtime probe 已实际加载 host/client
函数体并完成 RPC、tool、UI slot 和 style registration。结果为 `pass`：

- `config/status` 成功返回 case-local 清单；未知 RPC 返回 `ADAPTER_UNKNOWN_RPC`。
- export/import/tool 写路径均被 adapter 拒绝；import 覆盖场景捕获插件请求的
  `mode: danger-full-access`，实际 policy 为 `adapter-controlled-deny`，没有落盘。
- pinned `node -e` crypto script 通过 hash allowlist；Python/shell probe 被拒绝。
- dispose 后 RPC/tool/UI/style 注册数从 `4/1/2/1` 归零；owner 记录 7 个 adapter
  request/result，run 完成且 effect 数为 0。

证据：[runtime seam summary](/Users/bilibili/Documents/workspace/github/jununfly/ZWorkbench/evaluation/evidence/w8-deepseek-config-migrate-runtime-seam-20260902-rerun4/summary.json)。这只证明
case-local runtime seam 的候选边界；真实 DSH_HOME 写入、宿主级 OS sandbox 继承和
产品 adapter 仍未签核。

### Capability facade

| 插件请求面 | adapter 暴露 | 强制边界 |
|---|---|---|
| `ctx.get('fs')` | `resolve/stat/listDir/readText/readBytes/writeText` | 所有路径必须在 case root；写前 owner/policy gate；拒绝 `..`、绝对外部路径和插件自带 policy widening。 |
| `ctx.get('settings')` | `prepareDocument` | 仅用于识别 case-local DSH_HOME；不把宿主真实 settings 文档暴露给插件。 |
| `ctx.get('sandboxPolicy')` | adapter-owned policy context | 插件传入的 `mode: danger-full-access` 必须被忽略并替换，不能扩大权限。 |
| `ctx.get('subprocess')` | `node` only、无 shell、case-root cwd | 仅允许 pinned source 生成且经 adapter 验证的脚本；子进程需 OS sandbox；network/env/credential deny。 |
| `harness.handle/defineTool/registerTool` | wrapped bridge | registration、RPC、tool result 都挂到 adapter request id，并由 `dispose` 撤销。 |
| `ctx.get('slots')`、`styles`、`React` | client-only UI bridge | 不可获得 host 文件/凭据能力；UI callback 只能调用 wrapped host RPC。 |

当前插件的 export/import 语义确实需要写配置、AES 加密和链接重建。因此不能用
“插件代码没有危险操作”作为假设；必须记录其 `danger-full-access` 请求、内嵌
Node `fs` 脚本和 credential 处理，并在运行时以 pinned-script verifier、子进程
隔离和 owner gate 作为前提。若任一前提未实现，adapter 返回 `blocked`。

### State and ownership

| 状态 | canonical owner | dynamic plugin 可见范围 | 备份/回放 |
|---|---|---|---|
| run/thread/turn/effect/result/event/replay | ZWorkbench composition owner | opaque request context / correlation id | owner schema 与 owner backup/restore |
| migration export/import request | adapter | 当前调用的 args、allowlisted file view | adapter request/result ledger；不能伪装成 owner effect |
| 配置迁移包和 `.dshmig-state.json` | adapter namespace / case-local DSH_HOME | 仅 allowlisted migration files | 单独迁移包；不加入 owner canonical snapshot |
| Provider identity / credentials | owner ledger 记录引用和 policy outcome | 本轮 deny；未来显式 scoped handle | 不保存真实 secret；不得被 replay 复用 |

`dsh-config-migrate` 的配置备份不是 ZWorkbench composition backup。只有 owner 自己
生成的 manifest/database/state snapshot 才能满足 owner backup/restore；插件迁移包
最多作为一个经 policy 批准的外部 artifact 被记录。

### Compatibility and lifecycle

- 只接受 manifest 绑定的 host/client 相对路径和 pinned commit；入口或 package
  metadata 变化即重新 E1/E2。
- adapter version、plugin commit、profile identity 和 capability policy 必须同
  时写入 evidence；不允许 alpha core 与其他 ABI 混装。
- `dispose` 必须撤销 host RPC、tool、UI slot 和临时文件；泄漏则 E2 fail。
- 升级先生成新 identity 和静态 parse evidence；旧 adapter 仍保持 disabled，直到
  E1/E2 通过。回滚到旧 adapter 只读旧 namespace，不覆盖 owner state。
- 卸载删除 case-local migration state 和 registration；真实 DSH_HOME、远端数据、
  Provider 账户与 retention 不由本 adapter 代为声称已删除。

## Metrics and experiments

以下指标都有 baseline、unit、method、target/threshold 和 owner。当前 baseline
来自固定 commit 的本地 fixture；“未知”单独记录，不当作 absence。

| 指标 | baseline | unit | method | target/threshold | owner |
|---|---|---|---|---|---|
| E1 identity match | 首轮 dynamic package commit `24aa641…` | checks | `git rev-parse` + commit `git show package.json` | 100% | evaluation owner |
| E1 entry parse | `host.js`、`client.js` 两个函数体 | entrypoints | Node `new Function()` parse-only | 2/2；不执行 | evaluation owner |
| E1 profile binding | profile 中有 dependency、无 bundle 声明 | package fields | 读取 case-local profile JSON | dynamic plugin in bundles = 0；adapter id/version 有记录 | adapter maintainer |
| E2 capability closure | 观察到的 ctx/bridge/service 调用 | declared operation | regex ledger + manifest allowlist diff | 未知 capability = 0；全部声明 | adapter maintainer |
| E2 side effects | 本轮 runner | count | runner process contract | registry/network/real credential/external effect = 0；owner DB touch = 0 | evaluation owner |
| E2 provenance | source commit + tree；无 package artifact | records | local Git object + SHA-256 entry source | source identity 100%；artifact absence explicit；不宣称 reproducible build | project owner |
| Stage 1 owner correlation | runtime probe | request/result records | real plugin callback + CompositionOwner snapshot | 100% request IDs recorded；effect=0；run correlation 100% | adapter maintainer |
| Stage 1 disposal | RPC/tool/UI/style registrations | counts | runtime probe before/after dispose | after dispose `0/0/0/0`；泄漏即 blocking | adapter maintainer |

可重现命令：

```bash
python evaluation/runner/run_deepseek_config_migrate_adapter.py \
  --bundle-root /private/tmp/zworkbench-deepseek-plugin-bundle.HVvyGR \
  --output evaluation/evidence/w8-deepseek-config-migrate-adapter-e1-e2-20260902
```

证据至少包含 `adapter-manifest.json`、`source-ledger.json`、`summary.json`；运行
输出必须明确 E3-E6 未由本 runner 执行，不能把 E1/E2 或 runtime seam 结果包装成完整 bundle 通过。

## Rollout, recovery, and lifecycle

### Stages

1. **Stage 0（本轮）**：静态 identity、入口 parse、capability ledger 和 profile
   binding；通过后获得“可重开”资格。
2. **Stage 1（本轮已完成）**：在同一 case-local root 加载 pinned host/client，验证
   request/result correlation、write gate、pinned subprocess、dispose 和 state
   separation；所有迁移写入均被拒绝，仍未接真实 DSH_HOME。
3. **Stage 2（下一节点）**：Stage 1 与 E1/E2 已在本轮保持通过，可以独立重开与
   Codex 相同门槛的 E3–E6；
   E3–E6 必须有独立 adapter evidence，不借用旧 owner evidence。
4. **Stage 3（可选）**：若 E3–E6 有非重复收益，再做个人试点 CBAM 复审；没有净
   收益就停在 Codex 主 Harness。

### Pause and rollback

遇到 unknown capability、路径逃逸、未授权 write、子进程 sandbox 失败、registration
泄漏、owner correlation 丢失、未知 effect 或任意真实外部连接，立即 `blocked` 和
safe-stop。恢复顺序是：停止 adapter → 保留 evidence → 清理 case-local 临时资源 →
重新打开 owner 检查 state → 只有人工确认后才重试。

adapter 升级失败时禁用新版本，恢复旧版 adapter manifest；不回滚/覆盖 owner
canonical database。若 migration 包损坏，按插件自身校验返回错误；不能宣称 owner
backup/restore 已完成。

## Principle considerations

### Performance

本轮只做静态 parse 和 ledger，未测动态调用延迟、内存或子进程成本。下一轮需要以
`callRpc`/`callTool` wall-clock、子进程启动时间、峰值内存为 unit，以固定 case
重复 5 次为 method；目标是 adapter overhead 不超过同一操作 baseline 的 20%，超过
则进入 CBAM 复审。个人开发者不应为迁移功能引入常驻服务。

### Simplicity and accessibility

对用户暴露的能力应保持“配置迁移”一个入口；安全提示必须明确区分 dry-run、export、
import、凭据和外部插件链接。不要要求用户理解 Cordis ABI。client UI 是 non-blocking
评估面，但其按钮只能调用 wrapped RPC，不能直接获得文件系统或 secret handle。

### Security and privacy

威胁主体包括恶意/被篡改插件、模型生成的 tool 参数、越界迁移路径、导入包中的恶意
条目、凭据泄露和 subprocess 脚本逃逸。信任边界是 pinned source → adapter loader →
capability facade → owner/policy/OS boundary；任何边界缺证据都保持 deny。

- credentials：本轮不暴露真实 credential；未来只能使用 scoped opaque handle，导出
  必须显式审批，证据禁止保存明文。
- approvals：所有 write/import/link 操作先过 owner policy；插件传入的 full-access
  参数不具备授权意义。
- isolation：case root、DSH_HOME、cwd 和 output 都限定在隔离范围；network、shell、
  inherited env 和外部 home deny。
- provenance：commit、tree、entry SHA-256、license、依赖和 lifecycle ledger 都
  记录；当前没有独立 package artifact，不能把 source commit 当作 binary provenance。

## Testing and validation

| Gate | reproducible scenario / fixture | expected observation | threshold | result / exit decision |
|---|---|---|---|---|
| E1 | 固定 bundle root 的 `dsh-config-migrate` checkout + headless profile | commit/package/version、host/client、dynamic contract 和 adapter identity 全记录；两入口 parse；profile 不含 bundle | 全部 identity 100%、入口 2/2、plugin 不静默 bundle 化 | 本轮 runner 应为 `pass`；否则 blocking |
| E2 | 同一 bundle root，parse-only Node subprocess | capability allowlist 完整；plugin full-access 请求被标记但不能扩大 policy；network/credential/effect/owner DB touch 为 0 | unknown capability 0；外部计数全 0；license/dependency/artifact ledger 完整 | 本轮 runner 应为 `pass`（static scope）；否则 blocking |
| Stage 1 runtime seam | 同一 bundle root 的 pinned host/client + case-local facade + CompositionOwner | request/result correlation、write gate、full-access 覆盖、pinned subprocess、dispose、state separation | correlation 100%；effect=0；after dispose `0/0/0/0`；negative probe deny | `pass`；见 runtime seam evidence |
| E3 | Stage 2 plugin-aware adapter runtime | deny、write gate、unknown effect、dispose 可复核 | 与 Codex C2/C4 阈值相同 | 当前尚未运行 |
| E4 | 未来同一 owner 的 migration task + provider/replay fixture | 不重复 effect、显式降级、simulated replay | 与 Codex C3/C5/C6 阈值相同 | 当前 not reopened |
| E5 | 未来个人开发者 install/upgrade/backup/restore/diagnosis/exit | 服务数、人工时间、卸载责任 | 安装≤90 分钟；其余各≤30 分钟；常驻服务≤3 | 当前 not reopened |
| E6 | 未来同 task/provider/owner 对比 Codex | 至少一个非重复、可复现收益 | E1–E5 全 pass 后才允许判断 | 当前 not reopened |

E1/E2 的最终证据路径：[evaluation/evidence/w8-deepseek-config-migrate-adapter-e1-e2-20260902-rerun3/summary.json](/Users/bilibili/Documents/workspace/github/jununfly/ZWorkbench/evaluation/evidence/w8-deepseek-config-migrate-adapter-e1-e2-20260902-rerun3/summary.json)。

## Open decisions

| Question | Evidence needed | Owner | Due/exit condition |
|---|---|---|---|
| runtime 是否能限制插件内嵌 Node script 到 pinned source？ | script hash verifier + OS sandbox negative probe | adapter maintainer | E2 runtime stage；不能证明则 blocking/stop |
| `fs.writeText` 如何记录 owner approval 与 effect result？ | synthetic export/import request/result ledger | ZWorkbench owner | Stage 1 后；correlation 100% |
| migration artifact 是否允许进入 owner backup？ | backup schema review + restore failure probe | project owner | 必须保持 namespace 分离；否则只作外部 artifact |
| client UI 是否值得保留？ | headless 与 interactive task benefit/cost | Human | E6 前；无非重复收益则不纳入主线 |
| source-only dynamic plugin 的发布 provenance 是否足够？ | upstream release artifact / independent rebuild | project owner | 产品集成前；未知不是通过 |

## Review record

| Reviewer | Date | Concern | Response or decision | Remaining risk |
|---|---|---|---|---|
| Codex agent | 2026-09-02 | 首轮四件套 E1 fail 是否意味着生态无价值？ | No；把 dynamic plugin 分流到独立 adapter 轨道，保留其可能的非重复收益。 | E3–E6 尚未证明 |
| Codex agent | 2026-09-02 | 插件声明 `danger-full-access` 是否可直接使用？ | No；adapter 必须 ignore-and-replace，并在后续 runtime gate 验证。 | subprocess/OS sandbox 未验证，blocking |
| Human | 待复核 | 是否接受 Stage 1 的 adapter 成本？ | Open；需看 E3–E6 非重复收益和个人开发者维护成本。 | 当前 decision `revise` |

### Short-read acceptance

- 当前 decision：`revise`，不是产品集成批准。
- blocking：runtime adapter、subprocess/OS sandbox、write/owner gate、E3–E6 独立证据。
- non-blocking：client UI 和 package artifact 的后续产品化判断。
- 下一步：以新的 adapter evidence 独立重开并运行 E3–E6；不得继承 Codex 或标准 bundle 证据。
