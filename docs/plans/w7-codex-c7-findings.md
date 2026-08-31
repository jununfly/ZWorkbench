# W7 Codex C7 运维、许可证与退出审计结果

状态：`machine-contract-pass / candidate-signoff-unknown-stop` ·
`acceptance/evaluation` · 不代表 Codex 原生或 ZWorkbench 产品通过

本轮对固定 Codex Harness `0.139.0` 建立并运行了候选级 C7 audit adapter。它把
机器可复核的身份、入口、隔离、备份恢复、故障诊断、许可证元数据和退出 fixture
与 C2-C6 证据 identity 关联起来；它不替代真实单一操作者计时、真实安装/升级/回滚
或法律审查。

## 0. 产品实现进展（2026-08-31）

ZWorkbench 已实现一个真实的本地 composition owner：
[`w7-composition-owner-design.md`](./w7-composition-owner-design.md) 对应的
`src/zworkbench/composition.py` 使用单一 SQLite 文件持有 run、approval、effect、
effect-attempt、result、replay metadata 和 event durable ledger，并提供 fail-closed claim、
uncertain reconcile、bounded retry、safe-stop、export、backup 和 restore。

这关闭了“没有 owner 实现”的产品缺口。`src/zworkbench/codex_adapter.py` 已接入真实
Codex app-server 工作台任务流；但 `evaluation/fixtures`、Codex `CODEX_HOME` 和机器
审计目录仍不是 composition truth，只有 adapter 实际写入的 case-local SQLite owner
state 才进入下面的新回归证据。新的真实 owner backup/restore 与 exit 机器控制已重跑；
C7 其余人工、法律、发布供应链和远端退出门仍保持独立判断。

## 1. 审计范围和硬边界

| 项目 | 固定边界 |
|---|---|
| 候选 | Codex Harness，`codex-cli 0.139.0` |
| 源码身份 | release `rust-v0.139.0`，peeled commit `a7dff904308535e965aee87680c1fc5ef1d19eec` |
| 操作范围 | 每 case 独立 workspace 与 `CODEX_HOME`；仅 case-local 可逆文件 |
| 禁止事项 | 不改全局 `CODEX_HOME`，不真实安装/升级/回滚，不连真实 Provider/凭证/外网，不碰生产数据或不可逆用户数据 |
| 场景 | `identity`、`install`、`upgrade`、`backup_restore`、`fault_diagnosis`、`exit` |
| 重复 | 每场景 3 次，共 18 cases |
| 服务上限 | 维护常驻服务 ≤3；本 fixture 计入候选运行时 + 一个 composition owner = 2 |
| 人工阈值 | 首次安装 ≤90 分钟；升级、备份恢复、预制故障定位各 ≤30 分钟 |
| 签核条件 | 必须有单一操作者真实 stopwatch；机器 subprocess 时间不得代替人工时间 |

正式资产：

- Runner：[`run_codex_c7.py`](../../evaluation/runner/run_codex_c7.py)
- Fixture：[`c7-audit.py`](../../evaluation/fixtures/w7-codex-c7/c7-audit.py)
- 候选 manifest：[`w7-codex-candidate-manifest.json`](./w7-codex-candidate-manifest.json)
- 一手来源：[`w7-codex-c7-primary-sources.md`](./research/w7-codex-c7-primary-sources.md)
- 许可证/provenance 审计：[`w7-codex-c7-license-provenance-audit.md`](./research/w7-codex-c7-license-provenance-audit.md)
- Human upgrade/rollback 原始日志：[`upgrade-rollback.log`](../../evaluation/evidence/w7-codex-c7/upgrade-rollback.log)
- npm signatures/attestation 验证：[`npm-audit-signatures.txt`](../../evaluation/evidence/w7-codex-c7/npm-audit-signatures.txt)

## 2. 最新机器审计结果

历史全量候选审计 summary：[`summary.json`](../../evaluation/runs/w7-codex-c7-20260831T032735-294299Z/summary.json)

本次重跑的目的，是让 C7 的 C2-C6 identity ledger 绑定已完成的 C4 组合式 approval
验证；机器场景与阈值不变。此前修正后的 C7 运行
[`summary.json`](../../evaluation/runs/w7-codex-c7-20260830T172916-565440Z/summary.json)
和最初的错误 oracle 运行
[`initial summary.json`](../../evaluation/runs/w7-codex-c7-20260830T172833-703491Z/summary.json)
均保留为历史证据，不纳入最新候选结论。

最新结果已经写入并复核。早期执行曾因 fixture 把“禁止执行”的事实值直接作为正向
oracle，错误得到 `12/18`；随后已改为显式的 `*_not_executed` 安全断言。最新判定结构是：

| 维度 | 判定 | 解释 |
|---|---|---|
| machine contract | **`18/18 pass`** | 入口、artifact digest、事件完整性、隔离、零网络/真实数据、服务清单和 case-local oracle |
| human timing | `partial-evidence` | 已有单人临时 prefix 的 install `13.64s` 报告和 upgrade/rollback `14.35s` 原始日志；backup/restore、故障定位及 install 原始日志仍缺 |
| candidate install | `partial/unknown` | 有临时 prefix 安装耗时报告，但全新安装状态、版本/help 输出和原始 install log 未固化 |
| candidate upgrade/rollback | `partial-exercised` | 临时 C7 prefix 中真实完成 `0.138.0 → 0.139.0 → 0.138.0`，版本与 app-server help 已存档；未验证 composition ledger/schema 迁移兼容 |
| license declared | `Apache-2.0` | 固定源码 LICENSE 和本机 package metadata 声明一致 |
| commercial/notice review | `unknown` | 不能由单一 LICENSE 文件覆盖所有依赖、NOTICE、商标和商业边界 |
| source-to-binary provenance | `pass-at-release-level` | root/platform npm SLSA attestation 绑定 `rust-v0.139.0` / `a7dff904…`；官方 tarball 与本机安装内容核对通过；npm CLI attestation 验证通过；独立重建仍开放 |
| C7 / G7 signoff | **`unknown/stop`** | 关键 unknown 未达到冻结的放行阈值 |

`unknown/stop` 是保守停止条件，不是测试失败；它表示机器审计已经可复核，但候选
生命周期签核所需的关键真实证据尚未产生。

本轮新增的 owner-backed 定向重跑 summary：[`summary.json`](../../evaluation/runs/w7-codex-owner-c7-20260831T082149-262592Z/summary.json)。
它只重跑 `backup_restore` 与 `exit`，结果为 `6/6 machine pass`，并要求每个 case
先由真实 Codex app-server adapter 产生 SQLite owner state；详细结果见第 8 节。它
关闭的是此前“没有真实 composition state”对这两个机器控制的阻断，不改写上面的
全量候选生命周期、法律和发布供应链结论。

## 3. 六类 fixture 证据

### 3.1 identity

只读执行固定候选的 `--version` 和 `app-server --help`，并核对 wrapper、npm package、
platform package、vendor binary digest。`app-server` 帮助中可见 `stdio://` 默认
transport 和 `generate-json-schema`，但命令仍标记为 experimental。该 case 证明
入口可观察、身份可绑定，不证明 app-server 协议在未来版本稳定。

### 3.2 install

fixture 只记录固定 release 的安装 runbook 与前置身份，不执行
`npm install -g @openai/codex@0.139.0`。因此 machine preflight 可以通过，但不能
回答个人开发者第一次真实安装所需时间、权限、网络、凭证、PATH、平台包下载和失败
恢复。安装人工门保持 `unknown`。

### 3.3 upgrade

fixture 在隔离 workspace 保存候选 identity snapshot 和 rollback target，生成 dry-run
upgrade plan，不修改全局 package。另有 Human 在临时 C7 prefix 中真实完成
`0.138.0 → 0.139.0 → 0.138.0`，总耗时 `14.35 秒`，并保存版本与
`app-server --help` 原始日志（见 [`upgrade-rollback.log`](../../evaluation/evidence/w7-codex-c7/upgrade-rollback.log)）。
这关闭了“完全没有候选版本切换证据”，但仍不能回答 composition config/schema/tool
compatibility、durable state migration、失败恢复或非临时安装环境；该 gate 保持
partial/unknown。

### 3.4 backup_restore

fixture 在 case-local composition state 中写入 C2-C6 identity，复制 backup，注入
`corrupted` 状态，再恢复并核对 digest 和 `healthy` 状态。它证明了外部 composition
ledger 可使用可逆文件完成最小 backup/restore contract，未触碰候选数据或外部数据。
它不等于真实生产 ledger 的备份保留、加密、跨版本迁移和灾难恢复已通过。

### 3.5 fault_diagnosis

fixture 生成固定 `candidate_provenance_unknown` 故障，使用同一 `fault_id`/`run_id`
产出 bounded diagnosis，并明确建议“不宣称 independent reproducible rebuild，在升级时
重跑审计”。本轮 registry 证据已关闭 release-artifact 层的 provenance unknown，但
独立重建与其他安装渠道等价性仍需保持边界。这证明未知会被诊断并保留，不会静默升级为 pass；不证明
所有生产故障都能在 30 分钟内定位。

### 3.6 exit

fixture 导出候选和 composition metadata，独立复制到 import 目录并读取，再删除 export、
import 和 case-local `CODEX_HOME`，验证 workspace 零残留。它证明了机器级
export/re-import/delete 合同；没有删除真实用户数据、Provider 账户、远程资源、组织
备份或 retention 记录，因此不能把它写成“完整退出已证明”。

## 4. 与 C2-C6 的证据连接

| 证据 | 当前结论 | C7 如何处理 |
|---|---|---|
| C2 | scripted fail-closed adapter pass；宿主级强制边界仍有未知 | C7 只读取并绑定 C2 summary identity，不回填更强安全结论 |
| C3 | `pass-with-composition` | backup/restore payload 保留 C2-C6 identity；不把 schedule/幂等算作 Codex 原生 |
| C4 | composition approval/recovery `pass-with-composition`；Codex native approval `unknown` | C7 绑定新的 C4 summary，并继续传递 native approval unknown；退出 metadata 不会覆盖原生审批证据缺口 |
| C5 | `pass-with-composition` | 依赖单一 composition owner；服务/依赖/退出成本计入 owner |
| C6 | `pass-with-composition` | backup/restore 和 exit metadata 绑定 replay schema；不宣称原生 replay contract |

C7 的定位是生命周期审计，不是把 C2-C6 的 composition 结果重新包装成 Codex 原生
能力。若引入第二 Harness、gateway、workflow 或独立观测平台，必须重新计算服务、
许可证、升级、备份、排障和退出边界。

## 5. ATAM 分析

| 敏感点/风险 | 场景化证据 | 责任边界 | 残余风险/决策 |
|---|---|---|---|
| `R-C7-01` 安装无法由个人完成 | 临时 prefix 安装 `13.64s` 由单人报告；原始 install log 和全新状态未固化 | 候选发布包 + 操作者 | 时间项暂通过但整体仍 partial；补齐 fresh-install identity/log |
| `R-C7-02` 升级破坏状态或无法回滚 | 临时 prefix `0.138.0 → 0.139.0 → 0.138.0`，耗时 `14.35s`，版本/help log 已固化 | 候选 package + composition owner | 时间与版本回滚项暂通过；仍需 schema/config/ledger identity 与失败恢复证据 |
| `R-C7-03` ledger 损坏后无法恢复 | 3 次 case-local restore digest/health oracle | composition owner | 仅收窄 fixture 风险；生产 retention、加密、跨版本迁移未测 |
| `R-C7-04` 故障定位超过小团队能力 | fault/run 关联和 bounded diagnosis 通过 | 候选诊断面 + composition owner | 机器通过不替代人工 ≤30 分钟；需真实 stopwatch |
| `R-C7-05` 服务拼盘超出维护能力 | 计入 2 个，低于上限 3 | 候选运行时 + 一个薄 adapter | 当前可保留；新增服务须重新走 C7 |
| `R-C7-06` 许可证/NOTICE/商业边界遗漏 | Apache-2.0 一手来源已记录 | 项目维护者 + 合规审查 | `commercial_boundary` 和 notice review 仍 unknown |
| `R-C7-07` 发布二进制无法追溯到源码 | root/platform npm SLSA attestation、npm CLI 验证、tag/commit、registry tarball integrity 和本机 bytes 均已绑定；commit API 仍为 unsigned | 发布供应链 | release-artifact provenance 已 pass；独立重建及其他安装渠道仍 unknown |
| `R-C7-08` 退出留下真实残留 | case-local 导出/导入/删除达到零残留 | composition owner + 外部账户/数据 owner | 仅机器 fixture 通过；真实账户、远程资源、备份 retention 未审计 |

ATAM 结论：本轮把 C7 的主要风险从“没有生命周期证据、没有发布 provenance”收窄为
“机器 contract 和 npm release-artifact provenance 已有证据，但真实操作者、独立构建
边界、法律边界和生产退出责任仍未关闭”。停止条件应保持可见，不通过补充解释或机器
时间来绕过。

## 6. CBAM 分析（个人开发者/小团队约束）

继续采用“一个主 Harness + 一个必要薄 composition owner”的最小路线假设，理由是
当前 C3-C6 已证明该薄层能够承接 durable、routing、replay 和 policy ledger，而 C7
把它的生命周期责任集中到两个维护对象：候选 runtime 和 composition owner。

| 选项 | 增量收益 | 增量成本/风险 | 当前决策 |
|---|---|---|---|
| Codex + 一个薄 adapter | 复用真实 Codex入口；维护服务计数为 2；C2-C6 关联字段有单一 owner | schema、版本回归、ledger 备份、故障排查、退出由小团队承担 | 保留为首选候选路线，但 C7 不签核 |
| 再加第二 Harness | 可能覆盖另一模型/工具面 | 复制安装、升级、凭证、sandbox、事件和退出责任；本轮无边际收益证据 | 暂不引入 |
| LiteLLM / router | C5 可能复用 Provider 路由 | 常驻网关、secret、能力等价性、许可证和迁移成本 | 只有当路由收益超过 C7 成本才重评 |
| Temporal/LangGraph / scheduler | 可提供 durable workflow 或调度抽象 | 服务数、状态迁移、升级、备份、排障和退出复杂度上升 | 不在当前最小组合中 |
| 独立观测平台 | 可能减少查询成本 | 新部署/存储/隐私/许可证/retention/退出 owner | C6 adapter 够用前不引入 |

CBAM 的硬约束：任何新组合件必须以同一 C2-C7 矩阵证明它减少了明确风险，并重新
计入维护服务（上限 3）、人工安装/升级/恢复/排障时间和退出成本；不能只用功能数量
或机器运行时间证明“值得增加”。对个人开发者/小团队，当前最有价值的是保持单一
composition owner、可删除 ledger、case-local 可回放和显式未知，而不是扩大拼盘。

## 7. 决策和下一节点

- `1-5` 的审计工作可以完成并在路线图中标记 `completed`。
- C7 结论必须保持 `unknown/stop`，不能写成 C7 通过或 G7 通过。
- 在 `1-8-5` 之前，Human 已确认真实 composition state 不存在；该历史结论不再用于
  新的 owner-backed machine control。现有 fixture、Codex `CODEX_HOME` 和审计目录仍
  不得冒充 owner state。
- `1-8-5` 的真实 owner 隔离回归已关闭 C7 backup/restore 与 exit 的“无真实 state”阻断；
  它只覆盖 case-local SQLite owner，不覆盖候选原生数据、远端账户、组织 retention
  或生产灾难恢复。
- 只有以下证据齐全后才可签 C7：四类真实单人 stopwatch（当前仅 install 与
  upgrade/rollback 有 partial 记录，其余各 ≤30 分钟门仍未填）、完整 candidate install、
  upgrade/rollback 的 schema/config/ledger 证据、许可证/NOTICE/商业边界审查，以及对
  release provenance 的信任边界/独立重建结论。
- `1-6` 继续负责基于 C1-C7 的 ATAM/CBAM 采用姿态；应携带 C4 native approval unknown、
  C7 unknown/stop 和 source-to-binary 的 release-artifact pass / independent rebuild
  unknown 分层结论。

## 8. 接入真实 owner 后的 C7 backup/restore 与退出回归（2026-08-31）

正式 runner：[`run_codex_owner_c7.py`](../../evaluation/runner/run_codex_owner_c7.py)

正式证据：[`summary.json`](../../evaluation/runs/w7-codex-owner-c7-20260831T082149-262592Z/summary.json)

本轮固定 Codex `0.139.0`，每个 case 使用独立 `CODEX_HOME`、task workspace、SQLite
owner 和 loopback-only fake Provider；真实流程先经 adapter 完成
`initialize`、`thread/start`、`turn/start`、`turn/completed`，再执行 C7 操作。每个 owner
snapshot 均包含 completed run、真实 `thread_id`/`turn_id`、Provider identity、
`recorded_view` replay metadata 和 `adapter.initialized/thread/turn` 结果；不把 Codex
内部 SQLite 或 rollout 文件当 composition state。

| 场景 | 重复 | 机器结果 | 关键证据 |
|---|---:|---|---|
| `backup_restore` | 3 | `3/3 pass` | SQLite `composition.sqlite3`、`state.json`、manifest、integrity check；恢复到独立 DB 后 state digest 与完整 snapshot 一致 |
| `exit` | 3 | `3/3 pass` | `export_state` + 独立 backup restore；删除 case workspace、owner DB 和 `CODEX_HOME` 后零残留 |

汇总为 `6/6 machine pass`。维护对象按 2 个计数（Codex app-server + SQLite owner），
fake Provider 仅为 case-local test process；无真实凭证、无生产数据、无外部网络，且不
声称删除远端 Provider、账户、组织备份或 retention 数据。

因此，之前“无真实 composition state”对 C7 backup/restore 和 exit 机器控制的阻断已
关闭；本轮也把 source-to-binary 从完全 unknown 收窄为 npm release-artifact provenance
pass-at-release-level。C7 总体仍是 `unknown/stop`，因为本轮没有改变人工 stopwatch、
真实候选安装/升级/回滚、NOTICE/商业边界、独立重建、远端资源退出和 Codex 原生
approval 的完整签核状态。
