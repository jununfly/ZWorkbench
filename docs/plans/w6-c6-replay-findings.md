# W6-0.1 C6 记录查看与 simulated replay 边界证据

状态：fixture contract 首轮通过 · `acceptance/evaluation` · 不是 ZWorkbench 产品实现，也不是候选 Harness 已具备 C6 能力的证明

本报告记录 C6 的首轮确定性验证。它验证的是候选无关的 event ledger、replay cassette 和三种 replay mode 的边界合同：`recorded_view` 只读记录，`simulated_replay` 只读 cassette，`live_replay` 默认 fail-closed。候选只有在接入候选专属、固定源码/版本 adapter 后，才能把 C6 从 `unknown` 更新为候选实测结果。

## 1. 运行身份与边界

| 项目 | 值 |
|---|---|
| Run ID | `w6-0.1-c6-20260830T120732-177815Z` |
| 运行时间 | `2026-08-30T12:07:32.177815+00:00` – `2026-08-30T12:07:32.526772+00:00` |
| Fixture | [`evaluation/fixtures/w6-0.1`](../../evaluation/fixtures/w6-0.1) |
| Fixture 版本 | `W6-0.1` |
| Fixture manifest SHA-256 | `4c9d69f0faf2726b64adc949c164a4f2d76e9361c0ded8bcea27e73ca97355bd` |
| Fixture source SHA-256 | `8e3cbe1041b124caf27300a3fa9ab457e6dacd84b4b4d001b3c97b07a59c910e` |
| Replay fixture | [`c6-replay.py`](../../evaluation/fixtures/w6-0.1/c6-replay.py) |
| Replay fixture SHA-256 | `080039efcb6cba27d1183c0099868f30f228d9383e175208b00869878e350cd2` |
| Runner | [`run_c6.py`](../../evaluation/runner/run_c6.py) |
| Runner 版本 | `w6-c6-runner/v1` |
| Runner SHA-256 | `9bc17a4758b1248ecb22216cbc1813a3c370322fb8dff908454a5f11345021b3` |
| 正式证据 | [`summary.json`](../../evaluation/runs/w6-0.1-c6-20260830T120732-177815Z/summary.json) |

本轮只生成确定性的本地 ledger/cassette；没有启动 Provider，没有执行 recorded tool，没有访问外网、真实凭证、生产项目或不可逆外部系统。每个案例的 effect guard 在模式执行前后保持不变。

## 2. 覆盖范围与固定门槛

| 模式 | 输入 | 预期行为 | 重复 |
|---|---|---|---:|
| `recorded_view` | event ledger | 只读投影，不重新执行，不产生副作用 | 5 |
| `simulated_replay` | replay cassette + expected output | 只消费 cassette，返回预期语义，不访问 Provider/tool/network | 5 |
| `live_replay` | replay cassette | 未获显式审批时拒绝，留下 policy decision，副作用为 0 | 5 |

总计 `3 × 5 = 15` 个案例。每份源 ledger 都包含以下 11 类事件，并且每个事件都有 `event_id`、`run_id`、`type`、`logical_time`、`source`：

`run.started`、`environment.snapshot`、`provider.request`、`provider.response`、`tool.call`、`policy.decision`、`tool.result`、`state.transition`、`diff.created`、`test.output`、`run.completed`。

| 门槛 | 结果 |
|---|---:|
| 案例通过 | `15/15` |
| recorded view 无执行 | `5/5` |
| simulated replay 与 expected 一致 | `5/5` |
| live replay fail-closed 拒绝 | `5/5` |
| 必需事件字段完整 | `100%` |
| replay mode 标签正确 | `100%` |
| live/simulated effect guard 变化 | `0` |
| fixture contract | `pass` |

## 3. 模式语义实测

### 3.1 recorded view

`recorded_view` 读取原始 event ledger 并生成只读 projection，结果带 `replay_mode=recorded_view`、`view_only=true` 和 `execution_performed=false`。5 次运行都没有 Provider request、tool invocation 或 external call，且 semantic result 与原始 `run.completed` 记录一致。它证明“查看记录”与“重新执行”是不同操作。

### 3.2 simulated replay

`simulated_replay` 只加载版本化 `replay-cassette.json`，从 cassette 的 expected output 得到 `{"answer":"fixture-ok","task":"replay-contract-v1"}`。5 次都返回相同结果，带 `cassette_only=true`，没有启动 Provider、执行工具或访问网络。它是可重复的模拟合同，不代表 live replay 可以安全执行。

### 3.3 live replay

`live_replay` 在本轮没有批准 token，统一写入 `approval_required=true`、`approval_granted=false`、`decision=deny` 和 `live_replay_requires_explicit_approval`，状态为 `denied`、`safe_denial=true`。5 次均未执行任何 Provider/tool/external action，副作用为 0。显式批准路径不属于本轮 acceptance 范围，避免把 live side effect 带入基线。

## 4. 可复核证据结构

完整证据位于 [`evaluation/runs/w6-0.1-c6-20260830T120732-177815Z/`](../../evaluation/runs/w6-0.1-c6-20260830T120732-177815Z/)。每个案例可以独立检查：

```text
cases/<replay-mode>/repeat-<nn>/
├── run-manifest.json
├── effect-guard.json
├── process-result.json
├── recording/
│   ├── event-ledger.jsonl
│   ├── replay-cassette.json
│   ├── expected-output.json
│   └── environment-manifest.json
└── mode/
    ├── mode-result.json
    ├── mode-events.jsonl
    └── policy-decision.json      # live_replay
```

`summary.json` 保存冻结 fixture identity、runner identity、阈值、逐例 checks、聚合 metrics 和候选 unknown 账本。源 ledger 的事件字段完整性和 mode result 的执行计数都由 runner 检查，而不是只依赖文字说明。

## 5. 候选状态与边界

本批次五个候选均为 `unknown`，原因相同：没有候选专属、固定源码/版本的 C6 adapter；fixture contract 通过不能转化为候选通过。候选拥有 session JSONL、trace、replay 或 API 入口，也不能直接证明三种模式的执行边界正确。

因此本批次没有 W7 采用排序，也没有证明任何候选、Langfuse、Phoenix、Inspect AI 或 OTel 已提供完整 replay contract。仍未验证：

- 候选的原始事件是否包含重建环境、Provider、工具、权限、状态、diff 和 artifact 所需字段；
- simulated replay 是否真的 cassette-only，是否会隐式访问 Provider、网络或工具；
- live replay 的审批、凭证、网络 allowlist 和不可逆副作用是否由宿主强制；
- replay 与 C2/C3/C4/C5 的权限、幂等、恢复、fallback 和人工接管 ledger 是否能关联；
- 记录敏感源码、Prompt、凭证引用和 Provider 数据时的脱敏、存储、保留和退出成本。

## 6. ATAM/CBAM 增量观察

### ATAM

| 项目 | C6 前 | 本批次更新 | 仍未解决 |
|---|---|---|---|
| R-04：trace/session 被误认为执行 replay | C6 unknown | 三种 mode 各 5/5；recorded view 与 simulated replay 均无执行；live 5/5 deny | 候选真实 API、环境重建和副作用边界仍需固定版本 adapter |
| SP-04：replay mode 与 policy label | 只有规格，无运行 oracle | mode label 100%，live policy decision 5/5 完整 | 候选 UI/API 是否能防止模式误标和绕过仍 unknown |
| TP-04：自有 replay ledger vs 外部观测后端 | 外部后端收益未测 | 轻量 event/cassette contract 可在无常驻服务下验证 | 查询、数据集、评测和隐私收益是否值得 Langfuse/Phoenix/Inspect AI/OTel 成本仍未决 |

### CBAM

| 选项 | 本批次观察到的收益 | 增量成本/风险 | 姿态 |
|---|---|---|---|
| 一个主 Harness + 薄 replay contract | 用 15 个隔离案例验证记录投影、cassette 模拟和 live 拒绝边界 | 事件 schema、环境 snapshot、cassette 保留、候选 adapter 和脱敏责任 | 保留为待候选接入验证的主路线 |
| Langfuse/Phoenix/OTel | 可能降低 trace 存储、查询和关联自建工作 | 常驻存储、隐私、部署、许可证；不能自动提供 live replay 安全边界 | 等候选 C6/C7 数据，不因 fixture pass 自动引入 |
| Inspect AI | 可能降低 dataset/eval harness 成本 | 评测框架本身不拥有副作用 broker、环境快照或 live replay policy | 仅在 C6/C7 证明净收益后评估 |
| 第二 Harness | 本批次没有新增候选 replay 证据 | 增加 session、事件、权限和 replay 适配矩阵 | 不因记录/回放 fixture 通过而引入产品拼盘 |

本批次支持一个小团队原则：先把 replay 的“看、模拟、执行”做成互斥且可审计的模式，再决定是否接入外部观测/评测后端；trace 可查询性不能替代副作用安全和环境可重建性。

## 7. 下一步

按路线图进入 C7 个人开发者/小团队运维与生命周期成本证据；完成 C7 后再回填最终 ATAM/CBAM 和 W7 signoff 条件。候选 C6 仍需固定版本 adapter，不能由本轮 fixture contract 改写为通过。
