# W8 DeepSeek Harness 插件生态挑战：带证据的研究发现

状态：`fresh-collection` · `acceptance/evaluation` · 研究日期：2026-09-01（Asia/Shanghai）

本记录重新审视前一轮“DeepSeek 评估完成，但不足以替换或并列 Codex 主 Harness”的结论。前一轮主要测量固定版本的 DeepSeek Harness 本体和通用 composition fixture，没有把官方插件合同、插件目录、社区插件、跨 Harness bridge 与外部控制面作为独立能力供应方纳入决策面。因此，前一轮的“DeepSeek 缺口”只能表示“固定 Harness/当前测试组合尚未证明”，不能表示“DeepSeek 生态无法补齐”。

本轮仍不宣布切换 Harness，也不接入生产插件。新的结论是：**DeepSeek 生态应从“被动挑战者”升级为“需要完成插件组合评估的一等候选架构”；Codex 仍是当前生产主线，直到插件组合通过相同的 C1–C7 和个人/小团队成本门槛。**

## 1. 证据边界

### 1.1 Sealed ledger

- 主生态 ledger：[`w8-deepseek-plugin-ecosystem.v3.ledger-response.json`](./w8-deepseek-plugin-ecosystem.v3.ledger-response.json)
  - 19 个仓库；143 条 canonical evidence；brief fingerprint：`832bd1c765c47364d2a4d7e36c1a5da09e5a98e26ad832132c0f1af6e06e581e`
  - observed at：`2026-09-01T16:20:58.574Z`
  - 9 个信息缺口保持为 `unknownCriteria`，没有被转成负向能力结论。
- 生态目录补充 ledger：[`w8-deepseek-plugin-registry.ledger-response.json`](./w8-deepseek-plugin-registry.ledger-response.json)
  - `awesome-dsh-plugin/awesome-dsh-plugin`，固定 commit `a105d90c9f2398b184550534b205778c7bf853d`，4 条 canonical evidence。
- GitHub Stars 和 topic match 仅用于候选发现与可见度，不用于能力评分。
- 所有 commit、Stars、topic match 均以 ledger 为准；第三方 README 的“已兼容”或“已测试”仍属于项目自述，除非本项目另行复现，不升级为 ZWorkbench C1–C7 pass。

### 1.2 四种能力来源

本轮采用四种标签，避免把插件生态混成一个“DeepSeek 原生能力”列：

| 标签 | 含义 | 能否直接改变 C1–C7 判定 |
|---|---|---|
| `native` | 固定 DSH 版本本身提供并由候选合同拥有 | 可以，但仍需场景证据 |
| `plugin-composed` | 通过 DSH/Cordis 插件 ABI 装配到同一进程或 profile | 只能在插件固定版本实测后改变 |
| `outer-composed` | 独立服务、桌面控制面、网关、远程执行器或另一运行时 | 不改变 DSH native；必须新增 owner/服务审计 |
| `bridge/migration` | 跨 Harness 迁移、协议投影、导入导出或兼容桥 | 提供互操作价值，不自动提供 durable/replay/safety owner |

## 2. 关键修正：DeepSeek 确实把“插件”当作产品边界

固定 commit `4e84901e6471b79ec0338099867ebb4606d12bb5` 的官方 CLI 文档把 `dsh` 描述为唯一 Node launcher，profile 是按顺序叠加的 plugin-bundle patch layers；SDK 和 ACP 是 profile，不是另起的 bin。[E1692252522188e29a83706e5](https://github.com/deepseek-ai/deepseek-harness/blob/4e84901e6471b79ec0338099867ebb4606d12bb5/apps/cli/README.md)

同一文档还把 profile、headless、web、tui 和 SDK/ACP 入口放进统一 launcher 合同。[E6cf9d81a5eee301f6dd20cd0](https://github.com/deepseek-ai/deepseek-harness/blob/4e84901e6471b79ec0338099867ebb4606d12bb5/apps/cli/README.md)

生态目录的 canonical evidence 进一步明确：社区插件通过 `dsh plugin add` 安装，并声明 `dsh.bundle` manifest；`dsh-market` 则把发现、安装、更新、卸载、热启停、profile 插件清单 backup/restore 聚合为一个可选 UI。[E68cc1708a7eb8e97458c5b64](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/blob/a105d90c9f2398b184550534b205778c7bf853d/README.md)、[Ee6433a2533f7d876de709ad2](https://github.com/dsh-market/dsh-market/blob/a2a21c5147ffdc872a9ed8731e6d93c9a7f67f17/README.md)、[E784f178fdc0ace33fddaab0a](https://github.com/dsh-market/dsh-market/blob/a2a21c5147ffdc872a9ed8731e6d93c9a7f67f17/README.md)

因此，前一轮把“核心 Harness 未直接提供”写成“DeepSeek 不足以挑战 Codex”的推理链少了一层：**插件 ABI 是候选架构的供给面，插件生态是能力供给面，但插件生态不是免费、无主、无风险的能力。**

## 3. 生态候选及其对 ZWorkbench 的实际意义

下表只选择与工作台目标直接相关的候选。完整 19 个仓库仍在 sealed ledger 中；Stars/topic match 是 GitHub 采集时的元数据，不是质量分数。

| 角色 | 固定候选 | 证据显示的能力 | 对 ZWorkbench 的初步判断 |
|---|---|---|---|
| 核心 Harness | `deepseek-ai/deepseek-harness` @ `4e84901e…` | profile/plugin-bundle、headless、SDK、ACP 入口 | `native/plugin host`；需要以固定测试版本重新验证 |
| 发现/安装 | `awesome-dsh-plugin/awesome-dsh-plugin` @ `a105d90c…`；`dsh-market/dsh-market` @ `a2a21c5…` | `dsh.bundle` 目录；市场实时 catalog、安装/更新/卸载、profile 插件备份恢复 | `plugin-composed`；可降低选型摩擦，但把远程 registry、npm/commit 供应链和升级责任带入工作台 |
| 生态验证 | `AdamPlatin123/dsh-plugin-radar` @ `ef60e1cb…` | 版本锚、DSH/测试环境锚、运行级兼容结果、快照 artifact | `outer-composed`；很适合做候选筛选与证据供给，但其自报判定不能替代本地验收 |
| 观测/上下文 | `bowenliang123/dsh-context` @ `552bb907…`；`Jockjrop/dsh-usage-stats` @ `40bb65a…`；`Han-1413141/dsh-cost-meter` @ `28856d6…` | context composition、请求趋势、事件/文件活动、token/费用与 Provider 统计 | `plugin-composed`；可能显著降低 C6/成本可视化工作量，但要验证脱敏、数据 owner、历史日志 schema 和外部额度请求 |
| 记忆 | `Qinling-Melon-Farmers/dsh-memoir` @ `4416d50e…` | 本地跨 session project memory、BM25、provenance、生命周期、无外部服务 | `plugin-composed`；与个人/小团队本地优先目标高度匹配，但 memory 是否应成为 ZWorkbench canonical state 必须拒绝隐式双 owner |
| Provider/路由 | `yjh051108/dsh-routing-suite` @ `f753bb1c…`；`cinob/dsh-web-search-multi` @ `fcfcd70…`；`AITabby/dockyard-dsh` @ `7af2328…` | 运行时插件注入；任务/推理路由；多搜索 Provider fallback；provider-neutral LLM adapter | 路由插件可能是 DeepSeek 的真实差异化入口；必须区分“路由/搜索工具 fallback”和 C5 的模型 Provider failover |
| 跨 Harness 互操作 | `weijiafu14/pi2dsh` @ `f2005537…`；`Nwflower/dsh-chat-import` @ `68632511…` | Pi ABI 投影为 DSH 插件；跨 Claude/Codex/Pi 等历史导入、resume、可选双向 sync | `bridge/migration`；可把 Pi/Codex 生态带入 DSH，但事件、session、compaction、replay 和版本漂移需要显式映射 |
| 迁移/退出 | `kol-mm/dsh-config-migrate` @ `24aa641…` | profile、external plugins、agent presets 跨机器导出；凭据加密；依赖检测；跳过 sessions/storages | 对 C7 很有价值，但它是 config/plugin migration，不等同于 composition owner 的 backup/restore |
| 多 Agent | `NanmiCoder/dsh-agent-teams` @ `232a338…` | 真实成员 spawn/resume/依赖任务/报告；Alpha.2 兼容性和认证 fail-closed 测试 | 可能提升代码/并行任务能力；会引入成员 identity、预算、失败通知和子任务 durable owner |
| 远程工作区 | `flymysql/dsh-remote` @ `bf3573c…` | SSH、21 个 `rw_*` 工具、SFTP 双向 sync、冲突检测、端口转发、keychain 密码 | 能补“集成个人项目/远程项目”，但直接扩大凭证、网络、远端副作用和退出边界；首个个人试点默认拒绝 |
| 安全辅助 | `yzhangjy/dsh-path-anonymizer` @ `610b012…` | 用户消息中的 workspace-external 路径脱敏与确认 | 只是 privacy/message-redaction 插件，明确不是 sandbox，也不拦模型 tool call；不能用来签 C2 |
| 远端渠道 | `xmanrui/dsh-im` @ `c2be238…` | 9 种 IM 机器人和公网 AI Office Connector，渠道语义与降级规则 | 对自动任务/远程控制有潜力，但直接引入 webhook、远端消息、账户和出站数据；后置 |
| 外部控制面/替代运行时 | `agentrq/agentrq` @ `69ce7fc…`；`sandbaseai/sandbase-harness` @ `a634eb4…` | task queue/人机协同；sessions/files/environments/API keys/webhooks/schedules/metrics/audit/replay | `outer-composed` 或另一 Harness，不应被称为 DSH 插件补丁；若采用，必须重算服务数和单一 owner 成本 |

## 4. 关键证据与限制

### 4.1 生态已经覆盖若干“前一轮缺口”的候选供应

- `dsh-market` 的证据覆盖实时 registry、插件源/npm mapping、安装/更新/卸载、profile plugin list 与配置 backup/restore、merge/validate/rollback 和 hot disable/enable。[Ee6433a2533f7d876de709ad2](https://github.com/dsh-market/dsh-market/blob/a2a21c5147ffdc872a9ed8731e6d93c9a7f67f17/README.md)、[E784f178fdc0ace33fddaab0a](https://github.com/dsh-market/dsh-market/blob/a2a21c5147ffdc872a9ed8731e6d93c9a7f67f17/README.md)
- `dsh-plugin-radar` 的证据明确区分 plugin version、runner image digest、snapshot run id，以及“实测/自报”来源；其生态目录同时列出 replay、sandbox、remote 等不同类型插件。[E36645d7aab12f169efd100ac](https://github.com/AdamPlatin123/dsh-plugin-radar/blob/ef60e1cbca540487086866bf841d8d8a8b8da0fb/docs/adr/0003-versioned-verdict-archive.md)、[Ef99d6d7e1e439410fb8c85ed](https://github.com/AdamPlatin123/dsh-plugin-radar/blob/ef60e1cbca540487086866bf841d8d8a8b8da0fb/README.md)、[Eb0bf80fc7582a5ab322b512c](https://github.com/AdamPlatin123/dsh-plugin-radar/blob/ef60e1cbca540487086866bf841d8d8a8b8da0fb/README.md)
- `dsh-context` 的证据覆盖 context composition、provider-reported Actual Prompt/Output/Cache、context browser、趋势、事件和 file activity，是 C6/调试价值而非 durable run ledger。[Ecd9fe4a8353a1fa253b84073](https://github.com/bowenliang123/dsh-context/blob/552bb9077f9ec5885bd37e35037c5e0de51d4c6d/README.md)
- `dsh-routing-suite` 的 injector 描述了运行时注入本地 DSH plugin、热重载、清单持久化和重启恢复；它的 README 也显示仓库把兼容性与 DSH target/人工审核作为发布条件。[Eedca3f5d1cd863c936e443b0](https://github.com/yjh051108/dsh-routing-suite/blob/f753bb1cd793a8e74b01d8fa5ad2c3d87a2e3c30/injector/package.json)、[Eb53f42c74a9916a536cd1159](https://github.com/yjh051108/dsh-routing-suite/blob/f753bb1cd793a8e74b01d8fa5ad2c3d87a2e3c30/docs/FLATTEN-MIGRATION.md)
- `dsh-config-migrate` 明确排除 `sessions`/`storages`，同时对 profile、external plugin、preset 和凭据加密做迁移；这正好证明“插件/配置迁移”和“运行时 canonical state backup/restore”是两种合同。[E7f03837654c251735293b439](https://github.com/kol-mm/dsh-config-migrate/blob/24aa64188386181bdaf21f4b46fea02bddf77e71/README.md)
- `dsh-chat-import` 证明跨 Harness transcript import/resume/sync 可以成为插件能力；但其证据没有证明它满足 ZWorkbench 的 effect ledger 或确定性 replay 合同。[E0719b845e6316e2f7fc9985e](https://github.com/Nwflower/dsh-chat-import/blob/686325113117873c00ca74c476f18874b287679/README.md)、[E74631a072b48810a41d1f3f2](https://github.com/Nwflower/dsh-chat-import/blob/686325113117873c00ca74c476f18874b2876796/package.json)
- `pi2dsh` 不是简单“兼容成功”：它的文档明确记录 24 个 Pi rule rows，其中 7 个 same semantics、17 个 mapped/difference stated，并将 Pi session 投影到 DSH 原生 session/lineage/compaction。[E3703a75c32c40060736f877d](https://github.com/weijiafu14/pi2dsh/blob/f200553784f3e594acefcd8a653161b70f20cc70/docs/capabilities/sessions.md)、[Ed458c2b7cbf1227ca70f56c1](https://github.com/weijiafu14/pi2dsh/blob/f200553784f3e594acefcd8a653161b70f20cc70/docs/capabilities/sessions.md)
- `dsh-agent-teams` 的 Alpha.2 兼容性文档提供了 real member spawn/resume/complete/dependency report、服务 disposal 和 HTTP auth fail-closed 的项目级证据；同时明确插件迁移要 pin DSH exact Alpha.2，旧 RC 不可直接加载。[Ee5520f033c1907dae24c4b71](https://github.com/NanmiCoder/dsh-agent-teams/blob/232a338fc9a0d393f118912386f67e7f3a6c67d6/docs/alpha2-compatibility.md)、[Eb00c6383125d603d56f77de4](https://github.com/NanmiCoder/dsh-agent-teams/blob/232a338fc9a0d393f118912386f67e7f3a6c67d6/docs/alpha2-compatibility.md)
- `dsh-path-anonymizer` 自己声明“message redaction, not a security sandbox”，不拦 tool call、tool argument、tool result 或 filesystem access；这是一个很重要的反例：生态有安全相关插件，不代表它提供 C2 owner。[E0ab6150086e79145c07f3ef7](https://github.com/yzhangjy/dsh-path-anonymizer/blob/610b01261db9d9ad28eed883631fd73dcfc3d11a/README.md)
- `dsh-remote` 明确扩展 SSH、SFTP、remote write、port forwarding 与 keychain password；它能补远程项目工作流，也同时扩大 credential/network/remote effect 面。[E6acc038c4ee2a842bcc6ec64](https://github.com/flymysql/dsh-remote/blob/bf3573c8a7e767136a64d1edc9f5614026732626/README.md)、[Ed5a825624a7db250d024408a](https://github.com/flymysql/dsh-remote/blob/bf3573c8a7e767136a64d1edc9f5614026732626/package.json)
- `sandbase-harness` 的 API matrix 同时列出 sessions、artifacts、files、environments、webhooks、scheduled deployments、outcomes、metrics 和 restart；但该项目自己把它描述为本地 runtime/API，不是 DSH plugin，且 custom tool registration 仍是 planned。[E31939fe001be456cd8348f](https://github.com/sandbaseai/sandbase-harness/blob/a634eb43145a1e454339fc850931eaebea4a4a23/docs/api-matrix.md)、[E032f8a88b466c54a9c8f3454](https://github.com/sandbaseai/sandbase-harness/blob/a634eb43145a1e454339fc850931eaebea4a4a23/docs/api.md)

### 4.2 生态证据不能直接变成 ZWorkbench 通过证据

当前 v3 ledger 的 9 个 unknown 包括 `dsh-context` 的小团队成本、`dsh-memoir` 的 capability/cost、`dsh-routing-suite` 的 capability/security、`dsh-config-migrate` 的 capability，以及若干插件的运维成本。[`unknownCriteria`](./w8-deepseek-plugin-ecosystem.v3.ledger-response.json)

另外存在三个结构性限制：

1. **版本错位**：核心当前 ledger 是 Alpha.4；`dsh-agent-teams` 的公开兼容材料固定 Alpha.2；前一轮候选运行证据固定 Alpha.1。不能把不同 Alpha 的 package build 结果拼成一个通过结论。[Ee5520f033c1907dae24c4b71](https://github.com/NanmiCoder/dsh-agent-teams/blob/232a338fc9a0d393f118912386f67e7f3a6c67d6/docs/alpha2-compatibility.md)、[E2cce435d92a1bc0fc1c3119e](https://github.com/deepseek-ai/deepseek-harness/blob/4e84901e6471b79ec0338099867ebb4606d12bb5/apps/cli/package.json)
2. **状态 ownership**：市场 backup 是 profile/plugin configuration；chat-import 是 transcript import/sync；memoir 是 project memory；context/usage 是 projections。它们都不能自动成为 ZWorkbench 的唯一 `run/thread/turn/effect/result` canonical owner。
3. **安全 ownership**：path anonymizer 不等于 sandbox；remote/IM/plugin marketplace 把新的网络、凭据、远端数据和供应链带入；没有 request→policy→decision→effect/denial 的宿主链路，C2/C4 仍应 HOLD。

## 5. 重新进行 ATAM：新的敏感点

| 敏感点 | 新问题 | 当前状态 |
|---|---|---|
| SP-E1 插件 ABI/版本 | DSH alpha 变更是否能让外部插件静默失效？是否有 dsh target、lockfile、source pin 和兼容矩阵？ | 生态文档有版本锚和 exact-alpha 示例；ZWorkbench 尚未实测 |
| SP-E2 远程安装/registry | 实时 catalog、npm mapping、Gist/WebDAV 备份是否把远端供应链变成启动依赖？ | `dsh-market` 明确实时读取且无 stale fallback；需要本地 allowlist/pin |
| SP-E3 状态分裂 | market/config、memory、context、session import 与 owner ledger 是否各自保存同一事实？ | 已识别为主要架构风险；必须单一 owner |
| SP-E4 安全叠加 | 插件能否绕过 adapter/host boundary，新增 shell、网络、凭据、remote write？ | path anonymizer 的反例证明插件安全能力不能泛化；C2/C4 未关闭 |
| SP-E5 自动化/多 Agent | agent-teams、IM、外部 queue 的任务/成员/通知/重试是否与 C3/C4 语义一致？ | 局部项目证据存在，ZWorkbench 合同 unknown |
| SP-E6 观测/回放 | context/usage/replay/import 是 projection、log、migration 还是 deterministic replay？ | 价值明确，mode 和 effect boundary 仍需单测/集成测 |
| SP-E7 退出与合规 | 每个插件的 NOTICE、远端账户、Webhook、备份和卸载是否可独立退出？ | config/plugin migration 有帮助；真实生命周期与责任未签核 |

ATAM 的新决策：**不再用“核心缺口”拒绝 DeepSeek，但也不以“存在插件”自动放行；把“插件组合能否形成小团队可维护的单一 owner 工作台”作为下一轮架构问题。**

## 6. 重新进行 CBAM：不是拼盘，而是最小可验证组合

### 6.1 方案比较

| 方案 | 增量收益 | 继承成本 | 当前姿态 |
|---|---|---|---|
| Codex + 现有 owner | 已有 C1–C7 证据链和单一 owner | 继续处理 Codex native/C7 阻断 | 当前产品主线 |
| DeepSeek core 单体 | 插件 ABI、ACP/profile 和 DSH 原生代码闭环 | 仍需 owner 补 C3–C7 | 不足以单独改判，但不应被视作终局 |
| DeepSeek + 受控 plugin-composed bundle | 用 context、routing、memory、migration 等复用生态供给，可能降低自建成本 | 版本矩阵、插件 allowlist、单一 state owner、逐插件 C2–C7 回归 | **一等挑战方案，进入验证** |
| DeepSeek + market/registry 全自动拼盘 | 低摩擦发现和安装 | 远端 registry、npm、热更新、供应链、不可预测依赖和退出风险 | 不作为首个验证组合 |
| DeepSeek + AgentRQ/Sandbase 等 outer runtime | 可能快速得到队列、API、webhook、metrics | 第二运行时、服务、凭据、事件和退出责任；不再是小薄层 | 后置/单独决策 |
| 从零重写所有缺口 | 完全控制语义 | 失去生态杠杆，重复实现 loop、tool、state、replay、security、ops | 排除 |

### 6.2 建议的最小 plugin-composed 评估包

这不是生产安装清单，而是评估顺序。每次只加入一个插件，保持能回滚到 core-only：

1. **Core + `dsh-context`**：验证 C6 观测价值、脱敏、session/event schema，不把 projection 当 canonical ledger。
2. **Core + `dsh-routing-suite`**：验证 C5 路由/降级 reason；严格区分模型 Provider failover 与工具/搜索 fallback。
3. **Core + `dsh-memoir`**：验证跨 session project memory 是否可作为独立 projection，且不写入 owner 的 run/effect truth。
4. **Core + `dsh-config-migrate`**：验证插件/profile/config 可迁移；另外用 owner-backed backup/restore 验证真实 composition state，不能只看插件导出。
5. **Core + `dsh-chat-import` 或 `pi2dsh`**：二选一验证跨 Harness 迁移，先选有明确当前用户任务的一项。
6. **暂不纳入首批**：`dsh-remote`、`dsh-im`、实时 `dsh-market`、AgentRQ、Sandbase；它们属于远程/外部控制面或供应链扩大，需另开安全和 C7 节点。

### 6.3 成本判断

在没有实测之前，不能把“插件数量”换算成人日。用于 CBAM 的量级门槛保持：

- `L`：≤3 工程日、不新增常驻服务、不改 durable schema；适合单个观测或纯 projection 插件的试验。
- `M`：1–2 工程周、一个明确 adapter/协议面；适合 routing/memory/migration 的隔离验证。
- `H`：2–6 工程周、涉及权限、状态、事件、Provider 或跨版本矩阵；remote、agent-teams、replay bridge 至少按此估算。
- `VH`：>6 工程周，或引入第二运行时/常驻服务/全生态兼容；AgentRQ/Sandbase/自动市场拼盘默认落入此类。

只有当插件组合相对 Codex 现有 owner **减少**自建/维护工作，并且新增 C7/退出成本不超过收益，才允许把收益记入 CBAM；“插件已经有实现”不等于“ZWorkbench 不需要维护”。

## 7. 新的公平验证门槛

### E1：插件 ABI 与版本封账

- 固定一个 DeepSeek alpha 版本，并为每个插件固定 commit、package version、lockfile 和 `dshTarget`。
- core-only、core+plugin 两组均能 fresh install/build/boot；旧 alpha 不得静默加载新 plugin。
- 阈值：版本/来源/lockfile 字段 `100%`；不兼容必须显式 fail，不能 fallback 到未声明版本。

### E2：插件 provenance 和安装安全

- 不使用实时 registry 作为评估输入；先从 pinned commit/本地 tarball 安装。
- 记录 package tree、依赖、许可证、安装脚本、网络/凭据声明和卸载方式。
- 阈值：未 allowlist 的 package/source `0` 次；install script、网络和凭据行为逐项可观察；未知安全边界直接 HOLD。

### E3：C2/C4 安全与副作用

- 同一插件组合重跑 fail-closed adapter、宿主审批、任意 shell/子进程、workspace 越界、secret/network 和 effect retry。
- 阈值沿用 W6：关键拦截 `100%`，未授权执行 `0`，危险副作用重复 `0`，未知 effect 不自动重试。

### E4：C3/C5/C6 capability parity

- 每个插件只能声明其实际拥有的能力；scheduler、attempt、effect、fallback、degradation、replay mode 继续由唯一 owner 记录。
- 阈值：C3 幂等有效副作用 `1`、重复额外副作用 `0`；C5 silent semantic switch `0`、fallback reason 记录率 `100%`；C6 simulated replay `5/5`、未批准 live effect `0`。

### E5：小团队 C7 与退出

- 每个被采用插件单独执行 fresh install、升级/回滚、backup/restore、故障定位、卸载和网络/账户退出检查。
- 阈值：首次安装 ≤`90` 分钟；升级、backup/restore、预制故障定位各 ≤`30` 分钟；MVP 常驻服务 ≤`3`；不依赖额外专家；卸载后无隐性远端任务、Webhook、备份或凭据残留。

### E6：组合收益门槛

- 在同一任务集和固定 Provider 上，对照 Codex 当前路线与 DeepSeek plugin-composed bundle。
- 只有出现一个**非重复、可测量、可复现**的优势（例如同等安全/可回放约束下显著减少自建维护面，或完成 Codex 路线不具备的用户任务），并且 E1–E5 全部通过，才重开“替换/并列主 Harness”决策。

## 8. 现阶段结论

本轮挑战推翻的是前一轮过强的表述，不是直接推翻 Codex 当前路线：

1. **被推翻/修正**：不能把“固定 DeepSeek Harness C3–C7 尚未证明”写成“DeepSeek 不能通过插件生态补齐”。
2. **仍然成立**：插件存在、插件 README 自述、市场可安装、或某个项目有自己的兼容性测试，都不等于 ZWorkbench C1–C7 和单一 owner 已签核。
3. **新的架构候选**：DeepSeek core + pinned plugin-composed bundle + ZWorkbench 单一 composition/policy/replay owner，值得与 Codex + owner 做一次同形状纵向切片对照。
4. **当前产品决策**：Codex 仍保持当前生产主线；DeepSeek 升级为“一等挑战架构”，不再是“已知不足而无需继续评估”的候选。
5. **下一节点**：先执行 E1/E2，选 `dsh-context`、`dsh-routing-suite`、`dsh-memoir`、`dsh-config-migrate` 中的最小组合做隔离兼容和 provenance 验证；不先做自动市场安装，也不先接远程/IM/外部控制面。

本记录不构成任何第三方项目的安全、合规、许可证或商业保证；所有第三方能力均需以固定版本和本地复现为准。
