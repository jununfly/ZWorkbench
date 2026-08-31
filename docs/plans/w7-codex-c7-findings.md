# W7 Codex C7 运维、许可证与退出审计结果

状态：`machine-contract-pass / notice-commercial-boundary-mapped / candidate-signoff-unknown-stop` ·
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
- Human/agent fresh-install 原始日志：[`fresh-install.log`](../../evaluation/evidence/w7-codex-c7/fresh-install.log)
- Human fresh-install stopwatch-bound 原始日志：[`fresh-install-human-bound.Vta7cz`](../../evaluation/evidence/w7-codex-c7/fresh-install-human-bound.Vta7cz)
- npm signatures/attestation 验证：[`npm-audit-signatures.txt`](../../evaluation/evidence/w7-codex-c7/npm-audit-signatures.txt)
- owner 跨版本兼容性 runner：[`run_codex_owner_upgrade_compat.py`](../../evaluation/runner/run_codex_owner_upgrade_compat.py)
- vendor/transitive 依赖 ledger：[`w7-codex-c7-dependency-ledger.md`](./research/w7-codex-c7-dependency-ledger.md)

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
| human timing | `fixture-level-pass` | 单一操作者的 install `17.01s`、upgrade/rollback `14.35s`、backup/restore `12.38s` 和预制故障定位 `2.85517min` 均低于阈值；install stopwatch 已与同一次 raw log 绑定 |
| candidate install | `pass-at-install-timing-and-identity-level` | 临时 prefix 全新安装 `0.139.0`；同一次 raw log 固化安装输出、版本、help、npm tree 和四个 artifact digest，SHA-256 已记录；完整 C7 仍 unknown/stop |
| candidate upgrade/rollback | `partial-exercised` | 临时 C7 prefix 中真实完成 `0.138.0 → 0.139.0 → 0.138.0`，版本与 app-server help 已存档；另有同一 owner 的跨版本 machine probe 通过；真实发布环境/人工 gate 仍未签核 |
| license declared | `Apache-2.0` | 固定源码 LICENSE 和本机 package metadata 声明一致 |
| commercial/notice review | `bounded-evidence / signoff-open` | 已有固定版本的一手来源与工程边界地图；逐包 NOTICE clearance、商业/API/账户/数据模式和商标责任人签核仍缺 |
| source-to-binary provenance | `pass-at-release-level` | root/platform npm SLSA attestation 绑定 `rust-v0.139.0` / `a7dff904…`；官方 tarball 与本机安装内容核对通过；npm CLI attestation 验证通过；独立重建仍开放 |
| C7 / G7 signoff | **`unknown/stop`** | 关键 unknown 未达到冻结的放行阈值 |

`unknown/stop` 是保守停止条件，不是测试失败；它表示机器审计和部分人工生命周期
证据已经可复核，但候选生命周期、法律和退出签核所需的关键证据仍未全部产生。

本轮新增的 owner-backed 定向重跑 summary：[`summary.json`](../../evaluation/runs/w7-codex-owner-c7-20260831T082149-262592Z/summary.json)。
它只重跑 `backup_restore` 与 `exit`，结果为 `6/6 machine pass`，并要求每个 case
先由真实 Codex app-server adapter 产生 SQLite owner state；详细结果见第 8 节。它
关闭的是此前“没有真实 composition state”对这两个机器控制的阻断，不改写上面的
全量候选生命周期、法律和发布供应链结论。

新增的 owner 跨版本兼容性 probe：[`summary.json`](../../evaluation/runs/w7-codex-owner-upgrade-20260831T095350-497892Z/summary.json)。
它在临时 npm prefix 中真实安装 `0.138.0`、升级到 `0.139.0`、再回滚到 `0.138.0`，
并让同一 SQLite owner 依次承载三个成功 run。中间注入一次受控 app-server 启动失败，
该 run 被 owner 持久化为 `failed`，且没有 effect；owner 关闭后重开，最终 state digest
仍为 `087800966a7b586dbe2f0122b513cda7dddaf31bb1df347b207267fb185d0242`。该 probe
的 machine checks 为 `15/15 pass`，把“schema/config/ledger/failure recovery 完全未知”
收窄为“本机 owner contract pass”；它不证明真实生产 schema migration、候选内部状态
或人工升级耗时已通过。

## 3. 六类 fixture 证据

### 3.1 identity

只读执行固定候选的 `--version` 和 `app-server --help`，并核对 wrapper、npm package、
platform package、vendor binary digest。`app-server` 帮助中可见 `stdio://` 默认
transport 和 `generate-json-schema`，但命令仍标记为 experimental。该 case 证明
入口可观察、身份可绑定，不证明 app-server 协议在未来版本稳定。

### 3.2 install

fixture 原本只记录固定 release 的安装 runbook；本次 Human 在临时 C7 prefix
真实执行了 `npm install -g @openai/codex@0.139.0`，并由单一操作者计时
`17.01 秒`。同一次 raw log 固化 `0.139.0`、`app-server --help`、npm tree、四个
artifact digest 和结束标记，日志 SHA-256 为
`6db2fe3abaf3febe72ab6a6acbd282e587daf1876b7c5cb255fd66e7eaefecb5`；四个 digest
与候选 manifest 一致。此前机器 fresh-install `2.314s` 日志仍作为独立机器证据保留，
不替代人工 stopwatch。该项关闭 fresh-install 的人工日志绑定，但不回答真实生产
凭证、远程责任或失败恢复边界，也不证明 app-server 原生调度、approval、Provider
routing 或 replay 能力。

### 3.3 upgrade

fixture 在隔离 workspace 保存候选 identity snapshot 和 rollback target，生成 dry-run
upgrade plan，不修改全局 package。另有 Human 在临时 C7 prefix 中真实完成
`0.138.0 → 0.139.0 → 0.138.0`，总耗时 `14.35 秒`，并保存版本与
`app-server --help` 原始日志（见 [`upgrade-rollback.log`](../../evaluation/evidence/w7-codex-c7/upgrade-rollback.log)）。
这关闭了“完全没有候选版本切换证据”，但仍不能回答 composition config/schema/tool
compatibility、durable state migration 或非临时安装环境。新增跨版本 owner probe 已
验证固定 v1 owner schema、稳定 adapter config identity、历史 run 保留和受控失败恢复；
因此本机兼容性项为 machine-pass，候选 C7 gate 仍保持 partial/unknown。

### 3.4 backup_restore

fixture 在 case-local composition state 中写入 C2-C6 identity，复制 backup，注入
`corrupted` 状态，再恢复并核对 digest 和 `healthy` 状态。它证明了外部 composition
ledger 可使用可逆文件完成最小 backup/restore contract，未触碰候选数据或外部数据。
Human 随后在同一隔离 owner-backed case 上完成一次 backup/restore，报告耗时
`12.38 秒`（`0.2063 分钟`），验证输出 `status: pass` 且 20 个 operation checks 全部为
`true`；原始证据见 [`human backup/restore README`](../../evaluation/runs/w7-codex-c7-human-20260831T180332/README.md)。
它不等于真实生产 ledger 的备份保留、加密、跨版本迁移和灾难恢复已通过。

### 3.5 fault_diagnosis

fixture 生成固定 `candidate_provenance_unknown` 故障，使用同一 `fault_id`/`run_id`
产出 bounded diagnosis，并明确建议“不宣称 independent reproducible rebuild，在升级时
重跑审计”。跨版本 probe 另以受控 `CodexProtocolError` 验证失败 run 会落入 owner ledger。
本轮 registry 证据已关闭 release-artifact 层的 provenance unknown，但独立重建与其他
安装渠道等价性仍需保持边界。这证明未知会被诊断并保留，不会静默升级为 pass；不证明
所有生产故障都能在 30 分钟内由单人定位，人工 stopwatch 仍缺。

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
| `R-C7-01` 安装无法由个人完成 | 临时 prefix 全新安装 `17.01s` 由单人报告；同一次 raw log 固化版本/help/npm tree/四个 artifact digest，日志 SHA-256 `6db2fe3a…` | 候选发布包 + 操作者 | fresh-install 人工时间与 raw log 已绑定；完整 C7 仍受 NOTICE/商业边界、真实退出责任等阻断 |
| `R-C7-02` 升级破坏状态或无法回滚 | 临时 prefix `0.138.0 → 0.139.0 → 0.138.0`，耗时 `14.35s`，版本/help log 已固化；同一 owner probe `15/15` machine pass | 候选 package + composition owner | 本机 schema/config/ledger/失败恢复项收窄为 pass；真实 migration 与人工 gate 仍开放 |
| `R-C7-03` ledger 损坏后无法恢复 | 3 次 case-local restore digest/health oracle；另有单人隔离 owner-backed restore `12.38s`、20/20 checks pass | composition owner | 人工时间项通过；生产 retention、加密、跨版本迁移未测 |
| `R-C7-04` 故障定位超过小团队能力 | fault/run 关联、bounded diagnosis 和受控 adapter failure persistence 通过；单一操作者完成诊断并保存结论 `2.85517min` | 候选诊断面 + composition owner | 预制 fixture 的人工时间项通过；生产故障的范围和真实远端责任未测 |
| `R-C7-05` 服务拼盘超出维护能力 | 计入 2 个，低于上限 3 | 候选运行时 + 一个薄 adapter | 当前可保留；新增服务须重新走 C7 |
| `R-C7-06` 许可证/NOTICE/商业边界遗漏 | 固定 commit/LICENSE、vendor/transitive ledger、OpenAI 服务/个人服务/使用政策/品牌一手来源及边界地图已记录 | 项目维护者 + 合规审查 | 已收窄为 `bounded-evidence / signoff-open`；逐包 NOTICE、再分发材料、商业/API/账户/数据模式和商标审查仍未签核 |
| `R-C7-07` 发布二进制无法追溯到源码 | root/platform npm SLSA attestation、npm CLI 验证、tag/commit、registry tarball integrity 和本机 bytes 均已绑定；commit API 仍为 unsigned | 发布供应链 | release-artifact provenance 已 pass；独立重建及其他安装渠道仍 unknown |
| `R-C7-08` 退出留下真实残留 | case-local 导出/导入/删除达到零残留；已明确 ZWorkbench 不拥有 Provider 侧任务、Webhook、备份或账户生命周期 | composition owner + 外部账户/数据 owner | 产品责任为本地停止/清理和数据边界披露；Provider 侧数据、备份、账单和 retention 由账户/供应商责任人处理，未验证零残留 |

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
- 只有以下证据齐全后才可签 C7：四类真实单人 stopwatch（当前 install、upgrade/rollback、
  backup/restore、预制故障定位均已有报告且 install raw log 已绑定）、完整 candidate install、
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
pass-at-release-level，并把 NOTICE/商业边界从“完全未知”收窄为有一手条款和停止边界的
工程地图。随后单一操作者在隔离 owner-backed case 上完成 backup/restore，
耗时 `12.38 秒`，低于 ≤30 分钟阈值，20/20 operation checks 通过，关闭该人工时间项的
fixture-level gate。随后单一操作者在预制 fault fixture 上完成读取、关联、分类和 bounded
diagnosis 保存，耗时 `2 分 51.31 秒`，低于 ≤30 分钟阈值；诊断文本已保存并与
`fault_id/run_id` 对齐。C7 总体仍是 `unknown/stop`，因为逐包 NOTICE/商业边界、独立
重建、远端资源退出和 Codex 原生 approval 的完整签核状态仍未改变。

## 9. 跨版本 owner 兼容性与依赖盘点（2026-08-31）

跨版本 probe 的事实结果：

- `0.138.0`、`0.139.0`、回滚后的 `0.138.0` 安装、版本输出和 `app-server --help`
  均通过；所有 platform package version 与目标版本匹配；
- 同一 owner 始终为 `zworkbench-composition-owner/v1` / schema version `1`；固定 adapter
  config identity SHA-256 为 `29b53c591b9f7ed27ef3017cd47189c8e75e4f1812281428fff628f6d50a5b45`；
- 回滚后 owner 有 4 个 run、28 个 event、0 个 effect，且失败 probe 的 terminal 状态和
  之前的成功 run 均保留；owner reopen digest 与关闭前一致；
- 受控失败返回 `CodexProtocolError: controlled startup fault`，被记录为 `failed`，没有
  伪造成功或执行副作用。

依赖 ledger 已确认 root/platform npm declared license、vendor `codex`/`rg`/PCRE2/zsh
边界及固定 commit Cargo.lock 的 `1332` 个 package entry（workspace `123`、registry
`1197`、git `12`）。它与一手来源和边界地图一起把 NOTICE/商业边界收窄为
`bounded-evidence / signoff-open`，但仍明确标记逐包 SPDX/NOTICE、vendor 再分发文本、
商业/API/商标和独立重建为 open；不能用该盘点代替合规责任人签核。

## 10. NOTICE/商业边界处理结果（2026-08-31）

本轮没有把“Codex 源码声明 Apache-2.0”扩大解释为整个 ZWorkbench 发行物或服务的
许可结论，而是形成了一个可执行的边界地图：

| 路径 | 当前工程处置 | 仍需什么才能改变处置 |
|---|---|---|
| 个人/小团队成员各自安装固定版本，在本机受控试用 | 可继续；ZWorkbench 不分发 Codex artifact | 继续保持版本、provenance、凭证和敏感数据边界，并由使用者承担适用条款责任 |
| 在 ZWorkbench npm、安装器、容器或压缩包中捆绑 Codex | 停止再分发 | 完整 root/platform/vendor/Cargo 逐包许可证、版权、NOTICE/例外和发布材料 clearance |
| 用 OpenAI API 为自己的产品提供能力 | 条件路径，当前不签核 | 确认适用服务协议、使用政策、数据/隐私、地区、账户/API key 和产品责任 |
| 用个人 ChatGPT 账户驱动共享工作台或对外 SaaS | 停止 | 不能用个人服务条款替代开发者/API 集成审查；需重新确定合法、合约和账户路径 |
| 使用 OpenAI/Codex/GPT logo、名称或营销背书 | 默认停止 logo/背书用法 | 商标责任人审核事实性兼容性说明、命名、截图和视觉资产 |

证据入口为 [`w7-codex-c7-primary-sources.md`](./research/w7-codex-c7-primary-sources.md)、
独立核查 [`w7-codex-c7-notice-commercial-primary-sources.md`](./research/w7-codex-c7-notice-commercial-primary-sources.md)、
[`w7-codex-c7-license-provenance-audit.md`](./research/w7-codex-c7-license-provenance-audit.md)
和 [`w7-codex-c7-notice-commercial-boundary.md`](./research/w7-codex-c7-notice-commercial-boundary.md)。
结论是 `bounded-evidence / signoff-open`，不是法律意见、再分发授权或商业批准；在
逐包 clearance、商业/API/账户/数据模式和商标/归属责任人完成签核前，C7/G7 继续
`unknown/stop`。

## 11. 真实远端退出责任准备结果（2026-08-31）

本轮建立了独立的[真实远端退出责任包](./w7-codex-c7-remote-exit-responsibility.md)。
它把远端退出拆成认证身份、Provider 数据、远端任务、webhook/集成、backup/retention、
发布制品、账单/组织和第三方项目权限，并要求每项记录资源 ID（脱敏）、数据类别、
创建来源、删除或撤销入口、第一责任人、retention、人工操作时间和验证证据。

当前 C7 fixture 仍只使用 loopback-only fake Provider；npm/GitHub 是只读证据来源，不计为
用户远端资源。真实 Provider 侧数据、任务、Webhook、备份和账单不由 fixture 验证，
因此本轮没有执行或授权任何真实删除。

当前已确认的真实工作台接入画像是多个模型厂商的 OpenAI-compatible API，各自使用
Provider-specific API key；协议兼容不代表统一合同主体或统一删除入口。具体厂商、
endpoint、账户范围（个人/团队/企业）、org/project、地区、数据/retention、账单和
责任人仍需逐厂商确认；只记录 key fingerprint，不记录 key 值，也不执行跨 Provider
批量撤销或删除。

其中已由用户确认一条具体记录：火山方舟，endpoint 为
`https://ark.cn-beijing.volces.com/api/coding/v3`，个人账户，且远端数据、任务、
Webhook 和备份存在，但 ZWorkbench 不创建或管理这些 Provider 侧资源。该记录因此是
`human-reported / externally-owned`：资源级删除由个人账户所有者/火山方舟责任人负责，
ZWorkbench 只负责本地停止调用、清理本地状态和披露数据边界。资源 ID、实际数据类别
和时间范围、任务/调度状态、Webhook 权限、备份位置与 retention、账单责任和删除/撤销
结果仍未取得；不能把火山方舟记录为已退出，也不能据此推断其他模型厂商的状态。

真实操作的安全顺序是：冻结新 run 与自动触发 → 由账户所有者确认账户/Provider/组织和
资源清单 → 导出脱敏的最小必要审计材料 → 停用 schedule/worker/webhook → 按对应供应商
规则删除数据或提交 retention 请求 → 撤销凭证和第三方权限 → 核对延迟 retention、账单
和是否重新产生写入 → 最后删除本地副本并由责任人签核。资源范围、授权、恢复窗口、
删除入口或供应商结果不明确时，必须 `safe-stop`。

关闭门槛见退出责任包第 6 节。当前产品边界已明确为
`remote_resource_lifecycle = delegated-to-provider/account-owner`，但
`provider_side_deletion = not-performed/not-verified`；C7/G7 仍因其他未签核门保持
`unknown/stop`。如果未来要签核个人账户本身的退出，才需要账户所有者补充资源级清单。
