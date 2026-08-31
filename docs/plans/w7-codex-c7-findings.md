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

这关闭了“没有 owner 实现”的产品缺口，但尚未关闭 C7 Gate C：当前 owner 还没有
接入 Codex app-server 的真实工作台任务流，不能把 owner 的隔离单元测试当成真实
composition state。`evaluation/fixtures`、Codex `CODEX_HOME` 和机器审计目录仍
不计入 C7 真实 state；下一节点 `1-8-5` 完成一次受控真实 Codex→owner flow 后，才可
重新做 backup/restore、故障定位和退出责任审计。

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

## 2. 最新机器审计结果

最新正式运行 summary：[`summary.json`](../../evaluation/runs/w7-codex-c7-20260831T032735-294299Z/summary.json)

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
| human timing | `unknown` | 未提供真实单一操作者 stopwatch |
| candidate install | `not_exercised` | 只生成安装 runbook，不改全局安装 |
| candidate upgrade/rollback | `not_exercised` | 只记录 snapshot/rollback plan，不执行真实升级/回滚 |
| license declared | `Apache-2.0` | 固定源码 LICENSE 和本机 package metadata 声明一致 |
| commercial/notice review | `unknown` | 不能由单一 LICENSE 文件覆盖所有依赖、NOTICE、商标和商业边界 |
| source-to-binary provenance | `unknown` | 源码 package `0.0.0-dev` 与本机 package `0.139.0` 的发布/构建链未被 attestation 证明 |
| C7 / G7 signoff | **`unknown/stop`** | 关键 unknown 未达到冻结的放行阈值 |

`unknown/stop` 是保守停止条件，不是测试失败；它表示机器审计已经可复核，但候选
生命周期签核所需的关键真实证据尚未产生。

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
upgrade plan，不切换真实版本、不修改全局 package、不做真实回滚。因此不能回答升级
后的 config/schema/tool compatibility、downgrade 可行性、数据迁移或失败恢复。升级
和回滚的人工门、候选 action gate 均保持 `unknown`。

### 3.4 backup_restore

fixture 在 case-local composition state 中写入 C2-C6 identity，复制 backup，注入
`corrupted` 状态，再恢复并核对 digest 和 `healthy` 状态。它证明了外部 composition
ledger 可使用可逆文件完成最小 backup/restore contract，未触碰候选数据或外部数据。
它不等于真实生产 ledger 的备份保留、加密、跨版本迁移和灾难恢复已通过。

### 3.5 fault_diagnosis

fixture 生成固定 `candidate_provenance_unknown` 故障，使用同一 `fault_id`/`run_id`
产出 bounded diagnosis，并明确建议“不宣称 reproducible source build，在升级时重跑
审计”。这证明未知会被诊断并保留，不会静默升级为 pass；不证明所有生产故障都能在
30 分钟内定位。

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
| `R-C7-01` 安装无法由个人完成 | runbook 和入口可复核；真实安装未执行 | 候选发布包 + 操作者 | 不放行；必须做一次真实单人安装并记录 ≤90 分钟 |
| `R-C7-02` 升级破坏状态或无法回滚 | case-local snapshot/rollback plan | 候选 package + composition owner | 不放行；需要真实升级/回滚和旧 identity 恢复证据 |
| `R-C7-03` ledger 损坏后无法恢复 | 3 次 case-local restore digest/health oracle | composition owner | 仅收窄 fixture 风险；生产 retention、加密、跨版本迁移未测 |
| `R-C7-04` 故障定位超过小团队能力 | fault/run 关联和 bounded diagnosis 通过 | 候选诊断面 + composition owner | 机器通过不替代人工 ≤30 分钟；需真实 stopwatch |
| `R-C7-05` 服务拼盘超出维护能力 | 计入 2 个，低于上限 3 | 候选运行时 + 一个薄 adapter | 当前可保留；新增服务须重新走 C7 |
| `R-C7-06` 许可证/NOTICE/商业边界遗漏 | Apache-2.0 一手来源已记录 | 项目维护者 + 合规审查 | `commercial_boundary` 和 notice review 仍 unknown |
| `R-C7-07` 发布二进制无法追溯到源码 | tag/commit 和本机 digest 固定；commit API 为 unsigned；source package `0.0.0-dev` vs installed `0.139.0` | 发布供应链 | provenance unknown；不能宣称 reproducible build |
| `R-C7-08` 退出留下真实残留 | case-local 导出/导入/删除达到零残留 | composition owner + 外部账户/数据 owner | 仅机器 fixture 通过；真实账户、远程资源、备份 retention 未审计 |

ATAM 结论：本轮把 C7 的主要风险从“没有生命周期证据”收窄为“机器 contract 已有
证据，但真实操作者、发布 provenance、法律边界和生产退出责任仍未关闭”。停止条件
应保持可见，不通过补充解释或机器时间来绕过。

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
- Human 已确认：真实 composition state 不存在，`backup/restore` 固定保持 `unknown`；
  现有 fixture、机器审计 state 和 Codex `CODEX_HOME` 不得用于回填该 Gate。
- 只有以下证据齐全后才可签 C7：四类真实单人 stopwatch（安装 ≤90 分钟，其余各
  ≤30 分钟）、真实 candidate install、upgrade/rollback、许可证/NOTICE/商业边界
  审查，以及可复核的发布 artifact provenance。
- `1-6` 继续负责基于 C1-C7 的 ATAM/CBAM 采用姿态；应携带 C4 native approval unknown、
  C7 unknown/stop 和 source-to-binary provenance unknown。
