# W6-0.1 C5 双 Provider 故障切换与显式降级证据

状态：fixture contract 首轮通过 · `acceptance/evaluation` · 不是 ZWorkbench 产品实现，也不是候选 Harness 已具备 C5 能力的证明

本报告记录 C5 的首轮确定性验证。它验证的是一个候选无关的 loopback Provider router、能力协商和 fallback/degradation 合同；DeepSeek Harness、Pi Agent Harness、Codex Harness、OpenCode、Goose 只有在接入候选专属、固定源码/版本 adapter 后，才能把 C5 从 `unknown` 更新为候选实测结果。

## 1. 运行身份与边界

| 项目 | 值 |
|---|---|
| Run ID | `w6-0.1-c5-20260830T112617-960750Z` |
| 运行时间 | `2026-08-30T11:21:16.843212+00:00` – `2026-08-30T11:21:21.804636+00:00` |
| Fixture | [`evaluation/fixtures/w6-0.1`](../../evaluation/fixtures/w6-0.1) |
| Fixture 版本 | `W6-0.1` |
| Fixture manifest SHA-256 | `182ba60e68bf79a8f328be79f77f33562db2c0bd8302c16ec44a14b8a8fac2d0` |
| Fixture source SHA-256 | `525d6c320865d6085df57a3f619f2ef3f6f5f461a2fc7c6246817ca78dd3704c` |
| Router | [`c5-provider-router.py`](../../evaluation/fixtures/w6-0.1/c5-provider-router.py) |
| Router SHA-256 | `32057c460e527286be5a0068c29601fa7ff245d8a27b7024d3315de296b04fb6` |
| Runner | [`run_c5.py`](../../evaluation/runner/run_c5.py) |
| Runner 版本 | `w6-c5-runner/v1` |
| Runner SHA-256 | `3bdfe2c2986cd1af54cf928f177487f0386efda2a22f02f6862a0f9d06bc2463` |
| 正式证据 | [`summary.json`](../../evaluation/runs/w6-0.1-c5-20260830T112617-960750Z/summary.json) |

所有 Provider 都是每个案例单独启动的 `127.0.0.1` 假服务；没有真实 Provider、真实凭证、生产数据、外网请求、消息、Git push、部署或不可逆外部写入。timeout 使用短客户端读超时和服务端延迟，stream interrupt 发送首个 SSE event 后关闭连接，structured output 缺失通过能力探测和拒绝契约表达。

## 2. 覆盖范围与固定门槛

| 案例组 | Primary | B 注入 | 重复 | 预期结果 |
|---|---|---|---:|---|
| `normal-a` | fake-a | 无 | 5 | A 正常完成 |
| `normal-b` | fake-b | 无 | 5 | B 正常完成 |
| `timeout-once` | fake-b | `timeout_once` | 3 | 记录 timeout，切换到 A |
| `stream-interrupt-once` | fake-b | `stream_interrupt_once` | 3 | 记录半截流，切换到 A |
| `structured-output-unsupported` | fake-b | `structured_output_unsupported` | 3 | 探测能力缺口，显式切换到 A |

总计 `2 × 5 + 3 × 3 = 19` 个案例。每个案例的输入、Provider identity/model/endpoint、能力探测、request/response/error 事件、attempt history、fallback/degradation ledger 和最终语义结果都落盘。

| 门槛 | 结果 |
|---|---:|
| 案例通过 | `19/19` |
| 正常 A 用例语义一致 | `5/5` |
| 正常 B 用例语义一致 | `5/5` |
| 故障案例通过 | `9/9` |
| fallback 原因和目标记录 | `9/9`（100%） |
| structured output 能力缺失显式处理 | `3/3`（100%） |
| 静默语义变化 | `0` |
| loopback-only / 无真实 Provider | `19/19` |
| fixture contract | `pass` |

## 3. 故障切换语义

### 3.1 正常确定性

fake-a 和 fake-b 对 plain 任务均返回 `fixture-ok`，router 归一化为同一语义结果 `{"answer":"fixture-ok"}`。A、B 各 5 次的 semantic signature 均与 expected result 相符，没有 fallback，也没有无记录的 Provider 切换。

### 3.2 timeout 与流中断

`timeout_once` 的 B 首次请求在 response header 前超时，attempt history 将失败原因记录为 `timeout`；`stream_interrupt_once` 的 B 请求收到首个 SSE event 后提前结束，router 因缺少 `[DONE]`/`stop` 终止标记记录为 `stream_interrupt`。两类故障均采用有界策略：不在 B 上静默重试，写入 `provider.fallback`，显式转到 fake-a，再以同一 expected semantic result 完成。

### 3.3 structured output 能力缺失

B 的能力探测只报告 `tool_calls` 和 `streaming`，不报告 `structured_output`。对于要求 JSON schema 的任务，router 在发起 B 请求前记录 `capability_missing:structured_output`，写入 degradation/fallback ledger，再探测 A 并用 structured response 完成。该路径证明“能力不足可被观察并显式降级”，不证明所有 Provider 都能保持结构化输出的 schema 兼容；真实 Provider 的 schema、工具调用和参数语义仍需后续候选 adapter 验证。

## 4. 可复核证据结构

完整证据位于 [`evaluation/runs/w6-0.1-c5-20260830T112617-960750Z/`](../../evaluation/runs/w6-0.1-c5-20260830T112617-960750Z/)。每个案例可以独立检查：

```text
cases/<case-type>/repeat-<nn>/
├── case-manifest.json
├── task.json
├── router-process-result.json
├── result.json
├── provider-events.jsonl
├── capability-detection.jsonl
├── attempt-history.jsonl
├── fallback-ledger.jsonl       # 发生 fallback 的案例
├── degradation-ledger.jsonl    # 能力降级案例
└── provider-runtime/
    ├── fake-a.provider.log
    ├── fake-a.requests.jsonl
    ├── fake-b.provider.log
    └── fake-b.requests.jsonl
```

`summary.json` 保存 fixture manifest/source hash、router hash、冻结阈值、逐例 checks、聚合 metrics 和候选 unknown 账本。Provider request event 保留完整的无敏感输入 body 及 hash；每条 attempt 和 capability record 都含 provider identity、model 和 endpoint。

## 5. 候选状态与边界

本批次五个候选均为 `unknown`，原因相同：没有候选专属、固定源码/版本的 C5 adapter；fixture contract 通过不能转化为候选通过。C1 的“能请求两个 fake Provider”也不能替代 C5 的故障、能力协商和语义 oracle。

因此本批次没有 W7 采用排序，也没有证明任一候选、LiteLLM 或其他 Provider 组合件已经满足生产级 fallback。仍未验证：

- 候选自己的 Provider 配置、stream parser、tool-call/structured-output schema 适配是否可观察且可回退；
- Provider/model/endpoint 变化后的凭证、限额、成本和版本漂移治理；
- fallback 后跨 Run 状态、幂等、副作用和人工接管是否与 C3/C4 合同一致；
- LiteLLM 等网关是否真的降低总适配成本，而不是增加一个不可解释的故障面；
- 真实 Provider 的服务条款、隐私、数据驻留和网络边界。

## 6. ATAM/CBAM 增量观察

### ATAM

| 项目 | C5 前 | 本批次更新 | 仍未解决 |
|---|---|---|---|
| R-05：Provider 故障被误报为成功 | C1 仅证明基本请求，fallback unknown | 19/19 案例保留 attempt、failure reason、fallback target；静默语义变化 0 | 候选真实事件/API 与多 Provider schema 仍需固定版本 adapter |
| SP-03：能力协商入口 | 能力缺失未实测 | B 的 `structured_output` 缺失在请求前被记录并显式切换 | 真实 Provider 能力声明可能不完整或漂移，需版本化 capability contract |
| TP-03：统一 Provider 层 vs 最低共同能力 | 是否引入 LiteLLM 未决 | 候选无关薄 router 已足以验证 fallback ledger 和语义 oracle | 是否由网关还是 ZWorkbench 拥有降级、成本和 schema 责任仍未决 |

### CBAM

| 选项 | 本批次观察到的收益 | 增量成本/风险 | 姿态 |
|---|---|---|---|
| 一个主 Harness + 薄 Provider adapter | 用 19 个隔离案例验证双 Provider metadata、能力缺失和有界 fallback 合同 | 每个候选仍需 endpoint/config/schema/stream adapter；需要保留 fallback ledger | 保留为待候选接入验证的主路线 |
| LiteLLM | 本轮只证明“Provider 路由问题可被单独建模”，没有证明网关收益 | 网关、凭证、转译、限流、许可证和新增故障面 | 保持候选，不因 C5 fixture pass 自动引入 |
| 第二个 Harness | 本批次没有新增候选 C5 证据 | 会扩大 Provider、权限、状态、事件和升级矩阵 | 不因双 Provider fixture 通过而引入产品拼盘 |

本批次支持一个明确的小团队原则：先拥有可解释的 Provider contract 和 fallback/degradation ledger，再决定是否引入网关；不要把“支持多个 Provider”简化成一个兼容 API。C5 只收窄了 fixture/protocol 风险，不能替代 C7 运维成本或 W7 采用决策。

## 7. 下一步

按路线图进入 C6 记录查看与 simulated replay 边界证据；随后再以固定版本候选 adapter 补做候选 C3–C6。候选状态在出现真实 adapter、完整版本绑定和可复核失败/通过样本前继续保持 `unknown`。
