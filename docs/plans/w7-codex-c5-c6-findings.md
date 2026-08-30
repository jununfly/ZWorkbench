# W7 Codex C5/C6 隔离验证结果

状态：`C5 pass-with-composition` · `C6 pass-with-composition` ·
`acceptance/evaluation` · 不代表 Codex 原生或 ZWorkbench 产品通过

本轮针对固定 Codex Harness `0.139.0` 的真实 `app-server` 入口，验证 Provider
故障切换和事件回放 adapter。所有 Provider、workspace、`CODEX_HOME`、router
和 replay 证据均限制在 case-local 运行目录；本轮没有修改 ZWorkbench 产品代码，
也没有连接真实 Provider、凭证或外部副作用系统。

## 1. 固定边界

| 项目 | 固定值 |
|---|---|
| 候选 | Codex Harness（`openai/codex`） |
| CLI | `codex-cli 0.139.0` |
| 入口 | `codex app-server` over `stdio://` |
| Provider | case-local fake Provider；C5 由 loopback router 代理，C6 直连 loopback |
| Codex Provider 地址 | `127.0.0.1:11434` |
| workspace | 每 case 独立目录；不接触 ZWorkbench 工作区文件 |
| C5 adapter | `w7-codex-c5-c6-composition-adapter/v1` |
| C6 schema | `zworkbench-w7-codex-c56/v1` |
| durable/composition owner | 一个外部 adapter；不复制 Codex agent loop、权限模型或观测后端 |
| Provider 选择 | 只在 case-local router 内做 capability、attempt、failure、fallback/degradation 记录 |
| replay | `recorded_view`、cassette-only `simulated_replay`、default-deny `live_replay` |

C4 的 `approval-boundary-unknown` 继续向后传递。本轮的 replay default-deny 证据不
回填 Codex 原生 approval 结论。

## 2. C5：Provider 故障切换与显式降级

正式运行证据：
[`C5 summary.json`](../../evaluation/runs/w7-codex-c5-c6-20260830T165759-141575Z/summary.json)

### 2.1 结果

| 场景 | 重复 | 结果 | 观察 |
|---|---:|---:|---|
| normal-a | 5 | `5/5 pass` | `fake-a`，无 fallback |
| normal-b | 5 | `5/5 pass` | `fake-b`，无 fallback |
| timeout-once | 3 | `3/3 pass` | `fake-b → fake-a`，reason=`timeout` |
| stream-interrupt-once | 3 | `3/3 pass` | `fake-b → fake-a`，reason=`stream_interrupt` |
| structured-output-unsupported | 3 | `3/3 pass` | capability 缺失前置检测，`fake-a`，显式 degradation |
| 合计 | 19 | **`19/19 pass-with-composition`** | 语义结果均为 `fixture-ok` |

验证阈值全部满足：

- 两个正常 Provider 各 `5` 次；每个故障类型 `3` 次；
- 每个 fallback 都记录了来源、目标和 reason；
- `fake-a`/`fake-b` capability detection 完整；
- 逻辑 attempt 按 `started` 事件统计，生命周期 `started`/`succeeded`/`failed`
  记录完整；
- timeout 和半截流均只进行一次 fallback；
- structured-output 缺失在 dispatch 前显式降级；
- 所有最终 semantic result 为 `fixture-ok`，silent semantic change 为 `0`；
- 缺失证据时 evaluator 保持 `unknown/stop`。

### 2.2 C5 结论与边界

本轮证明的是：一个外部、case-local Provider router 可以围绕 Codex 的真实
app-server 入口补出可审计的 Provider 选择、故障原因、fallback、能力缺失降级
和最终语义结果关联。

本轮没有证明：

- Codex 原生提供多 Provider routing、health policy 或 fallback contract；
- loopback router 已具备生产级连接池、熔断、secret 管理、成本策略或跨进程持久化；
- fallback 后的所有模型都具有等价工具/结构化输出语义；本 fixture 只验证了
  显式 capability gate 和固定语义结果；
- C4 approval owner 已经由 Codex 原生能力解决。

因此 C5 的可采纳结论是“composition-required 且当前 seam 通过”，不是“Codex
原生多 Provider 已通过”。

## 3. C6：事件采集与回放 adapter

正式运行证据：
[`C6 summary.json`](../../evaluation/runs/w7-codex-c5-c6-20260830T165822-636804Z/summary.json)

### 3.1 结果

| replay mode | 重复 | 结果 | 约束验证 |
|---|---:|---:|---|
| `recorded_view` | 5 | `5/5 pass` | 真实 Codex JSON-RPC stream，13 个 canonical events/case |
| `simulated_replay` | 5 | `5/5 pass` | 只读 cassette/expected output；Provider、tool、network 次数均为 0 |
| `live_replay` | 5 | `5/5 pass` | 无显式批准时 default deny；Provider、tool、network、外部副作用均为 0 |
| 合计 | 15 | **`15/15 pass-with-composition`** | mode label、identity、字段完整性均通过 |

每个 capture 都具备以下 `11` 类必需 event type：

`run.started`、`environment.snapshot`、`provider.request`、
`provider.response`、`tool.call`、`policy.decision`、`tool.result`、
`state.transition`、`diff.created`、`test.output`、`run.completed`。

每个 canonical event 都具备 `event_id`、`run_id`、`type`、`logical_time`、
`source`。代表性 capture 的真实工具命令为 `/bin/zsh -lc 'printf fixture-ok'`，
退出码为 `0`；该命令只在 case-local workspace 中执行。

### 3.2 C6 结论与边界

本轮证明的是：外部 adapter 可以从真实 Codex event stream 生成带环境、Provider、
策略和工具关联的 canonical ledger，并在三个明确标注的 mode 之间保持边界：

- `recorded_view` 只查看记录，不重新执行；
- `simulated_replay` 只消费 cassette，不启动 Provider/tool/network；
- `live_replay` 在没有显式批准时安全拒绝，不把“回放”默认为真实执行。

本轮没有证明：

- Codex 原生提供版本稳定、完整的 replay/cassette contract；
- 已批准的 live replay 在真实 Provider、真实项目和真实副作用系统上安全；
- canonical ledger 已覆盖所有未来插件、MCP、Provider 或工具事件；
- 录制 schema 在 Codex 升级后仍兼容。升级、sandbox、tool surface 或 Provider
  协议变化都必须重跑 C6。

## 4. ATAM 解释

| 敏感点/风险 | 本轮证据 | 责任边界 | 残余风险 |
|---|---|---|---|
| `R-C5-01` Provider 故障导致任务中断 | timeout、半截流均显式切换且 `19/19` 通过 | 外部 router/adapter | 生产 router 的连接、熔断、secret 与成本策略未测 |
| `R-C5-02` capability 缺失造成静默语义变化 | structured-output 缺失前置降级；语义结果稳定 | capability registry + router | 真实模型间等价性仍需按能力逐项评测 |
| `R-C6-01` 回放误执行 Provider/tool | simulated 为 0 次；live replay default deny | replay adapter / approval owner | 已批准 live replay 尚未放行验证 |
| `R-C6-02` 事件缺字段导致不可回放 | 15/15 mode case identity 与必需字段完整 | canonical event ledger | Codex 升级后的 schema drift 未测 |
| `SP-C5/C6-01` 运行身份关联缺失 | provider/model/endpoint、run/event/mode identity 均记录 | composition adapter | 需要将 schema 维护纳入升级回归 |
| `SP-C2/C4-01` approval owner 不清晰 | C4 approval boundary 仍 unknown；C6 live 默认拒绝 | C2 adapter 与候选原生 surface | 不能把本轮 replay policy 当作 Codex 原生 approval 证据 |

## 5. CBAM 决策

本轮支持“一个主 Harness + 一个必要薄 composition layer”的增量路线：

- C5 只增加一个 loopback Provider router，未增加第二 agent loop；
- C6 只增加 event/cassette/replay adapter，未增加 Langfuse、Phoenix、Inspect AI
  或常驻 workflow 服务；
- Provider routing、replay policy、canonical ledger 和关联字段由一个外部 owner
  负责，避免多个系统各自产生 attempt、effect 或 replay truth；
- 该组合直接覆盖当前 W7 高风险未知，收益高于立即引入第二 Harness 或 Temporal/
  LangGraph 的常驻服务成本。

新增或必须承认的成本：

- 维护 Provider capability、attempt/fallback、event schema、cassette identity
  和 replay policy；
- Codex 版本、sandbox、工具面或 Provider 协议变化后重跑 C2–C6 回归；
- durable ledger 的备份、迁移、查询和退出责任尚未在 C7 真人运维场景验证；
- 对个人开发者/小团队而言，只有在这些薄层能保持单 owner、低常驻运维和可删除时，
  才值得继续采用。

当前不引入第二 Harness、LiteLLM、Temporal/LangGraph 或独立观测平台。若后续
需要其中任何一个，必须先用同一 C5/C6/C7 阈值证明它减少了明确的 durable、routing、
replay 或运维风险，并抵消新增部署、升级、备份、排障、迁移和退出成本。

## 6. 路线放行与下一节点

- `1-4` 可记录为 `completed`，结论为 `pass-with-composition`；
- Codex 可进入下一候选评估，但采用前提是接受外部 composition owner，而不是把
  C5/C6 能力误记为 Codex 原生能力；
- C4 的 `approval-boundary-unknown` 必须继续携带，不能被 C5/C6 的 default-deny
  replay 证据覆盖；
- 产品实现仍未开始，本轮只完成隔离验收资产和决策证据；
- 下一节点应继续评估 C7 的可观测性/真人运维边界，重点确认个人开发者或小团队
  能否承担 ledger、升级回归、故障排查和退出成本。

## 7. 资产索引

- [`run_codex_c5_c6.py`](../../evaluation/runner/run_codex_c5_c6.py)
- [`w7-codex-c5-c6 fixture`](../../evaluation/fixtures/w7-codex-c5-c6/README.md)
- [`C3/C4 findings`](./w7-codex-c3-c4-findings.md)
- [`C2 findings`](./w7-codex-c2-findings.md)
- [`W7 roadmap`](./personal-workbench-w7-roadmap.md)

