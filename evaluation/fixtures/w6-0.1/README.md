# W6-0.1 隔离评估 Fixture

这是候选 Harness 首轮比较使用的无真实副作用 fixture。它只允许访问本地临时目录和 loopback 假服务，不使用真实凭证、生产项目、外部消息或不可逆部署。

## 组成

- `code-project/`：带一个明确缺陷、现有测试和项目说明的小型 Python 项目；
- `fake-provider-a.json` / `fake-provider-b.json`：确定性 Provider 契约和故障注入说明；
- `fake-provider.py`：仅监听 loopback 的 OpenAI-compatible 最小假服务；
- `c5-provider-router.py`：候选无关的双 Provider 路由、能力探测、显式 fallback/degradation 与语义 oracle；
- `c6-replay.py`：候选无关的 recorded view、cassette-only simulated replay 和 fail-closed live replay 边界 fixture；
- `c7-operations.py`：候选无关的安装、升级、备份恢复和预制故障定位运维演练；只操作 case-local 文件，不安装依赖、不启动常驻服务、不访问网络；
- `fake-sink.py`：只写调用者指定的临时日志文件；
- `c2-adapter.py`：C2 acceptance-only fail-closed adapter；默认拒绝五类危险动作，仅允许带精确一次性 token 的 loopback sink；
- `policy/policy.json`：五类危险动作的评估策略；
- `manifests/fixture-manifest.json`：fixture 版本与 hash 入口。

`dummy-remote.git`、假凭证和运行时快照由 runner 在临时目录中生成，不提交到 fixture 源目录。

运行统一 fixture self-test：

```sh
python3 evaluation/runner/run_baseline.py --self-test
```

候选 preflight 只执行 `--version`/`--help`，不启动 Agent、不请求模型、不访问网络；完整 C1–C7 只有在候选有明确的本地 fake Provider 和安全 adapter 后才会被标记为实测。

运行 C2 adapter 契约与已接入候选：

```sh
python3 evaluation/runner/run_c2.py --repeats 3 --deepseek-entry /path/to/deepseek/apps/cli/lib/bin.js
```

C2 runner 会在临时目录生成假凭证、dummy Git remote、loopback sink 和 deploy stub，输出 policy、approval、tool-result、event ledger 与 side-effect snapshot。候选执行使用自身的 workspace sandbox；`--outer-sandbox` 仅用于 macOS `sandbox-exec` 嵌套兼容性探测，不是默认候选路径。

运行 C4 隔离状态机首轮验证：

```sh
python3 evaluation/runner/run_c4.py
```

C4 runner 在每个案例目录保存 durable `state`、状态转移、故障注入、attempt、tool-result 和 effect ledger。它覆盖工具执行前/后提交前/提交后下一步前、Provider timeout、tool timeout 和真实进程 `SIGTERM`；每个注入点覆盖 `read-only`、`idempotent`、`approval-required` 三类工具并重复 3 次。fixture contract 通过不代表任何候选已通过 C4；没有候选专属 C4 adapter 的候选继续标记为 `unknown`。

运行 C3 定时触发与幂等首轮验证：

```sh
python3 evaluation/runner/run_c3.py
```

C3 使用外部确定性触发器驱动 `daily-summary-v1`，覆盖首次触发、相同 key 重复、延迟触发、执行中断后重试和错过触发；每种场景重复 3 次。触发、attempt、结果和副作用都写入 case ledger，loopback fake-sink 只应收到同一 `idempotency_key` 的一个版本化结果。该结果是 `pass-with-composition` 的 fixture 合同；候选没有固定版本 C3 adapter 时仍为 `unknown`。

运行 C5 双 Provider 故障切换与显式降级首轮验证：

```sh
python3 evaluation/runner/run_c5.py
```

C5 每个案例都会单独启动 `fake-provider-a` 与 `fake-provider-b`，只使用
loopback endpoint；正常 A/B 各重复 5 次，`timeout_once`、
`stream_interrupt_once` 和 `structured_output_unsupported` 各重复 3 次。
每个案例保存 task/case manifest、Provider request/response/error 事件、能力
探测、attempt history、fallback/degradation ledger、最终语义结果和 fake
Provider 日志。structured output 缺失时先记录 B 的能力缺口，再显式 fallback
到 A；timeout 和半截 SSE 也必须带有可解释原因和目标 Provider。fixture
contract 通过不代表任何候选已通过 C5；没有候选专属固定版本 C5 adapter 的
候选继续标记为 `unknown`。

运行 C6 记录查看与 replay 边界首轮验证：

```sh
python3 evaluation/runner/run_c6.py
```

C6 为每个 replay 模式重复 5 次。`recorded_view` 只读取 event ledger，
`simulated_replay` 只读取 replay cassette，二者都不访问 Provider、工具或
网络；`live_replay` 没有显式批准时直接拒绝，并记录 policy decision。每个
案例保存 run/environment manifest、原始 event ledger、cassette、模式结果、
模式事件、policy（live）和 effect guard。fixture contract 通过不代表任何
候选已通过 C6；没有候选专属固定版本 C6 adapter 的候选继续标记为
`unknown`。

运行 C7 个人开发者/小团队生命周期成本首轮验证：

```sh
python3 evaluation/runner/run_c7.py
```

C7 对安装、常规升级、备份恢复和预制故障定位各重复 3 次。每个案例分别
保存机器可测墙钟时间、人工操作步骤、operation ledger、服务清单、依赖清单
和 `human-timing-template.json`。首轮不带 `--human-timings-json`，所以机器
流程可以通过，但人工时间门保持 `unknown`；runner 的 subprocess 时间绝不
被解释成真人运维时间。若有真实单人秒表记录，可按场景提供：

```json
{"install": 42, "upgrade": 8, "backup_restore": 10, "fault_diagnosis": 12}
```

再使用 `--human-timings-json <path>` 重跑。固定门槛是安装 ≤90 分钟，其余
三类各 ≤30 分钟；参考 MVP 维护常驻服务 ≤3 个，Provider 与宿主 OS 不计入，
且不需要额外专家。该 fixture contract 通过不代表候选 C7 通过；候选仍需
固定版本 runbook、真实操作者记录、升级/回滚与退出证据。

运行 W6 持续评估控制面（不调用候选）：

```sh
python3 evaluation/runner/run_continuous_evaluation.py
```

该 runner 只运行本 fixture 的 self-test，并用 synthetic control summary 验证
版本漂移触发、隔离回归、fail-closed pause、rollback 和 rerun 证据链；它不产生
候选 C2–C7 通过结论。
