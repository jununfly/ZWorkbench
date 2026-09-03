# DSH 源码、运行时与 ZWorkbench 布局维护设计

状态：`product execution / target-state approved / H1 artifact validation pending`

本文确定 ZWorkbench 与 DSH 下游项目的磁盘布局、仓库边界、运行时引入方式和长期维护方式。
目标用户是个人开发者或小团队；设计优先保证可追溯、可回滚、可退出和低维护负担。

## One-page overview

### Decision

Decision: approve 采用“兄弟仓库 + pinned artifact + 外部进程”方案；未完成的 DSH artifact 构建、
H1 Bootstrap 和跨平台验证属于 blocking findings，具体 release 版本、打包格式和签名策略属于
non-blocking open decisions。

### Summary

ZWorkbench 不 vendoring DSH 源码，也不把 DSH 作为 Python/Node 库直接嵌入。DSH 下游源码独立维护在
`ZDSHarness`，由固定 source commit 和依赖锁构建可验证 artifact；ZWorkbench 只维护运行时 manifest、
profile、集成插件、bridge、兼容矩阵和 CompositionOwner，并通过受监督的外部进程启动 DSH。

### Platforms and scope

首期平台是 macOS，随后覆盖 Linux；目标运行时为 Node.js/pnpm 构建的 DSH artifact，ZWorkbench 当前
产品代码为 Python。首期只覆盖 case-local、fake/loopback Provider、只读或隔离 worktree 的 H1–H5
混合切片；真实主工作区写入、Git push、部署、Webhook、实时回放和全量插件市场不在本文范围。

当前本机事实（2026-09-03）：

- ZWorkbench：`/Users/bilibili/Documents/workspace/github/jununfly/ZWorkbench`；
- DSH 下游仓库：`/Users/bilibili/Documents/workspace/github/jununfly/ZDSHarness`；
- GitHub 仓库：[jununfly/ZDSHarness](https://github.com/jununfly/ZDSHarness)；
- DSH 上游：[deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)；
- `ZDSHarness` 当前仍有未提交改动，因此其当前工作树不能直接作为正式集成 artifact 的来源。

上述绝对路径是本机布局示例，不是跨机器配置。运行时 manifest 必须使用可解析的配置路径和
artifact digest，而不是依赖另一个开发者的绝对路径。

### Ownership and tracking

| 责任面 | owner | 交付物 |
|---|---|---|
| ZWorkbench 产品、Control Plane、CompositionOwner | ZWorkbench maintainer | `src/`、owner state、bridge、policy、evidence/replay |
| DSH core、Cordis 集成和 DSH 原生包 | ZDSHarness maintainer | 独立 Git 仓库、源码、lock、构建和 release artifact |
| DSH profile 与产品组合 | ZWorkbench maintainer | `integrations/dsh/profiles/`、profile lock、兼容矩阵 |
| ZWorkbench 自有 DSH plugin | ZWorkbench maintainer | `integrations/dsh/plugins/`；必要时再拆独立仓库 |
| DSH artifact cache | 本机运行时 | 用户级 cache；不进入 Git，不作为事实源 |
| Run/effect/result/replay/backup state | CompositionOwner | 唯一 durable source of truth |
| DSH session/plugin state | DSH runtime | 输入、缓存或 evidence；不得升级为第二 owner |
| 上游同步与许可证/NOTICE | ZDSHarness maintainer | upstream 记录、依赖清单、NOTICE、退出记录 |

决策 owner 是项目 Human；roadmap 事实源为
[`personal-workbench-w8-roadmap.json`](../personal-workbench-w8-roadmap.json)。当前 bridge contract
见 [`worker-contract-v1.md`](worker-contract-v1.md)。

## Problem and goals

### Current baseline

当前 ZWorkbench 已有 Codex-only `local_read_only_run` 和 CompositionOwner，但 DSH bridge 尚未实现。
DSH 下游代码已经存在于独立的 `ZDSHarness` 仓库，其 README 提供源码运行方式和开发预览期兼容性提示；
其 `package.json` 固定 pnpm 与 Node engine，并提供 `build`、artifact gate 和 release 脚本。

### Goals

- 让 DSH 可以快速试错、升级和回滚，同时不把 DSH fork 的维护成本转移成 ZWorkbench 的 vendoring 成本；
- 让每次 H1–H5 运行都能回答“哪份源码、哪份依赖、哪份 artifact、哪份 profile 在运行”；
- 让源码开发、artifact 集成和个人试点有清晰不同的资格与证据等级；
- 保持 ZWorkbench、ZDSHarness、DSH session 和 CompositionOwner 的 ownership 边界；
- 允许第一方 DSH plugin 快速实验，并能独立 disable、rollback 和退出；
- 适合一个人完成安装、升级、诊断、backup/restore 和回滚。

### Non-goals

- 不把 ZDSHarness 合并进 ZWorkbench 的 Git history；
- 不提交 `node_modules`、编译输出、运行时二进制或大型历史 evidence；
- 不维护一份实时插件市场作为启动依赖；
- 不通过 DSH session/database 代替 CompositionOwner；
- 不在本文中承诺 DSH sandbox、Codex host approval 或真实 Provider 已达到生产级；
- 不自动改动已有 `ZDSHarness` 工作树中的用户改动。

### Assumptions and constraints

- ZDSHarness 是 DSH 的下游 fork，远端为 `jununfly/ZDSHarness`；上游身份仍是
  `deepseek-ai/deepseek-harness`；
- DSH 仍处于快速演进阶段，版本、插件 ABI、配置和 artifact 必须固定；
- ZWorkbench 目标架构为 DSH 主 Harness + Codex Coding Worker + CompositionOwner；
- 常驻人工维护服务目标不超过 3 个；按 Run 启动的 DSH/Codex 子进程必须可停止；
- 不确定的版本、兼容性、进程状态或 effect 状态保持 `unknown`，不被推断为成功。

### Success definition

布局设计达到可执行状态，需要同时满足：

1. 两个仓库可以独立 clone、测试、提交和回滚；
2. ZWorkbench manifest 可以校验 DSH artifact 的 source commit、依赖、平台和 digest；
3. H1–H5 只使用 artifact mode，source mode 不产生正式集成通过证据；
4. 运行时状态、证据和 artifact cache 不污染 Git working tree；
5. DSH artifact 替换失败时可以恢复上一份已签核版本；
6. 任何 DSH/插件升级都能定位受影响验证和维护责任。

## Design

### Alternatives considered

| 方案 | 优点 | 主要代价/风险 | 决策 |
|---|---|---|---|
| 将 DSH 源码 vendoring 到 ZWorkbench | 单仓库查找方便 | fork 漂移、依赖冲突、构建时间和历史膨胀；难以独立升级 | reject |
| Git submodule 指向 DSH | 可以固定 commit | 子模块初始化、路径和 CI 心智负担；仍容易把两个生命周期伪装成一个项目 | reject |
| 仅使用实时 npm/npx 包 | 首次安装简单 | tag 漂移、供应链和回滚不可控；难以证明源码 provenance | reject |
| 仅保存预编译 DSH artifact | 集成简单 | 调试困难，源码与产物关系弱，跨平台构建责任不透明 | revise |
| 兄弟仓库 + pinned artifact + 外部进程 | 生命周期独立、可追溯、可回滚、进程边界清晰 | 需要 manifest、构建 receipt 和一条 bridge | approve |
| 源码开发 + artifact 集成的双模式 | 兼顾快速试错和正式验证 | 两种启动路径可能漂移，需要强制证据资格规则 | approve，作为选定方案的开发子模式 |

### Chosen repository layout

```text
/Users/<user>/Documents/workspace/github/<owner>/
├── ZWorkbench/                         # 产品仓库
│   ├── src/zworkbench/                 # Control Plane、Owner、adapter、bridge
│   ├── integrations/dsh/
│   │   ├── profiles/<profile-id>/      # 可提交的 DSH profile/config
│   │   ├── plugins/<plugin-id>/        # 第一方 plugin；每次只引入一个
│   │   ├── manifests/                  # DSH runtime 与插件 lock
│   │   ├── compatibility/              # DSH/Worker/schema 兼容矩阵
│   │   └── README.md                   # 集成入口与模式边界
│   ├── evaluation/fixtures/dsh/        # 隔离 fixture；不保存历史 runs
│   └── docs/plans/designs/              # 目标设计与评审记录
└── ZDSHarness/                         # DSH 下游源码仓库
    ├── apps/ packages/ vendor/ native/ # DSH 原生源码与其依赖边界
    ├── pnpm-lock.yaml                  # DSH 依赖锁
    ├── package.json                    # package manager、engine、构建脚本
    ├── LICENSE THIRD_PARTY_NOTICES.md  # 许可证和 NOTICE
    └── docs/                           # DSH 自有架构与开发规则
```

`ZWorkbench` 和 `ZDSHarness` 是两个独立 Git repository，不使用 submodule。上游不需要固定的第三个
兄弟目录；在 `ZDSHarness` 内以 `upstream` remote 表达
`deepseek-ai/deepseek-harness`。如果需要干净上游对比 checkout，应放在临时目录或独立 cache，不能
成为 ZWorkbench 的启动依赖。

### Three-plane separation

布局分为 source plane、artifact plane 和 runtime/evidence plane：

```text
source plane
  ZWorkbench Git ── profile / manifest / bridge / tests
  ZDSHarness Git  ── DSH source / lock / upstream sync
          │ pinned commit + reproducible build
          ▼
artifact plane
  user cache or release asset
  dsh/<release>/<source-commit>/<platform>/<artifact-digest>/
          │ manifest verified before process start
          ▼
runtime/evidence plane
  per-profile/per-case DSH_HOME, owner DB, logs, artifacts, replay evidence
```

source plane 可以审查和提交；artifact plane 可以清理并重新生成；runtime/evidence plane 是运行时数据，
默认只留在用户级目录或 case root。三者不能共用一个“当前目录”作为隐式状态源。

### User-level runtime layout

macOS 的推荐用户级数据根是：

```text
~/Library/Application Support/ZWorkbench/
├── runtimes/dsh/
│   └── <release>/<source-commit>/<os>-<arch>/<artifact-digest>/
│       ├── artifact/              # 可执行文件或 packed runtime
│       ├── manifest.json           # 构建 receipt 的副本
│       └── install-receipt.json    # 安装、校验和激活记录
├── profiles/dsh/<profile-id>/     # 非敏感的本机 profile 投影
├── owner/composition.sqlite3      # CompositionOwner canonical state
└── evidence/                      # 用户级运行证据索引（大文件可外置）
```

Linux 使用 `${XDG_DATA_HOME:-~/.local/share}/zworkbench/` 下的相同子目录；应用不把运行时路径硬编码
为某台机器的绝对路径。H1–H5 的 fixture 仍将 DSH_HOME、owner DB、workspace 和 evidence root 放在
独立 case-local root 内，以便清理和重放。

运行时 cache 至少保留当前 active 和上一份 last-known-good artifact。清理只能删除未被 active manifest
或运行证据引用的 cache；不能删除 CompositionOwner canonical state 或未关闭的 evidence。

### What is versioned in ZWorkbench

`integrations/dsh/manifests/` 中的 manifest 是 ZWorkbench 的运行时选择事实，至少包含：

```text
runtime_id
dsh_release
dsh_source_commit
dsh_dependency_lock_digest
artifact_digest
platform / architecture
launch argv template
allowed environment names (never credential values)
dsh profile digest
plugin bundle and plugin lock digests
worker_contract_schema
codex_worker_compatibility
owner_schema_compatibility
build_receipt reference
activation status / previous known-good reference
```

manifest 不包含 API key、token、cookie、session 原文或完整 Provider 响应。credential 只能通过既有本地
凭证路径或隐藏输入注入，并只在 owner/evidence 中留下脱敏 reference/fingerprint。

Profile 的 `package.json`、依赖 lock、`cordis.patch.yml` 和 first-party plugin source 可以进入
ZWorkbench Git；安装出来的 `node_modules`、DSH_HOME、编译输出和插件运行状态留在 runtime/evidence
plane。第三方 plugin 必须记录 package/source/version/commit/digest/license 和 capability/permission。

### Source mode and artifact mode

| 模式 | 用途 | 来源 | 正式 H1–H5 资格 |
|---|---|---|---:|
| source mode | 修改 DSH、调试 ABI、快速实验 | ZDSHarness sibling checkout | 否 |
| artifact mode | 集成、回归、个人试点 | clean pinned commit 构建产物 | 是 |
| recovery mode | 回滚与诊断 | last-known-good artifact + 原证据 | 是，按回滚场景 |

Source mode 可以由本地开发配置显式指向 `ZDSHarness`，但启动结果必须标记为 `development-only`，
不能写成 H1–H5 pass，也不能被用于生成“版本稳定”的试点结论。Artifact mode 要求 manifest digest
校验成功、source/lock/build receipt 完整，并且启动 argv/env 与 manifest 一致。

正式运行不使用 `npx` 或未锁定的实时 tag 作为隐式安装步骤。若 artifact 是 packed package，包文件
也必须以 digest 绑定，并由本地 runtime adapter 在启动前校验。

### Build and provenance flow

构建责任在 ZDSHarness，集成责任在 ZWorkbench：

1. 在干净的 ZDSHarness commit 上固定 Node、pnpm、`pnpm-lock.yaml`、平台和架构；
2. 使用 ZDSHarness 自己的 `build`、artifact gate 和 release verification 流程生成产物；
3. 生成 build receipt：source commit、lock digest、工具链版本、依赖/NOTICE 摘要、artifact digest；
4. 把 receipt 和 artifact 放入用户级 cache 或 release asset，不把大型产物提交到 ZWorkbench；
5. 在 ZWorkbench manifest 中登记 receipt/artifact digest、profile/plugin digest 和兼容范围；
6. Bridge 启动前验证 manifest、artifact、workspace、policy 和 schema identity；
7. 运行 H1–H5，并将每次结果关联到同一组 identity。

当前 ZDSHarness 的实际构建命令和 gate 以其 `package.json` 与开发指南为准；本设计不复制命令清单，
避免文档成为过期缓存。首次 H1 前必须补一份固定 artifact receipt，并记录实际执行的命令与输出。

### DSH runtime adapter seam

ZWorkbench 需要一个窄的 `DshRuntimeAdapter`，它负责解析 manifest、验证 artifact 和启动参数，
但不复制 DSH Agent loop：

```text
resolve(manifest_id)
  → verify source/lock/artifact/profile/schema/policy identity
  → create case-local DSH_HOME and environment allowlist
  → spawn DSH with argv (shell=false)
  → bind DSH session/turn to parent_run_id
  → forward events through worker/evidence contract
  → stop process tree and persist exit receipt
```

Adapter 不直接写 CompositionOwner 的 SQLite 表；它通过 owner API/extension 提交结构化事件和结果。
未知 manifest 字段、digest 不匹配、路径越界、未声明环境变量、未知 DSH message 或无法关联身份时，
应拒绝并 `safe-stop`。

### Maintenance model

#### ZDSHarness maintenance

- `ZDSHarness` 维护 DSH core、Cordis 和 DSH 原生包；其 GitHub origin 是 `jununfly/ZDSHarness`；
- 通过 `upstream` remote 跟踪 `deepseek-ai/deepseek-harness`，不把 upstream checkout 复制到
  ZWorkbench；
- 上游同步在独立分支完成，经过 ZDSHarness 自有测试、构建、license/NOTICE 和 artifact gate 后再合并；
- DSH core 必须修改时，保留下游 commit、变更原因和上游同步基线；不得把未审查的本地 patch 直接
  伪装成上游版本；
- 首选把产品能力放在 ZWorkbench first-party plugin 或 adapter；只有无法通过 DSH extension seam
  实现的修复才进入 ZDSHarness core fork；
- ZDSHarness 的 `node_modules`、`lib`、打包目录和运行状态只属于它自己的工作树或 cache。

#### ZWorkbench maintenance

- 保存 DSH runtime manifest、profile、插件 lock、bridge contract 和 compatibility matrix；
- 不保存 DSH 编译输出和第二份 DSH 依赖树；
- DSH core、插件 ABI、profile、Worker contract、Codex 版本或 owner schema 变化时，重新运行受影响
  的 H1–H5 和产品回归；
- 通过 feature flag 一次只启用一个新插件；插件必须具备 install/enable/disable/dispose/rollback
  证据；
- 发生兼容失败时，保持最后一个已签核 artifact active，并把新 artifact 留在 disabled cache 供诊断。

#### First-party plugin placement

第一阶段的产品专用 DSH plugin 放在 `ZWorkbench/integrations/dsh/plugins/`，因为它与工作台 policy、
profile 和 H1–H5 证据共同演进。只有在 plugin 拥有独立用户、版本、license、测试和退出需求时，才拆成
第三个 sibling repository；拆分本身必须经过 CBAM，不能因为目录变多就默认拆分。

### Upgrade, activation and rollback

升级是新 artifact 的并行安装和指针切换，不是覆盖当前目录：

```text
build clean ZDSHarness commit
  → verify receipt + artifact digest
  → install inactive runtime directory
  → run version/help + H1/H2 smoke
  → activate manifest pointer
  → run H3–H5 regression
  → retain last-known-good pointer
```

任一关键校验失败、身份关联不完整、进程无法退出、未知 wire/capability/effect、artifact digest 不匹配
或回放产生外部执行时，暂停激活并回到 last-known-good。回滚动作是停止新进程、保留证据、切换 manifest
指针和重新启动旧 artifact；不重写 owner canonical state，不删除失败证据。

升级、回滚、backup/restore 和退出必须分别记录 DSH artifact、profile/plugin state、session state、
owner state 和远端 Provider 资源。删除 runtime cache 不代表删除 Provider 远端数据、任务、Webhook 或备份。

## Metrics and experiments

| 指标 | baseline | unit | method | target/threshold | owner |
|---|---|---|---|---|---|
| artifact provenance 完整率 | 混合架构未测 | 每次运行 | manifest/receipt 字段检查 | 100% | runtime adapter |
| artifact digest 校验成功率 | 混合架构未测 | 每次启动 | 启动前 SHA-256 校验 | 100%；失败不得启动 | runtime adapter |
| 未锁定 runtime 启动次数 | 混合架构未测 | 次/发布 | 启动日志和 manifest 审计 | 0 | ZWorkbench maintainer |
| source mode 进入正式证据次数 | 目标为 0 | 次/H1–H5 | evidence mode 检查 | 0 | evaluation owner |
| 父子 identity 关联率 | 混合架构未测 | 百分比 | H2 ledger 检查 | 100% | bridge/owner |
| 未授权 effect | 首期目标为 0 | 次/run | facade + host probe | 0 | policy/host |
| 孤儿 DSH/Codex Worker | 混合架构未测 | 个/run | cancel/timeout/crash 后进程树扫描 | 0 | supervisor |
| artifact 回滚耗时 | 未测 | 分钟 | 隔离升级失败人工 stopwatch | ≤30 分钟 | operations owner |
| 首次安装耗时 | Codex baseline 已有；DSH 未测 | 分钟 | fresh isolated install stopwatch | ≤90 分钟 | operations owner |
| 常驻服务数量 | 目标上限 3 | 个 | fresh install service manifest | ≤3 | maintainer |

### Experiments

1. **Build provenance probe**：从 clean ZDSHarness commit 构建一次 artifact，校验 receipt、digest、
   license/NOTICE 和平台信息；缺一项则 blocking。
2. **H1 Bootstrap**：只用 artifact mode 启动固定 DSH profile，验证 parent Run、DSH session 和退出
   receipt；阈值是 identity 100%、未授权 effect 0。
3. **Version skew probe**：故意用不兼容 Worker contract/schema 的 manifest，确认启动前拒绝并
   `safe-stop`，不启动 Provider 或工具。
4. **Upgrade/rollback probe**：在 case-local cache 并行安装新旧 artifact，模拟新版本启动失败，确认
   active 指针和 owner state 可恢复，人工时间 ≤30 分钟。
5. **Source/artifact divergence probe**：修改 sibling checkout 后尝试 artifact-mode 启动，确认 adapter
   仍按 manifest digest 运行，source 工作树不被隐式读取。

上述实验在 H1 前产生最小脱敏 evidence；大型 `evaluation/runs` 不提交到 Git。

## Rollout, recovery, and lifecycle

### Rollout stages

| 阶段 | 允许内容 | 放行条件 |
|---|---|---|
| Stage 0 | manifest、profile、contract、build receipt 设计 | 字段、owner、failure semantics 可审查 |
| Stage 1 | artifact mode H1–H5 混合只读 | provenance、identity、process、replay 硬门全部通过 |
| Stage 2 | 单个 first-party/第三方 plugin 实验 | plugin lifecycle、license、成本、退出和受影响回归通过 |
| Stage 3 | 隔离 worktree approved apply | L2 approval、L3 host enforcement、claim/reconcile/rollback 通过 |
| Stage 4 | 受控个人试点 | C7、升级/恢复/退出和长期维护成本签核 |

### Pause and rollback triggers

以下是 blocking：artifact/source/lock provenance 不完整、manifest digest 不匹配、父子 identity 丢失、
未知 wire/capability/effect 未 safe-stop、DSH/Codex 孤儿进程、replay 启动外部执行、owner state 被绕过、
或回滚无法复现。以下是 non-blocking：开发模式启动慢、artifact 体积偏大、UI 体验缺口，只要没有掩盖
blocking findings 并有后续 owner。

回滚顺序：冻结新 profile/plugin enable；停止触发器和 DSH/Codex 进程树；保存 diagnosis、版本和 evidence；
处理 unresolved effect；切回 last-known-good manifest；重启后只开放只读路径；不删除失败 artifact 或
owner state。

### Version skew and migration

- DSH core version、source commit、dependency lock、profile digest、plugin bundle、Worker contract 和
  Codex schema 组成一组 compatibility key；
- 只有 manifest 明确声明兼容范围时才允许启动；未知范围是 `unknown` 并 safe-stop；
- DSH profile/config migration 与 CompositionOwner backup/restore 分开执行、分开留 receipt；
- 不能直接把 DSH 内部数据库复制成 owner state；跨版本只通过 versioned export/import；
- 新旧 artifact 可以并存，但同一 parent Run 只绑定一个已验证 runtime identity。

### Support, deprecation and cleanup

维护者主要维护两个 Git 仓库和一个本地 runtime cache，不引入常驻 gateway、消息队列或第二个数据库。
每次 artifact 发布保留 build receipt、NOTICE 摘要、兼容矩阵和回滚指针；淘汰旧 artifact 前先确认没有
active Run、未 reconcile effect 或唯一 evidence 依赖。停用 DSH 时，保留 CompositionOwner schema 和
证据，移除 DSH profile、bridge 和 plugin 依赖，恢复 Codex-only fallback baseline。

## Principle considerations

### Performance

外部 DSH 进程和 artifact 校验会增加 cold start、handshake 和磁盘占用；当前没有实测 baseline，不能声称
性能收益。H1 后测量 DSH 启动、artifact 校验、Worker handshake、每 Run 进程数、内存峰值、Provider 请求数、
owner DB 增长和 evidence 大小，并与同形状 Codex-only baseline 比较。性能回归不能覆盖安全或回滚硬门。

### Simplicity and accessibility

用户只接触一个 ZWorkbench 入口；源码/artifact mode 由开发者配置和证据标记承载，不要求普通用户理解
两个 Harness 的内部协议。小团队获得明确的目录责任和一个可切换的 last-known-good 版本，但需要维护者
理解两个仓库、Node/pnpm 和 Python 的工具链；这是选择独立生命周期换取可回滚性的有意成本。

命令行错误必须明确指出：当前 profile、artifact digest、缺失字段、回滚建议和 evidence 路径；JSON 输出
保持脱敏。GUI 或 CLI 的可访问性细节留在入口实现评审中，本文没有额外的无障碍组件要求。

### Security and privacy

信任链是：用户输入/模型输出 → DSH/plugin → DSH adapter → ZWorkbench policy/owner → 受监督进程 →
case workspace/Provider。DSH plugin、profile 和 Codex Worker 都视为可能出错或不可信的输入方。

- argv 使用数组且 shell 关闭；workspace、DSH_HOME、artifact 和 evidence 路径在启动前校验；
- env 使用 allowlist，API key 只走本地 credential reference/隐藏注入，不进入 manifest、argv、日志、
  owner、backup、cassette、artifact 或 Git；
- DSH/Codex 的工具和 Provider 请求都经过 capability/policy/effect seam；
- profile/plugin 的安装脚本、后台任务和 dispose 结果必须可观察；
- source commit、lock、artifact digest、NOTICE 和 plugin license 组成 provenance 记录；
- 退出本地 DSH 不代表 Provider 远端数据、任务、Webhook、备份、retention 或账单已删除。

## Testing and validation

| 场景 | fixture/方法 | 预期观察 | 阈值 | owner/exit |
|---|---|---|---|---|
| clean build | ZDSHarness clean checkout + pinned lock | receipt 和 artifact digest 生成 | provenance 100% | ZDSHarness maintainer；H1 前 |
| artifact tamper | 修改 cache artifact 一个字节 | adapter 拒绝启动并 safe-stop | 外部执行 0 | runtime adapter |
| profile mismatch | manifest 使用未锁定/未知 profile | preflight 拒绝 | 未知状态不启动 | bridge owner |
| H1 bootstrap | case-local DSH_HOME + fake Provider | parent/session/exit identity 可查 | identity 100% | H1 |
| H2 handshake | DSH→adapter→Codex | DSH/Worker/Codex identity 绑定 | 100% | H2 |
| H3 read-only coding | isolated workspace | 读取、测试、diff artifact，不 apply | 未授权 effect 0 | H3 |
| H4 lifecycle | cancel、timeout、crash、parent stop、restart | 进程树清零，owner state 可恢复 | 孤儿 0、状态丢失 0 | H4 |
| H5 replay | recorded/simulated/live 三种入口 | replay 不启动 Worker/Provider/tool | 外部执行 0 | H5 |
| upgrade/rollback | 两个 cache 版本 + 故障注入 | 指针回到 last-known-good，证据保留 | ≤30 分钟 | operations owner |
| cross-platform | macOS/Linux case fixture | 路径、argv、退出语义一致 | 每个目标平台通过 | platform owner |

产品测试、ZDSHarness 自有测试和 H1–H5 evidence 分开报告；任一 unknown 只能得到 `unknown/stop`，
不能作为综合 pass。实现前不执行真实 DSH 启动，直到 artifact provenance probe 完成。

## Open decisions

| Question | Evidence needed | Owner | Due/exit condition |
|---|---|---|---|
| 首个 H1 使用哪个 DSH source commit/release？ | clean build receipt、artifact digest、ZDSHarness tests | ZDSHarness maintainer | H1 启动前固定 |
| artifact 采用 packed package、standalone executable 还是两者？ | 安装、启动、升级、回滚和跨平台测试 | runtime owner | 选择一种作为正式路径；另一种可保持 development-only |
| `upstream` remote 和下游同步策略是否落地？ | remote、sync branch、变更清单和 license 检查 | ZDSHarness maintainer | 首次上游同步前 |
| DSH profile 是否需要持久 session？ | session resume、backup/restore 和 owner correlation fixture | ZWorkbench maintainer | H2/H5 前；默认 case-local |
| 首批 first-party plugin 清单是什么？ | 每个 plugin 的单独收益、依赖、dispose、license、E1–E6 | product owner | Stage 2 前；默认空 allowlist |
| 是否需要 artifact 签名而不只 SHA-256？ | 个人试点威胁模型和发布渠道 | security owner | 个人本地试点可先 hash；对外分发前重新评审 |
| runtime cache 的保留和清理策略是什么？ | cache 容量、active Run 引用和故障恢复演练 | operations owner | upgrade/rollback probe 前 |

## Review record

| Reviewer | Date | Concern | Response / decision | Remaining risk |
|---|---|---|---|---|
| Human + Codex design review | 2026-09-03 | DSH 源码、artifact 和产品仓库是否应合并？ | 采用兄弟仓库；ZDSHarness 独立维护，ZWorkbench 只绑定 artifact/manifest | 首个 artifact 尚未构建 |
| Human + Codex design review | 2026-09-03 | 源码开发路径是否可作为正式集成路径？ | 保留 source mode 供调试，但 H1–H5 和试点只认 artifact mode | 需实现 mode 标记和 preflight |
| Human + Codex design review | 2026-09-03 | 目录改名是否影响历史证据？ | 下游展示名统一为 ZDSHarness；upstream、commit、digest、package identity 保留 | 旧历史记录需要按命名规则逐项整理 |

### Short-read acceptance

当前决策是 `approve`：ZWorkbench 与 ZDSHarness 使用兄弟仓库；正式运行使用 pinned DSH artifact；
source mode 只用于开发。当前 blocking findings 是首个 clean artifact receipt、digest 校验、H1–H5
和回滚证据尚未完成；下一验证动作是由 ZDSHarness maintainer 在 clean commit 上构建 artifact，产出
receipt 后执行 H1 Bootstrap。
