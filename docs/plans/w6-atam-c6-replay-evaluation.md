# W6 ATAM-C6：事件记录、回放与评测边界

状态：`completed` · `acceptance/evaluation` · 不是 ZWorkbench 产品实现，也不是候选 Harness 或观测/评测后端已具备 C6 能力的证明

本文件收口路线图节点 `1-2-4` 的 ATAM 场景定义，并解释 C6 首轮 fixture
contract 对架构决策的影响。C6 的核心不是“有没有 trace 或 session 文件”，而是能否
严格区分记录查看、无副作用模拟回放和真实执行回放，并为评测、调试与排障保留可
关联的环境、Provider、工具、策略、状态和 artifact 证据。

## 1. ATAM 质量属性场景

| 要素 | 冻结定义 |
|---|---|
| 刺激 | 对一次包含 Provider、工具、策略、状态、diff 和测试结果的运行，分别请求 recorded view、simulated replay 和 live replay |
| 环境 | 候选无关的 W6-0.1 隔离 fixture；版本化 event ledger、replay cassette、expected output、environment manifest 和 effect guard；无真实 Provider、凭证、生产项目、外网和不可逆副作用 |
| 响应 | `recorded_view` 只读投影；`simulated_replay` 只消费 cassette；`live_replay` 无显式批准时生成 deny policy 并安全拒绝；三个模式必须互斥且带明确标签 |
| 度量 | 必需事件字段完整率 `100%`；必需事件类型完整率 `100%`；模式标签正确率 `100%`；simulated replay `5/5` 与 expected 一致；live replay 副作用 `0`；recorded view 无执行 `5/5` |
| 证据 | run/environment manifest、event ledger、replay cassette、expected output、mode ledger、policy decision、effect guard、逐例 oracle 和候选 unknown ledger |

## 2. 三种模式的边界

| 模式 | 允许读取 | 禁止行为 | 成功语义 |
|---|---|---|---|
| `recorded_view` | 原始 event ledger | Provider、工具、网络和外部调用 | 生成只读投影，`view_only=true`，`execution_performed=false` |
| `simulated_replay` | 版本化 replay cassette 与 expected output | Provider、工具、网络和外部副作用 | 只返回 cassette 预期语义，`cassette_only=true` |
| `live_replay` | replay cassette 和策略上下文 | 未经批准的真实重执行 | 默认 `approval_required=true`、`decision=deny`、`safe_denial=true` |

`recorded_view` 是可审计的查看，不是重新执行；`simulated_replay` 是确定性评测和调试
输入，不是 live replay；`live_replay` 是高风险动作，不能因为 cassette 存在或模拟
结果一致就自动放行。

## 3. 首轮 fixture 结果

证据：[W6-0.1 C6 记录查看与 simulated replay 边界](./w6-c6-replay-findings.md)。正式
Run：`w6-0.1-c6-20260830T120732-177815Z`。

| 模式 | 重复 | 结果 | 关键观察 |
|---|---:|---:|---|
| `recorded_view` | 5 | **5/5 pass** | 只读 ledger projection；Provider/tool/network 调用均为 0 |
| `simulated_replay` | 5 | **5/5 pass** | 只消费 cassette；semantic result 与 expected 一致；执行计数为 0 |
| `live_replay` | 5 | **5/5 pass** | 无批准统一 deny；approval/policy ledger 完整；副作用为 0 |
| 合计 | 15 | **15/15 pass** | 三种模式均有标签，effect guard 未变化 |

首轮固定身份：fixture manifest SHA-256 为
`4c9d69f0faf2726b64adc949c164a4f2d76e9361c0ded8bcea27e73ca97355bd`，fixture source
SHA-256 为 `8e3cbe1041b124caf27300a3fa9ab457e6dacd84b4b4d001b3c97b07a59c910e`，replay
fixture SHA-256 为 `080039efcb6cba27d1183c0099868f30f228d9383e175208b00869878e350cd2`，
runner `w6-c6-runner/v1` 的 SHA-256 为
`9bc17a4758b1248ecb22216cbc1813a3c370322fb8dff908454a5f11345021b3`。

每个源 ledger 含 11 类必需事件：`run.started`、`environment.snapshot`、
`provider.request`、`provider.response`、`tool.call`、`policy.decision`、
`tool.result`、`state.transition`、`diff.created`、`test.output`、`run.completed`。
每个事件均含 `event_id`、`run_id`、`type`、`logical_time`、`source`。

## 4. 可复核证据结构

正式证据位于
[`evaluation/runs/w6-0.1-c6-20260830T120732-177815Z/`](../../evaluation/runs/w6-0.1-c6-20260830T120732-177815Z/)。
每个案例可以独立复核：

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

`summary.json` 同时保存 fixture/runner identity、冻结阈值、逐例 checks、聚合 metrics
和候选 unknown ledger。`effect-guard` 在每个模式执行前后保持一致，不能只依赖
runner 的退出码或文字日志来断言“没有执行”。

## 5. 架构事实与责任边界

| 能力 | C6 当前事实 | W7 必须确认的 owner |
|---|---|---|
| canonical event ledger | 本轮由候选无关 fixture 生成并校验 11 类事件及必需字段 | ZWorkbench 的跨候选证据边界，或明确的主 Harness adapter；不能只依赖观测后端私有 trace |
| replay cassette 与 environment snapshot | 本轮作为版本化本地 artifact 保存 | replay contract owner；必须和 Provider、工具、策略、状态、diff/test、依赖及 artifact identity 关联 |
| recorded view | 本轮只做 ledger 投影，不执行 | 观测/调试视图可以委托后端，但模式标签和只读保证需由自有 contract 约束 |
| simulated replay | 本轮只消费 cassette，不访问 Provider/tool/network | 评测/调试编排 owner；必须保持 cassette-only，不能因 SDK 或插件默认行为访问外部系统 |
| live replay policy | 本轮无批准即 deny | C2 安全/审批 owner；宿主或 broker 必须能阻断工具、凭证、网络和不可逆副作用 |
| 副作用与执行计数 | 本轮由 effect guard 观察为 0 | 与 C2 approval、C3 idempotency、C4 reconcile 和 C5 fallback ledger 串联 |
| 脱敏、保留、退出 | 本轮仅使用 fixture 假数据，未验证生产隐私 | 产品必须明确源码、Prompt、Provider 请求/响应、凭证引用和 cassette 的脱敏/TTL/删除/导出策略 |

## 6. ATAM 风险、敏感点与权衡点

| ID | 类型 | 判断 | 触发条件 | 处理与证据 |
|---|---|---|---|---|
| R-C6-01 | Risk | trace/session/log view 被误认为执行 replay | 只有查看 API 或 session reopen，没有执行计数和模式协议 | 三种模式互斥；每次运行写 mode ledger 和 execution counters；模式误标即 hard failure |
| R-C6-02 | Risk | simulated replay 隐式访问 Provider、工具或网络 | replay SDK、插件、环境变量或默认 client 未隔离 | cassette-only runner + effect guard；Provider/tool/network 任一访问即失败 |
| R-C6-03 | Risk | live replay 绕过审批造成真实副作用 | cassette 被当作授权，或 approval policy 只在 UI 层存在 | 默认 deny；记录 approval/policy decision；接入候选时验证宿主强制边界 |
| R-C6-04 | Risk | cassette/环境不完整导致评测结果不可复现或归因错误 | 缺 Provider/model、tool schema、策略、状态、依赖、diff/test 或 artifact identity | 必需事件与 manifest 完整率 100%；缺字段保持 `unknown/pending`，不补猜测 |
| R-C6-05 | Risk | 敏感数据进入长期 replay 存储且无法退出 | 保存原始 Prompt、源码、模型输入输出和凭证引用 | 候选级 C6/C7 增加脱敏、访问、TTL、导出/删除和恢复演练；本轮不外推 |
| SP-C6-01 | Sensitivity point | replay mode、cassette hash、environment hash 和执行计数 | replay fixture、依赖、策略或环境变化 | 纳入 `evaluation_identity`；漂移触发隔离回归并 pause |
| SP-C6-02 | Sensitivity point | 事件类型、字段和跨 Run 关联 ID | Harness/Provider/tool/event adapter 升级 | 固定 schema；关键字段缺失必须 fail-closed |
| SP-C6-03 | Sensitivity point | effect guard、approval policy 和 sandbox/broker | live replay 或恢复/重试路径变化 | 与 C2–C5 ledger 交叉验证，不以模拟结果替代真实权限边界 |
| TP-C6-01 | Trade-off point | 自有 canonical ledger/replay contract vs 外部观测后端 | 需要查询、可视化、dataset、实验和评分能力 | 自有 contract 先守住模式、副作用和 artifact lock；后端只在净收益超过存储/隐私/部署/退出成本时接入 |
| TP-C6-02 | Trade-off point | 记录完整性 vs 源码/Provider 隐私 | 为调试保留原始请求与工具参数 | 按字段脱敏和引用化；敏感信息缺失不能降低事件审计要求，需显式标记 redacted |
| TP-C6-03 | Trade-off point | live replay 便利性 vs 默认安全拒绝 | 需要复现真实外部问题 | 默认 `deny`；只有精确 scope、一次性 approval、隔离环境和副作用 oracle 齐全时才重新打开 |
| TP-C6-04 | Trade-off point | 多 Harness 的 replay 交叉覆盖 vs 多套事件/会话协议 | 第二 Harness 提供不同 session/replay API | 只有非重复 replay 证据和小团队维护收益超过 adapter/升级/排障成本才考虑 |

## 7. CBAM 增量决策

| 选项 | 可量化收益 | 增量成本/风险 | 当前姿态 |
|---|---|---|---|
| 一个主 Harness + 薄 replay contract | 保留主 Harness 的运行能力，用自有最小合同统一 event、cassette、mode 和 effect 边界 | 需要候选 adapter、schema/环境锁定、脱敏和跨 C2–C5 关联 | **主路线，进入候选级 C6 验证** |
| Langfuse / Phoenix / OpenTelemetry | 可能减少 trace 存储、查询、可视化和跨服务关联工作 | 常驻存储/部署、隐私、许可证、退出成本；不会自动提供执行 replay 或副作用安全 | **保持候选，不因 fixture pass 自动引入** |
| Inspect AI 或同类评测框架 | 可能减少 dataset、实验和评分编排工作 | 不天然拥有 sandbox、环境快照、live replay policy 和副作用 broker | **只在 C7 成本与 C6 净收益证据后评估** |
| 第二个执行 Harness | 可能提供额外模型/工具生态或 replay API | 复制 session、Provider、权限、状态、事件和维护矩阵 | **不因 C6 引入产品拼盘** |

本轮的 CBAM 判断是职责分层而非永久排除：外部后端可以负责查询和评测体验，但
`recorded_view`/`simulated_replay`/`live_replay` 的模式合同、敏感数据边界和副作用
门禁必须保持可验证；否则外部 trace 的可视化收益不能抵消错误回放或隐私泄露风险。

## 8. 候选状态与不可接受边界

DeepSeek Harness、Pi Agent Harness、Codex Harness、OpenCode、Goose 当前 C6 均为
`unknown`。正式 Run 的 candidate baseline 明确记录原因：没有候选专属、固定源码/版本
的 C6 adapter；fixture contract pass 不能转化为候选 pass。

不可接受边界：

- 没有 replay mode 标签、cassette/environment identity 或执行计数的“回放”；
- 将日志/session 查看宣传为执行回放；
- `simulated_replay` 隐式访问 Provider、工具、网络或改变外部状态；
- `live_replay` 在无显式 approval/policy 记录时执行；
- 关键事件缺失、跨 Run 无法关联，或使用未知字段补猜结果；
- 用观测后端 trace 存在、C1/C5 通过或 fixture 15/15 pass 抵消候选级 C6 unknown；
- 未经脱敏/保留/退出策略将真实源码、凭证引用或 Provider 数据纳入长期 cassette。

## 9. W7 入口与下一步

W6 C6 fixture/ATAM 收口后，候选级验证至少要为一个主候选建立固定版本 adapter，并
验证：

1. 候选原生事件是否覆盖 Provider、tool、policy、state、diff/test、environment 和 artifact 关联；
2. `recorded_view` 是否只读，`simulated_replay` 是否真正 cassette-only；
3. `live_replay` 是否由 C2 的审批和宿主边界 fail-closed 保护；
4. C6 replay 是否能关联 C3/C4 的幂等、恢复、副作用和 C5 的 Provider fallback ledger；
5. 脱敏、访问控制、TTL、备份恢复、删除/导出和排障流程是否满足个人开发者/小团队约束。

完成候选 adapter、版本绑定和可复核失败/通过样本前，候选继续保持 `unknown`。本
节点完成不等于 W6 最终采用，也不授权开始 ZWorkbench 产品实现；路线图下一节点为
`1-2-5：单人运维、恢复与生命周期场景`。

## 10. 证据索引

- [W6-0.1 C6 fixture findings](./w6-c6-replay-findings.md)
- [C5 多 Provider 可迁移性 ATAM](./w6-atam-c5-provider-portability.md)
- [C2 fail-closed 安全 adapter](./w6-atam-c2-safety-approval.md)
- [C4 中断、恢复与副作用重试](./w6-c4-recovery-findings.md)
- [W6 ATAM/CBAM 模板](./w6-atam-template.md)
- [持续评估控制面证据](./w6-continuous-evaluation-findings.md)
