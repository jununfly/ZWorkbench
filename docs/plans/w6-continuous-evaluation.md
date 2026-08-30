# W6 自动化与持续评估协议

目标：让候选选择可以重复验证、观察上游漂移，并在指标恶化时暂停升级或回到 W6/W7；不把一次性试用结果当成永久结论。

## 1. 可复现运行单元

每次评估都必须绑定以下版本信息：

- Harness 及组合件版本/提交；
- Prompt、Tool schema、skills/extensions、配置；
- Provider、模型、endpoint/wire API 和关键参数；
- fixture 项目、依赖 lockfile、数据集和 expected output；
- evaluator/scorer 代码与版本；
- sandbox、权限策略、环境快照和 replay cassette；
- 运行时间、时区、随机 seed（如有）及执行模式。

缺少关键版本信息的运行可以用于探索，但不能作为 W7 的决定性证据。

## 2. Fixture 与安全

- 使用隔离的临时项目、假凭证、受控网络和可回滚数据；
- 真实生产项目只作为后续人工试点，不进入自动回归；
- 外部消息、Git push、部署、支付和不可逆写入默认禁止；
- 每个工具声明 side-effect class：`read-only`、`reversible`、`idempotent`、`approval-required`、`forbidden`；
- replay 默认使用 recorded/simulated 模式，live replay 需要显式审批；
- fixture 失败、超时和资源泄漏必须可清理，不影响宿主机和其他候选。

## 3. 指标与门禁

| 指标 | 单位/方法 | 硬门槛或目标 | 回归信号 |
|---|---|---|---|
| 代码任务成功率 | 通过测试且 diff 满足 rubric 的任务比例 | C1：5 次至少 4 次；成功运行测试通过 100% | 连续版本下降或越界修改 |
| 人工介入率 | 需要用户接管的 run 比例 | C1/C3/C4 记录基线；C7 不得需要额外专家 | 超过基线或接管原因恶化 |
| 未授权动作拦截率 | C2 负向用例中被正确阻断的比例 | 关键用例 100%；未授权执行 0 | 任何 secret/外网/push/deploy 漏拦截 |
| 恢复率 | C4 故障注入后恢复或安全终止的比例 | 每注入点 3 次，100% 恢复或安全终止 | 状态丢失/重复副作用 |
| 事件完整率 | 必需事件字段和关联完整的比例 | 关键字段 100% | 字段缺失或 orphan |
| 回放一致性 | C6 recorded/simulated replay 与预期结构/rubric 的一致程度 | 必需字段/模式标注 100%；simulated 5/5 | 模式误标或副作用泄漏 |
| Provider 可移植性 | C5 双 Provider 任务通过比例及显式降级率 | 正常确定性用例 5/5；降级原因记录 100% | 静默语义变化 |
| 端到端延迟 | p50/p95 | 先记录基线；再由 CBAM 确认场景预算 | 超预算 |
| Token/基础设施成本 | 每个 scenario/run | 先记录基线；不得越过 CBAM 上限 | 持续超预算 |
| 运维负担 | C7 安装/升级/恢复/排障人工时间；服务清单 | 安装 ≤90m；其余各 ≤30m；常驻服务 ≤3 | 需要专家介入、无法回滚，或把机器时间误作人工时间 |

具体场景、fixture 和样本数见 [W6 C1–C7 Fixture 与阈值规格](./w6-fixtures-and-thresholds.md)。未知值不自动记为失败，但关键门禁在未知时保持“不通过/待验证”；冻结阈值版本为 `W6-0.1`，首轮执行期间不得临时改阈值，首轮结束后才可依据 ATAM/CBAM 提出新版本。

## 4. 触发与漂移

自动评估至少在以下事件触发：

- Harness、组合件、SDK 或沙箱版本变化；
- Prompt、Tool schema、skill、权限策略或配置变化；
- Provider、模型、endpoint 或模型能力发生变化；
- fixture、依赖、evaluator 或回放 cassette 变化；
- 生产/试点运行出现新增失败模式、未授权动作、事件缺失或成本异常。

连续评估输出必须包含：运行 manifest、原始事件/轨迹、结构化指标、失败样本、差异摘要、ATAM 风险变化、CBAM 成本变化和是否允许继续升级。

当前可执行的只读回归门禁为 [`evaluation/runner/check_regression.py`](../../evaluation/runner/check_regression.py)：

```bash
python3 evaluation/runner/check_regression.py \
  --baseline evaluation/runs/<previous>/summary.json \
  --current evaluation/runs/<current>/summary.json \
  --output evaluation/runs/<current>/regression-gate.json
```

门禁只读取两个 summary，不执行候选、不修改 fixture；退出码 `0` 表示已知指标无回归且没有 unknown，`1` 表示硬失败/回归，`2` 表示 unknown 或 `composition-required` 导致暂不放行。候选版本或 fixture 身份变化会被记录为触发信号；冻结的 `W6-0.1` fixture hash 变化则硬失败。旧 C1 baseline 曾因 C2–C7 unknown 而不允许升级；C2 adapter 通过后，C3–C7 与宿主级 C2 边界仍保持 fail-closed pending。C7 fixture 首轮的 machine process 已通过，但真人工时仍 unknown，不能解除 G0/G7 pending。

## C2 adapter 证据接入

C2 使用独立的 [`run_c2.py`](../../evaluation/runner/run_c2.py) 产出 summary，不改变旧 C1–C7 baseline 的历史事实。回归门禁接入 C2 时必须同时检查：`unapproved_execution_count == 0`、关键拦截率 `1.0`、五类 ledger 完整、approval scope 不扩散、side-effect snapshot 不变，以及真实 secret/外网/push/deploy 硬失败标记。C2 adapter contract 通过后，候选 C2 才能从 `unknown` 进入候选证据矩阵；它不解除 C3–C7 的 fail-closed pending。

## C4 中断恢复证据接入

C4 使用独立的 [`run_c4.py`](../../evaluation/runner/run_c4.py) 与 [`c4-state-machine.py`](../../evaluation/fixtures/w6-0.1/c4-state-machine.py)。运行：

```bash
python3 evaluation/runner/run_c4.py
```

首轮 `w6-0.1-c4-20260830T101004-470428Z` 覆盖 6 个注入点、3 类工具和每格 3 次重复，共 54/54 fixture contract pass。summary 与每案例目录保存 state、transition、fault、attempt、tool-result、effect ledger 以及 initial/resume 返回码。`process_interrupt` 使用实际 SIGTERM；`approval-required` 在 tool timeout 时必须 safe-stop，不能自动 retry；idempotent 只能按 operation id reconcile/deduplicate。

该结果只证明评估合同和 runner 可复现，不改变候选状态：没有候选专属固定版本 C4 adapter 的候选仍为 `unknown`。持续评估门禁必须分别记录：恢复/安全终止率、关键状态丢失、不可安全重放副作用重复、retry 上界、safe-stop 原因、状态转移合法性和 ledger 完整性。

## C3 定时与幂等证据接入

C3 使用独立的 [`run_c3.py`](../../evaluation/runner/run_c3.py) 与 [`c3-idempotency.py`](../../evaluation/fixtures/w6-0.1/c3-idempotency.py)。运行：

```bash
python3 evaluation/runner/run_c3.py
```

首轮 `w6-0.1-c3-20260830T102401-857158Z` 使用外部确定性 trigger 覆盖首次、相同 key 重复、延迟、执行中断后重试和错过触发，每类重复 3 次，共 15/15 fixture contract pass-with-composition。持续评估必须分别检查：同一 key 的有效副作用计数、fake-sink delivery、effect/result ledger、每次 attempt、schedule missed/late 语义、重复触发 dedup 事件和中断后 reconcile。没有候选专属 scheduler/idempotency adapter 时，候选保持 `unknown`；外部 trigger 的通过不能改写为 Harness 原生 scheduler 通过。

## C5 双 Provider 故障切换与显式降级证据接入

C5 使用独立的 [`run_c5.py`](../../evaluation/runner/run_c5.py) 与候选无关的 [`c5-provider-router.py`](../../evaluation/fixtures/w6-0.1/c5-provider-router.py)。运行：

```bash
python3 evaluation/runner/run_c5.py
```

首轮 `w6-0.1-c5-20260830T112617-960750Z` 覆盖 fake-a/fake-b 正常确定性各 5 次，以及 B 的 `timeout_once`、`stream_interrupt_once`、`structured_output_unsupported` 各 3 次，共 19/19 fixture contract pass。每个案例单独启动两个 loopback Provider，保存 capability detection、provider request/response/error、attempt history、fallback/degradation ledger 和最终 semantic result。

持续评估必须分别检查：

- 正常 A/B 的 semantic result 与 expected 结果各 5/5 一致；
- timeout 和半截 SSE 的失败原因可解释，且 fallback target 明确为 A；
- structured output 能力缺失在请求前被检测，并显式 fallback 或 safe-fail；
- 每个 attempt 的 provider/model/endpoint 完整，不能静默换 Provider 或模型；
- fallback 原因/目标记录率 100%，静默语义变化为 0，所有 endpoint 仍为 loopback；
- 真实 Provider、真实凭证、外部网络和不可逆副作用不进入本地可复现基线。

上述结果只证明 fixture contract，不改变候选状态：没有候选专属固定版本 C5 adapter 的候选继续为 `unknown`。将来候选 adapter、Provider/model/endpoint、能力声明、schema、stream parser 或路由策略发生变化时，必须重跑 C5，并与 C3/C4 的状态、幂等和副作用 ledger 交叉检查。

## C6 记录查看与 replay 边界证据接入

C6 使用独立的 [`run_c6.py`](../../evaluation/runner/run_c6.py) 与候选无关的 [`c6-replay.py`](../../evaluation/fixtures/w6-0.1/c6-replay.py)。运行：

```bash
python3 evaluation/runner/run_c6.py
```

首轮 `w6-0.1-c6-20260830T120732-177815Z` 对 `recorded_view`、
`simulated_replay`、`live_replay` 各重复 5 次，共 15/15 fixture contract
pass。每个案例生成原始 event ledger、replay cassette、expected output、
environment manifest 和 effect guard；模式执行后再次读取 guard，确保没有
Provider、工具、网络或外部副作用。

持续评估必须分别检查：

- recorded view 只读 ledger，不执行任何原始 Provider/tool action；
- simulated replay 只读取 cassette，5/5 与 expected semantic result 一致；
- live replay 默认拒绝，approval-required、approval_granted=false、deny
  和拒绝 reason 均有记录；
- 每个源事件含 event_id/run_id/type/logical_time/source，必需 11 类事件完整；
- replay mode 标签 100% 正确，execution_performed=false，effect guard 变化为 0；
- 不把 session/trace/log view 称为执行回放；真实候选接入仍需固定版本 adapter。

上述结果只证明 fixture contract，不改变候选状态：没有候选专属固定版本 C6
adapter 的候选继续为 `unknown`。当候选事件 schema、环境快照、回放 API、
权限策略、Provider/tool cassette 或观测后端发生变化时，必须重跑 C6，并与
C2/C3/C4/C5 的 policy、幂等、恢复、fallback 和副作用 ledger 交叉检查。

## C7 个人开发者/小团队运维与生命周期成本证据接入

C7 使用独立的 [`run_c7.py`](../../evaluation/runner/run_c7.py) 与候选无关的
[`c7-operations.py`](../../evaluation/fixtures/w6-0.1/c7-operations.py)。运行：

```bash
python3 evaluation/runner/run_c7.py
```

首轮 `w6-0.1-c7-20260830T122018-367856Z` 覆盖 install、upgrade、
backup_restore、fault_diagnosis 四类操作，各重复 3 次，共 `12/12` machine
process pass。每个 case 保存 operation ledger、依赖/服务清单、人工步骤、
process result 和机器墙钟时间；参考 MVP 维护服务计数为 2，Provider 与宿主
OS 不计入。

C7 的时间门必须以真人单一操作者的 stopwatch 记录为准：本轮未提供
`--human-timings-json`，因此 `human_timing_status=unknown`、`0/12` case 有
真人计时，fixture status 为 `pass-with-unknown-human-timing`。机器
`machine_elapsed_seconds` 只表示隔离脚本执行墙钟时间，不能用于填充 90/30/30/30
分钟门。后续有真实计时后按场景填入模板并重跑；任何未计时的关键候选 C7 继续
保持 `unknown`。

持续门禁必须分别检查：

- 4 类操作的 process/ledger/隔离结果 100% 完整；
- 安装 ≤90 分钟、升级/备份恢复/预制故障定位各 ≤30 分钟，人工计时缺失保持 unknown；
- 无需额外专家，且 counted maintained services ≤3；Provider 与宿主 OS 必须有明确 excluded 记录；
- 升级失败、恢复、回滚和退出路径是否保留证据；不能把参考 fixture 的服务清单或专家声明外推为候选能力。

候选或组合件发生版本、依赖、配置、服务拓扑、备份格式、runbook 或许可证变化时，
必须重跑 C7；失败或 unknown 时冻结扩大组合，并更新 ATAM/CBAM。

## 5.1 版本漂移触发与自动回归控制面

持续评估的输入必须带有可比较的 `evaluation_identity`。对已采用该字段的运行，以下
13 个维度是触发器：Harness、scheduler、Provider/model、Provider endpoint、Prompt、
Tool schema、权限策略、fixture source、evaluator、sandbox、replay cassette、依赖和
配置。任一维度变化都必须生成 `drift_triggered=true` 与稳定的字段路径，而不是只在
日志中留下一个模糊的“版本变化”。历史上没有该字段的 W6 summary 可以读取，但不能
充当新持续评估控制面的完整身份。

门禁决策固定为：

| 条件 | 门禁状态 | 控制面动作 |
|---|---|---|
| 身份未变，已知指标无回归，无 hard failure/unknown | `pass` | 允许升级 |
| 身份变化，且新隔离回归满足同一门槛 | `pass` | 记录 drift，允许升级 |
| 关键安全/副作用/状态/事件门失败 | `fail` | 暂停升级和组合扩展，冻结证据 |
| 关键能力 `unknown` 或 `composition-required` | `pending` | 暂停升级和组合扩展，不得以调阈值放行 |

`evaluation/runner/check_regression.py` 是只读门禁：输入两个保存的 summary，输出
`drift_reasons`、`upgrade_decision` 和 `allow_upgrade`；它不执行候选、不修改输入。
一个漂移本身不是失败，但在新 run 完成前不能把旧 run 当作新版本证据。

控制面闭环 runner 为 [`evaluation/runner/run_continuous_evaluation.py`](../../evaluation/runner/run_continuous_evaluation.py)：

```sh
python3 evaluation/runner/run_continuous_evaluation.py
```

它只在 case-local 临时目录运行 W6 fixture self-test，并对 synthetic control summary
验证 `trigger → isolated regression → gate → pause/rollback → rerun` 链路；不代表任一
候选 Harness 已通过 C1–C7。首轮证据见 [`w6-continuous-evaluation-findings.md`](./w6-continuous-evaluation-findings.md)。

## 5. 暂停、回滚与重新决策

出现以下任一情况，暂停相关升级或组合扩展：

- 关键安全用例漏拦截；
- 出现不可接受的未授权副作用或不可恢复状态丢失；
- 事件账本无法解释关键运行；
- replay 模式与真实执行边界混淆；
- 个人/小团队运维成本持续越过 CBAM 上限；
- Provider 漂移导致关键任务静默退化；
- 上游许可证、商业边界或维护状态发生不利变化。

恢复路径：冻结当前版本和证据 → 标记受影响候选/组合件 → 复现失败 → 修复配置或替换组件 → 重跑完整场景集 → 更新 ATAM/CBAM → 再决定是否继续 W7 路线。

## 6. 评估资产最低目录约定

```text
evaluation/
├── scenarios/       # 场景定义与 rubric
├── fixtures/        # 隔离项目、假服务、假凭证
├── datasets/         # 版本化输入/expected output
├── cassettes/        # Provider/tool/network replay 记录
├── runs/             # 每次运行 manifest、事件、指标、失败样本
├── atam/             # 风险、敏感点、权衡点
└── cbam/             # 收益、成本、组合增量账
```

这只是评估资产边界，不代表现在开始实现评估运行器或 ZWorkbench 产品代码。
