# W4 findings：可观测性、记录、回放与评测基础设施的可行边界

## 研究元数据与证据状态

- 研究日期：2026-08-30（Asia/Shanghai）。本文件是 findings，不是技术选型报告，也不包含最终推荐。
- 研究问题：核实 Langfuse、Arize Phoenix、AgentOps、OpenTelemetry GenAI 语义约定及必要替代方案，回答它们实际记录什么/不记录什么、trace/span 与工具和模型事件、脱敏与成本/延迟、确定性或近似回放依赖、跨 Harness/Provider 统一事件模型、自托管与许可证，以及哪些能力必须由工作台自己拥有。
- 比较对象：`langfuse/langfuse`、`Arize-ai/phoenix`、`AgentOps-AI/agentops`、`open-telemetry/opentelemetry-specification`、`traceloop/openllmetry`、`braintrustdata/braintrust-sdk`。
- GitHub 采集：已按 `zj-research` 的 `zj-research-brief/v1` 发起 fresh collection；因匿名 GitHub API 配额在编译阶段耗尽，未产生 sealed ledger。可复核的请求和阻塞状态分别见 [`w4-research-brief.json`](./w4-research-brief.json) 与 [`w4-research-collection-status.json`](./w4-research-collection-status.json)。因此本文件**不宣称** stars、topic match、仓库 HEAD 或提交级比较；直接 `main` 链接只用于阅读一手文本，不能替代提交钉死的 ledger。
- 文档锚点：Langfuse 自托管页明确显示 Version v4；AgentOps 文档按 v2；OpenTelemetry 原 `opentelemetry-specification` 的 GenAI 页面明确声明内容已迁移到独立的 `semantic-conventions-genai` 仓库；迁移后的 GenAI 文档仍标为 Development，并引用 core semantic conventions v1.44.0、trace API v1.56.0、logs data model v1.55.0；OpenLLMetry 隐私页以 v0.49.2 / JS v0.21.1 为分界。Phoenix 与 Braintrust 页面未显示可供本次核验的产品版本，故只锚定访问日期。[OT-0]

## 术语边界

本文严格区分四件事：

| 词 | 本文含义 | 能回答的问题 | 不能自动推出的能力 |
| --- | --- | --- | --- |
| 观测（observability） | 对运行中的系统产生的 trace/span/metric/event 进行查询、聚合和可视化 | 发生了什么、耗时/成本/错误在哪里 | 不能把一次运行重新执行 |
| 记录（recording） | 把输入、输出、调用参数、工具结果、环境和关系持久化为可查询事实 | 事后查看某次运行 | 不能保证可重建外部世界或再次得到同一输出 |
| 回放（replay） | 从记录重新驱动执行，或用已记录依赖替代真实依赖，产生新的运行 | 改代码/改 prompt 后重跑同一轨迹 | 仅有 UI 时间线、会话查看、trace 导入都不等于回放 |
| 评测（evaluation） | 用数据集、任务和 evaluator/scorer 对输出或轨迹给出分数/标签/解释 | 是否更好、是否回归、是否满足 rubric | 评分结果不等于因果证明，也不保证任务重跑确定 |

## 先给事实结论（不构成推荐）

1. 这些系统都能做“观测 + 记录”的一部分；真正的“执行回放”不是它们的共同基线。Langfuse 的 session replay 是对已记录交互的查看/分析；AgentOps 的 session replay/水位图同样是 recorded session 的展示；Phoenix 的 ATIF 功能把已有 trajectory 导入为 span tree；这些来源都没有因此证明可以从 trace 独立重建并安全重执行原始工具和模型调用。[LF-3][AO-1][PH-5]
2. 评测基础设施与观测可以相连，但语义不同。Langfuse、Phoenix、Traceloop、Braintrust 都有数据集/实验/评分或监控路径；其中实验是“用同一输入集重新运行任务并比较结果”，不是把原始运行的外部副作用、网络响应和模型随机状态恢复出来。[LF-5][PH-4][OL-5][BT-2]
3. OpenTelemetry GenAI 约定适合作为跨 Provider/Harness 的低层事件词汇和关联骨架，不是完整的工作台事件溯源协议。它规定 operation/provider/model、token usage、prompt/output（均可 opt-in）、tool definitions、tool call/result、retrieval、memory、agent/workflow 等信号；但内容采集默认关闭，外部内容存储引用仍是 TODO，且 GenAI conventions 状态为 Development。[OT-1][OT-2][OT-3]
4. 脱敏不能只放在后端 UI。OTel 约定要求 instrumentation 默认不采集敏感正文；Phoenix/OpenInference 提供隐藏字段/截断；Langfuse 的推荐 Python hook 在导出阶段作用于该 Langfuse exporter 的 span 副本。任何额外 exporter、工具执行副作用、工作台自己的事件库，都需要单独的策略。[OT-1][PH-3][LF-6]
5. “统一事件模型”可统一 envelope、身份、父子关系、时间、状态、provider/model、usage 与可选 payload；不能假定各平台的业务对象相同。Langfuse 的 observation、Phoenix 的 OpenInference 属性、AgentOps 的 SESSION/AGENT/WORKFLOW/OPERATION/LLM/TOOL、Braintrust 的 typed span、OpenLLMetry 的历史 `gen_ai.prompt`/`gen_ai.completion` 字段存在明显差异。[LF-1][PH-1][AO-2][BT-1][OL-4]

## 统一底座：OpenTelemetry GenAI 约定

### 实际定义和记录什么

- GenAI client span 表示调用者观察到的逻辑操作；规范定义 `gen_ai.operation.name`、`gen_ai.provider.name`、请求/响应 model、conversation id、prompt name/version、sampling parameters、finish reasons、response id、TTFC、input/output/cache/reasoning token usage 等字段。`gen_ai.request.seed` 只表示请求携带了 seed；规范措辞是“更可能得到相同结果”，不是确定性保证。[OT-1]
- 规范覆盖 `chat`、`generate_content`、`text_completion`、`embeddings`、`retrieval`、`invoke_agent`、`invoke_workflow`、`plan`、`execute_tool`、memory 等 operation name。Agent/framework 约定把远程 agent invocation、内部 agent、workflow、plan 和 tool execution 作为不同 span 语义；`execute_tool` 是 INTERNAL span，工具调用参数/结果为 opt-in 内容。[OT-2][OT-3]
- `gen_ai.client.inference.operation.details` event 可独立存放输入/输出详情；`gen_ai.evaluation.result` event 记录 evaluator 名称、label/value 和 explanation；异常有 `gen_ai.client.operation.exception` event，涵盖 API error、rate limit、model error、timeout 等。GenAI events 尚处 Development，且部分语言尚未支持。[OT-3]
- 输入消息使用有顺序的结构化消息，可包含 assistant tool call 与 tool response；输出消息代表各 choice/candidate；tool definitions、retrieval documents/query、system instructions 也有对应结构/schema。[OT-1][OT-2]

### 明确不记录/不保证什么

- 默认不记录 system instructions、user input、model output：规范把它们列为大而敏感的内容，建议默认不捕获，或 opt-in 记录在 span/event，或存到外部受独立访问控制保护的存储中。[OT-1]
- 规范没有定义工作台级的重放协议、工具副作用回滚、网络/数据库 fixture、模型响应缓存、执行 determinism 或跨平台实验身份。外部内容引用的“common approach”在当前文档中仍是 TODO；因此 OTel 能做关联和交换，不能单独提供 replay。[OT-1]
- 规范不把 seed 写成“相同 seed 必然相同”；它只说结果更可能相同。Provider 服务端版本、权重、隐性状态、工具结果、检索索引、时间和并发仍是潜在变量。[OT-1]
- `gen_ai.provider.name` 是 instrumentation 所知的 provider，可能是代理/托管层而非最终上游；它应与 provider-specific attributes/signals 一致。这为跨 provider 统一提供了 discriminator，但不消除代理、模型别名、返回模型和真实计费主体之间的差异。[OT-1]

### 成本、延迟和隐私边界

- token usage 约定建议记录 input/output 及 cache/reasoning 等细分；规范还要求在 provider 同时报 billed 与 consumed 时优先报告 billed count。它不提供通用 USD 价格表，金额推导仍是 backend/application 的责任。[OT-1][OT-2]
- 全正文会增加 telemetry envelope、属性限制和存储成本；规范建议外部存储或截断。外部上传 hook 应在 sampling decision 之外执行，但具体上传、异步化、引用字段、访问控制由 application/distro 负责；因此“未采样 span”不能被理解为正文绝不会离开进程。[OT-1]
- 流式 chunks 的规范章节当前为 TODO；若工作台要做 token-by-token/first-token/partial tool-call 回放，不能只依赖当前 GenAI semconv。[OT-1]

## 逐项核验

### Langfuse

**记录模型。** Langfuse 将数据组织为 session、trace、observation；observation 是 LLM call、tool call、retrieval 等步骤，可嵌套，且有 generation/event 等 LLM-specific observation type。trace 负责把共享 `trace_id` 的 observations 归组，session 可把多条 trace 组成多轮交互。[LF-1] 其 v4 SDK 同时使用 OpenTelemetry；默认 exporter 过滤 Langfuse SDK span、带 `gen_ai.*` 的 span 和已知 LLM instrumentation scope，也可改为导出全部。[LF-6]

**具体记录与未记录。** 文档明确把 prompt、model response、token usage、latency、tools/retrieval steps作为 tracing 的核心；成本页说明 generation/embedding observation 保存 usage details 与 USD cost，成本可由响应 ingested 或由 model definition 推导。[LF-1][LF-7] Session 页的“simple session replay”是把多条已记录 trace 组成整个交互并在 UI 查看/分析；同页没有给出重新调用 provider、重放工具副作用或冻结外部依赖的执行协议，因此应归类为观测记录的 session replay，而不是 deterministic execution replay。[LF-3]

**评测。** Dataset item 是 input 加可选 expected output；dataset run/experiment run 把每个 item 链到新的 trace，并可附加 score。SDK experiment runner 支持本地或 Langfuse-hosted dataset、并发限制、任务/逐项与 run-level evaluator、错误隔离和自动 tracing；本地 dataset 不会自动形成 Langfuse dataset run，主要追踪 traces/scores。[LF-4][LF-5] 文档明确区分 code evaluator（可确定的程序检查）和 LLM-as-a-judge；前者的评分函数可确定，后者仍受 judge model 变化影响。[LF-4]

**脱敏、成本、延迟。** `LANGFUSE_SAMPLE_RATE`/`sample_rate` 在 client 端按 trace 决策；采样一个 trace 时，该 trace 的 observations 和 scores 一起采样，默认 rate=1。[LF-2] Python 推荐的 `mask_otel_spans` 在 export stage、经过 should-export 和 media handling 后，接收一个批次的只读 span snapshot，可删除/替换 span attributes；它不能改 span name、ID、parent、resource、events、links 或 instrumentation scope，且只影响发往该 Langfuse client 的副本。hook 是同步的，通常运行在 batch processor worker；慢或出错会拖住/丢弃 batch，因此不能把它当作任意网络 DLP 服务。[LF-6]

**互操作、自托管与许可证。** Langfuse 可以接入既有 OTel setup，但文档明确 global TracerProvider 的多个 processor 会看到同一批 span，过滤父 span还可能造成 orphan child；这说明 OTel 关联能互通，backend 语义与过滤策略仍需管理。[LF-6] v4 self-host 文档说明 Docker、Helm、Terraform 等部署；Web/Worker 之外依赖 Postgres、ClickHouse、Redis/Valkey、S3/blob，trace ingestion 先异步写入 S3 再由 worker 入 ClickHouse，部分功能依赖外部 LLM API/gateway。[LF-8] 当前 LICENSE 文本声明 `ee/`、`web/src/ee/`、`worker/src/ee/`使用 `ee/LICENSE`，其余受限外内容为 MIT Expat，第三方组件保留原许可证；所以不能只用“MIT”概括整个仓库。[LF-9]

**工作台仍需拥有的部分。** 来源没有给出跨 harness 的 canonical command/tool side-effect log、工具执行前后可恢复快照、provider response cassette、重放安全策略或实验 artifact lock。[LF-3][LF-5] Langfuse 可接收 trace、dataset、score 和 experiment relation，但“哪些输入允许重跑、怎样去重、怎样隔离副作用、怎样证明使用的是同一 prompt/model/tool version”仍落在工作台/任务 runner。[LF-5]

### Arize Phoenix

**记录模型。** Phoenix 通过 OTel/OTLP 接收 traces，并以 OpenInference/各框架 instrumentation 展示 LLM application 的 document retrieval、embeddings、LLM invocation、response generation、latency、token usage、exceptions、LLM parameters、prompt template variables、tool descriptions 和 function calls；trace 也可按 session ID 组织为多轮 conversation。[PH-1][PH-2] 它的自然单元仍是 OTel trace/span 和 OpenInference attributes，不是一个独立的“完整 agent event log”。

**具体记录与未记录。** Phoenix 文档明确支持查看输入/输出、工具、检索文档和模型参数，但“trace visualization”本身只说明如何理解已发生的路径。[PH-1] Phoenix 的 ATIF importer 能把已有的 agent trajectory JSON 转成 OTel-compatible span tree；它支持 parent/child subagent linking、continuation merge、字段映射、确定性 trace/span ID，并声称同一 trajectory 重传会得到同一 trace，避免重复。[PH-5] 这是一种**轨迹导入/幂等身份重建**，不是重新运行模型或工具；若没有 ATIF/原始 trajectory、工具结果和上下文，Phoenix span tree不能凭空恢复它们。长会话约 16+ turns 且工具调用密集时，完整 conversation history 可能超过 OTel attribute 限制而被截断，这是该导入路径明确记录的平台限制。[PH-5]

**评测。** Phoenix 同时支持 client-side SDK evaluations 和 server-side UI evaluations，可在 traces、experiment results 或 datasets 上运行；提供 deterministic code evaluators 与 LLM-as-a-judge，支持 RAG/tool-calling 指标，并对 evaluator 自身做 OTel tracing。[PH-3] 文档称 evaluator trace 会捕获输入、发给 judge 的 exact prompts、model full reasoning、final scores 和 timing；这说明评测过程本身可观测，但也意味着 judge prompt/reasoning 是额外敏感数据。[PH-3] Dataset experiment 的定义是用相同 inputs/evaluation criteria 比较不同 application version；它是 controlled rerun/evaluation，不等于原始环境的 replay。[PH-4]

**脱敏、成本、延迟。** Phoenix/OpenInference TraceConfig 提供 `HIDE_INPUTS`、`HIDE_OUTPUTS`、隐藏 input/output messages、images、text、embedding vectors、LLM invocation parameters、prompts、tools，以及 base64 image max length=32,000；文档列出的默认值为 False，故 instrumentation 默认可能记录这些内容，需显式改配置。[PH-3] Evals 页面声称 built-in concurrency/batching 最多 20x speedup、自动处理 rate limit/retry/dynamic concurrency；这是产品文档的能力描述，不是本研究独立测量的保证。[PH-3] Phoenix trace 文档能显示 token usage；本轮未在所读 Phoenix 页面找到通用 provider price table 或一个统一的 USD cost 推导契约，故金额字段和成本准确度应视为需按 instrumentation/部署核验的未知项。

**互操作、自托管与许可证。** Phoenix 接受 OTLP，并列出多语言、provider 和 framework integrations，因此可把不同 harness/provider 映射到 OTel/OpenInference span 树；但各 instrumentation 的属性完整度仍决定能否统一查询。[PH-1] self-host 文档声明 free/no feature limitations、数据留在本地、可 air-gap，并列 Docker/Compose、Kubernetes/Helm、AWS、Railway、Render、Cloud Run、Azure 等路径。[PH-6] 当前 LICENSE 是 Elastic License 2.0，禁止把软件作为给第三方提供实质功能的 hosted/managed service，并限制绕过 license-key 功能；“可自托管”不能简化为“可自由托管 Phoenix 给别人”。[PH-7]

**工作台仍需拥有的部分。** Phoenix 提供 span viewer、ATIF import、dataset/eval/experiment API 形状，但来源没有证明它能记录任意 harness 的完整 action precondition、filesystem/network/database snapshot、不可逆副作用补偿或 provider cassette。ATIF 是一条可用的轨迹交换入口；工作台仍需定义自己的事件完整性、版本封存、重放模式（真实/模拟/禁止）和副作用边界。

### AgentOps

**记录模型。** AgentOps v2 文档描述 SESSION 为一次 workflow execution 的 root，下面可有 AGENT、WORKFLOW、OPERATION/TASK、LLM、TOOL span；decorators 还列出 GUARDRAIL span。[AO-1][AO-2] LLM span记录 model/provider、prompt/completion tokens、estimated cost、messages；TOOL span记录 tool name/input/output/duration；operation/task记录参数/result/duration/status。[AO-2] SDK 可自动发现支持的 provider，也可用 decorator/manual trace 控制。[AO-3]

**具体记录与未记录。** AgentOps README 和 dashboard 文档称 session replay、timeline/tree、chat viewer、LLM calls、Action/Tool/Error waterfall可查看；这证明了 recorded session 的查询与展示，不证明“重新执行原函数/工具/模型”。[AO-4][AO-1] public API 明确是 read-only：可以取 trace/span details 和 metrics，创建 trace/span 要用 SDK/instrumentation；这进一步把 API 定位为记录读取接口而不是 replay engine。[AO-5]

**评测、脱敏、成本/延迟。** 本轮审阅的 AgentOps v2 文档有“testing”产品定位和 tracing/metrics，但没有找到 dataset、experiment、evaluator/scorer、ground-truth snapshot 的公开 v2 API/规范；因此“AgentOps 是否提供可复核的离线评测流水线”保留为未知，不能因为首页写了 evaluate 就补全该能力。[AO-4][AO-5] 文档明确有 LLM estimated cost 和 `@tool(cost=...)`，但本轮没有找到统一价格表、sampling 控制、正文 masking/field-level redaction 或 retention contract。它提供 `AGENTOPS_ENV_DATA_OPT_OUT`，且默认不 opt out；环境数据包括 OS/version、Python version、anonymized hostname、SDK version。[AO-3][AO-6] 因此环境记录是明确存在的，prompt/tool payload 的脱敏和 exporter 延迟则是未知项。

**互操作、自托管与许可证。** AgentOps 自称建立在 OTel 之上，v2 trace state可映射到 OTel StatusCode，且手册支持 semantic-convention keys 如 `agent.name`、`workflow.name`。[AO-1][AO-7] 这有利于关联，但其高层 span kind 命名仍是 AgentOps 自己的层级；不能把 AgentOps kind 自动等同于 OTel GenAI span type。[AO-2] v2 self-host 文档描述完整 backend/dashboard，依赖 FastAPI、Supabase/Postgres、ClickHouse、OTel Collector、Supabase Storage，支持 Docker/Compose、Kubernetes 和云平台。[AO-8] README 声明 app directory 为 MIT，当前 `LICENSE` 也为 MIT；自托管整个 app 仍需自行承担这些依赖、升级、备份与安全。[AO-4][AO-9]

**工作台仍需拥有的部分。** 来源没有给出跨 provider 的稳定 canonical payload schema、回放 cassette、工具副作用隔离、评测数据集版本锁或 evaluator execution record。AgentOps 能成为 session/span 记录读取端，但上述缺口不能由“session replay”措辞填补。

### OpenLLMetry（Traceloop）

**记录模型。** OpenLLMetry 是建立在 OTel 之上的 non-intrusive instrumentation；SDK 和单独 instrumentation可以把 traces 导出到 Traceloop 或现有 OTel stack，覆盖 LLM provider、vector DB、framework、MCP 等。[OL-1][OL-2] 当前文档的自定义语义约定列出 workflow/task/agent/tool，并记录 model requested/actual、temperature/top_p、prompt/completion、token usage、reasoning、function definitions、headers、vector query/result 等。[OL-3]

**具体记录与未记录。** 配置文档明确说默认把 prompts、completions、embeddings写入 span attributes，可用 `TRACELOOP_TRACE_CONTENT=false` 关闭；默认 batch processor可用 `disable_batch=True` 关闭。[OL-4] 这是真正的 recording surface，不是 replay surface。本轮 OpenLLMetry OSS instrumentation 文档未找到从 trace 驱动原始代码/工具/模型重执行的 replay 协议；Traceloop 产品的 experiments/datasets/monitors是另一个平台能力，不能把 SDK 的 OTel span exporter等同为 replay。[OL-5][OL-6]

**评测、脱敏、成本/延迟。** Traceloop 平台文档有 datasets、experiments、实时 monitors；monitor 是对匹配 span 异步执行 evaluator，可是 LLM-as-a-judge 或 deterministic structural/safety/syntax checks。[OL-5][OL-6] 配置文档说明 token enrichment可能使首次请求增加 latency，并可关闭；batching影响本地可见性和发送行为。[OL-4] 文档没有给出统一 USD cost 的跨 provider 可信契约，也没有在 OpenLLMetry SDK 页面证明字段级 PII redaction；正文整体关闭是明确能力，细粒度 masking需视具体 instrumentation/collector。

**互操作、自托管与许可证。** OpenLLMetry 的核心价值是输出标准 OTel，可指向 Datadog、Honeycomb、OTel Collector、Braintrust 等多个 destination；这使它适合作为 instrumentation layer，而不是必须绑定一个 backend。[OL-2] 其语义约定页面同时说“work in progress”，并使用旧式 `gen_ai.prompt`/`gen_ai.completion` 命名；当前 OTel GenAI repository已转向 `gen_ai.input.messages`/`gen_ai.output.messages`，因此跨版本字段映射必须显式处理。[OL-3][OT-1] README 声明 Apache 2.0。[OL-2] 本轮未找到 OpenLLMetry 完整 Traceloop SaaS backend 的自托管部署契约；能确认的是 SDK 可将 OTLP发往自定义 endpoint/exporter，不能据此确认平台全栈可本地化。[OL-4]

**工作台仍需拥有的部分。** 需要自己决定采哪些正文、如何把旧/新 semconv 映射为 canonical event、如何捕获非 OTel 的 harness state、怎样存 provider cassette 与工具副作用，以及怎样把平台 experiment 结果和本地代码版本/依赖锁绑定。

### Braintrust SDK（替代参照）

**记录模型。** Braintrust 把 trace 作为端到端 execution，把 span分成 eval、task、llm、function、tool、score、classifier；span可嵌套，并记录 input/output、metadata、latency、token counts、cost、scores。[BT-1] 其 OTel recipe通过 `BraintrustSpanProcessor`接收 OTel，支持 `filterAISpans`，并可把 trace parent指向 project/experiment/span；这是 OTel ingestion 到 Braintrust log/span model 的适配，不是 Braintrust 与所有后端共享同一 schema。[BT-4]

**具体记录与未记录。** 官方 tracing 页明确说 instrumented request captures inputs/outputs、model parameters、timing、token usage/cost、nested function/tool calls、errors/custom metadata；这覆盖观测记录。[BT-1] 评测页把 playground（可变）、experiment（immutable comparable record）、CI/CD、online scoring分开；online scoring异步执行以免影响请求 latency，但因 live request没有 ground truth，依赖 LLM-as-a-judge。[BT-2] 这清楚地说明 experiment rerun/eval和recorded trace不是同一件事；本轮未在 SDK/guide中找到 provider response cassette、工具副作用快照或“从 trace 一键执行回放”。

**评测、脱敏、成本/延迟。** Dataset可有 input、可选 expected output、metadata和版本/snapshot；Eval的 task可以是多步 agent、retrieval pipeline或任意 workflow，scorer可以是 code、autoeval或LLM judge。[BT-2][BT-3] tracing文档声明 input/output 默认是记录面；本轮未在所读 Braintrust SDK/OTel/self-host 页面找到与 Phoenix hide fields 或 Langfuse mask hook等价的通用字段级脱敏契约，故细粒度 masking、采样和 retention为未知；online scoring的“no impact on latency”是其官方异步架构描述，不是本研究基准结果。[BT-2]

**互操作、自托管与许可证。** Braintrust 提供 OTel processor，但仍以自己的 logs/experiments/datasets/span types 查询和评测。[BT-4] Self-hosting是 data-plane/control-plane split：data plane存 experiment/log/trace/span/dataset/prompt completion，control plane保留 UI、auth、metadata；SDK直发 data plane，control plane默认接收健康/系统/usage telemetry而非 logs/traces/customer data。[BT-5][BT-6] 这不是完全断网的全栈 self-host。`braintrust-sdk` 当前 LICENSE 是 Apache 2.0；不能把 SDK 许可证等同于整个平台 data/control plane 的运营权。[BT-7]

**工作台仍需拥有的部分。** 若选择这一类 eval/log backend，工作台仍需拥有本地事件封存、重放模式和副作用策略，以及把 project/experiment/dataset snapshot与 commit、Harness版本、provider/model、tool definition和环境依赖绑定的 artifact identity。

## 跨 Harness / Provider 的统一事件模型：能统一到哪里

以下是由来源共同支持、且适合作为“工作台事件 envelope”边界的字段族；这不是实现设计或最终推荐：

| 层 | 可跨系统共享的事实 | 仍需工作台补齐的事实 |
| --- | --- | --- |
| 关联 | trace/run/session id、span id、parent id、start/end/duration、status/error | 事件版本、ingest idempotency、跨文件/跨 continuation 的稳定 identity |
| Actor/调用 | operation kind、provider、requested/response model、agent/workflow/tool name | harness-specific agent state、真实上游 vs proxy、模型别名解析、工具版本与权限 |
| 内容 | 可选 system/input/output messages、tool definitions/call args/result、retrieval docs/query | 内容引用、加密/访问控制、字段级 redaction provenance、是否可复现的完整上下文 |
| 资源 | input/output/cache/reasoning token、latency、TTFC、estimated/ingested cost、error | provider billing period/price-table version、工具/检索成本、资源快照、预算决策 |
| 评测 | score/label/explanation、dataset item、expected output、evaluator/judge metadata | evaluator code/model/prompt version、dataset snapshot hash、重复运行规则、统计置信度 |
| 执行 | OTel span/event 是已发生操作的事实；ATIF 可把已有 trajectory 变成 span tree | replay plan、真实/模拟/禁止 mode、HTTP/LLM/tool cassette、DB/vector index/filesystem snapshot、side-effect compensation |

上表的共同字段边界来自 OTel span/event、各产品的 trace/span 数据模型和 ATIF 映射；各产品并未因此承诺完整互换。[OT-1][OT-2][OT-3][PH-5][LF-1][AO-2][BT-1] OTel `provider.name` 的 discriminator 语义能让不同 provider 的查询有共同入口，但 OpenLLMetry的旧字段、Phoenix/OpenInference字段、Langfuse observation字段、Braintrust typed span字段不应在接入层被“猜测式”互转；应保存原始属性和规范化字段两份，尤其是 prompt/output、tool call/result、usage/cost。[OT-1][OL-3][PH-1][LF-1][BT-1]

## “确定性 / 近似回放”的真实依赖

### 确定性较强的部分

- 读取同一已记录 trace/session/ATIF trajectory并按其原时间/父子关系展示：依赖记录完整性和稳定 ID，不依赖再次调用模型。Phoenix ATIF importer明确提供 deterministic IDs与重复上传去重；这属于记录重建/可视化的确定性。[PH-5]
- code evaluator、exact match、regex、结构校验等：在同样 input/output、同样 evaluator code/version下，评分通常是可重复的；Phoenix和Langfuse都把 code-based/deterministic evaluator与LLM judge分开。[PH-3][LF-4]
- 同一个 dataset snapshot上对不同 application versions运行：输入集可固定，但输出、工具响应和模型版本仍可能变；因此是可比较的实验控制，不是原始运行的确定重演。[LF-5][PH-4][BT-2]

### 只能近似或依赖外部封存的部分

- 模型调用：seed只提高相似概率，不封存服务端权重、sampling实现、system state、provider version或网络条件。[OT-1]
- 工具/检索：必须封存工具定义、参数、返回值、错误、时间、权限和外部数据版本；OTel/产品 trace 可以记录其中一部分，但没有替工作台自动快照/回滚的证据。[OT-2][PH-1]
- agent/harness：需要记录计划、handoff/subagent关系、状态机转移、人工中断、重试、并发顺序、上下文压缩和 continuation。OTel已有 agent/workflow/plan名称，Phoenix ATIF支持 subagent/continuation import，但完整 harness state仍取决于 exporter/ATIF producer。[OT-2][PH-5]
- 评测：LLM-as-a-judge有 judge model/prompt/temperature/provider 变量；online eval又没有 ground truth。它们是带版本和成本的近似质量信号，不是 deterministic oracle。[PH-3][BT-2][OL-6]

## 哪些能力必须由工作台自己拥有

这里是从各来源明确边界推导出的“责任归属”，不是推荐某个产品：

1. **Canonical event ledger。** 保存原始 OTel/OpenInference/Langfuse/AgentOps/Braintrust payload，另外生成带 schema version 的规范化 envelope；不能只保 UI 可见的 span字段，否则 prompt、tool call/result、评测 explanation和未知扩展会丢失。[OT-1][PH-3][LF-6]
2. **采集政策与可证明脱敏。** 在进程出口、collector、backend exporter分别配置正文开关、字段级 masking、截断、外部 blob 引用、加密、访问审计和删除；记录“原始值是否采集、在哪里被删除、哪个策略版本处理”。Phoenix 的 hide controls只覆盖其 instrumentation 配置，Langfuse mask hook只覆盖其 exporter副本。[PH-3][LF-6]
3. **Replay contract。** 明确 recorded-view、simulated replay、live replay、禁止 replay 四种模式；每个 tool/model/network event 要有 cassette/reference、输入 hash、输出 hash、时间、版本、失败行为和 side-effect policy。任何 session replay、trace import、实验 rerun在没有这层 contract时都不能被命名为执行回放。[LF-3][AO-4][PH-5]
4. **副作用与状态快照。** 文件系统、数据库、向量库、浏览器、支付/消息/HTTP 工具等不能由 observability backend替工作台回滚；需要工作台定义 sandbox、dry-run、allowlist、snapshot、compensation和人工确认点。各候选一手资料没有给出统一的通用副作用恢复机制。[OT-1][PH-5][BT-1]
5. **运行身份与 artifact lock。** 把 harness/agent code commit、prompt/version、tool schema/version、provider/model/endpoint、SDK/instrumentation、dataset snapshot、evaluator code/judge model、配置和环境依赖绑定到 run；否则“同一输入”不足以说明是同一实验或可比回放。[OT-1][LF-5][BT-3]
6. **评测编排与证据。** backend可提供 evaluator执行和分数，但工作台需要保存任务输入、expected output、score schema、judge rationale是否允许持久化、重试/并发、成本上限、失败样本与统计汇总，并区分在线无 ground truth 与离线有 snapshot。[PH-3][BT-2][LF-4]
7. **跨 backend 语义降级。** 记录哪些字段来自标准 semconv，哪些是 vendor extension，哪些在导出时被丢弃/截断/脱敏；特别要处理 OTel GenAI conventions 的 Development 状态和 OpenLLMetry旧/新字段迁移。[OT-1][OL-3]

## 未知项与不应作出的负面结论

以下不是“没有能力”，而是本轮一手资料范围内未得到可复核证据：

- GitHub stars、topic match、各仓库准确 HEAD/commit、按 commit 的源码差异：fresh sealed ledger被 GitHub 配额阻塞，不能用 mutable `main` 补齐。
- AgentOps v2 是否有尚未公开/未纳入所读文档的 dataset/experiment/evaluator API；其 v2 文档只足以确认 tracing、read-only trace API、自托管和环境 opt-out。[AO-5][AO-6]
- Phoenix 当前版本的统一 USD cost price table、细粒度 retention/sampling contract，以及所有 language instrumentation的字段完整度。[PH-1][PH-3][PH-6]
- Langfuse “session replay”在 UI 之外是否存在可调用的真实执行 replay API；本轮来源只证明 session view/replay和实验 runner，没有证明 replay engine。[LF-3][LF-5]
- OpenLLMetry/Traceloop full platform 的自托管边界、旧 `gen_ai.prompt` 到当前 OTel `gen_ai.input.messages` 的自动迁移语义，以及配置页仍描述 telemetry collection、隐私页称 v0.49.2+不再收集 telemetry 之间的版本/页面一致性。应以具体安装包版本与源码再核验。[OL-3][OL-4][OL-7]
- Braintrust SDK/backend的通用 sampling、field-level masking、retention API；self-host security 页能证明数据平面隔离、URL/访问控制和 telemetry边界，但不等于 SDK payload masking。[BT-5][BT-6]
- 各产品是否能可靠捕获 streaming chunks、hidden reasoning、异步工具并发顺序和跨进程 context；OTel GenAI 当前 streaming chunks章节仍 TODO，产品集成需逐一验证。[OT-1]

## 一手来源索引

访问日期均为 2026-08-30；带 `/main/` 的 raw 源是 mutable 文本，仅作当前许可证/README核对，不代表提交级证据。

### OpenTelemetry

- [OT-0 — 原 specification 页面说明 GenAI conventions 已迁移](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OT-1 — GenAI client spans 与内容采集策略](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md)
- [OT-2 — GenAI agent/framework spans 与 tool execution](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
- [OT-3 — GenAI events/evaluation result/exception](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-events.md)

### Langfuse

- [LF-1 — Observability concepts/data model](https://langfuse.com/docs/observability/concepts)
- [LF-2 — Client-side trace-level sampling](https://langfuse.com/docs/observability/features/sampling)
- [LF-3 — Sessions and session replay view](https://langfuse.com/docs/observability/features/sessions)
- [LF-4 — Evaluation overview/methods](https://langfuse.com/docs/evaluation/overview)
- [LF-5 — Dataset experiments via SDK](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk)
- [LF-6 — Masking and existing OTel setup](https://langfuse.com/docs/observability/features/masking) / [OTel integration FAQ](https://langfuse.com/faq/all/existing-otel-setup)
- [LF-7 — Token and cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking)
- [LF-8 — Self-hosting v4 architecture/deployment](https://langfuse.com/docs/self-hosting)
- [LF-9 — Repository license text](https://raw.githubusercontent.com/langfuse/langfuse/main/LICENSE)

### Phoenix

- [PH-1 — Tracing overview and recorded fields](https://arize.com/docs/phoenix/tracing/llm-traces)
- [PH-2 — Sessions](https://arize.com/docs/phoenix/tracing/llm-traces/sessions)
- [PH-3 — Evaluations and OpenInference masking](https://arize.com/docs/phoenix/evaluation/llm-evals) / [Mask span attributes](https://arize.com/docs/phoenix/tracing/how-to-tracing/advanced/masking-span-attributes)
- [PH-4 — Datasets and experiments](https://arize.com/docs/phoenix/get-started/get-started-datasets-and-experiments)
- [PH-5 — ATIF trajectory import, deterministic IDs, limitations](https://arize.com/docs/phoenix/tracing/how-to-tracing/importing-and-exporting-traces/importing-atif-trajectories)
- [PH-6 — Self-hosting/air-gap/deployment](https://arize.com/docs/phoenix/self-hosting)
- [PH-7 — Repository license text](https://raw.githubusercontent.com/Arize-ai/phoenix/main/LICENSE)

### AgentOps

- [AO-1 — v2 core concepts, OTel foundation, sessions, spans](https://docs.agentops.ai/v2/concepts/core-concepts)
- [AO-2 — v2 span kinds and attributes](https://docs.agentops.ai/v2/concepts/spans)
- [AO-3 — v2 recording operations and supported LLM calls](https://docs.agentops.ai/v2/usage/recording-operations) / [advanced configuration](https://docs.agentops.ai/v2/usage/advanced-configuration)
- [AO-4 — Repository README, session replay/self-host claim](https://raw.githubusercontent.com/AgentOps-AI/agentops/main/README.md)
- [AO-5 — v2 read-only public API](https://docs.agentops.ai/v2/usage/public-api)
- [AO-6 — environment data opt-out](https://docs.agentops.ai/v2/usage/advanced-configuration)
- [AO-7 — manual trace metadata and semantic convention mapping](https://docs.agentops.ai/v2/usage/manual-trace-control)
- [AO-8 — v2 self-host architecture/deployment](https://docs.agentops.ai/v2/self-hosting/overview)
- [AO-9 — Repository license text](https://raw.githubusercontent.com/AgentOps-AI/agentops/main/LICENSE)

### OpenLLMetry / Traceloop

- [OL-1 — What is OpenLLMetry](https://www.traceloop.com/docs/openllmetry/introduction)
- [OL-2 — Repository README, OTel destinations/instrumentations/license](https://raw.githubusercontent.com/traceloop/openllmetry/main/README.md)
- [OL-3 — GenAI semantic conventions used by OpenLLMetry](https://www.traceloop.com/docs/openllmetry/contributing/semantic-conventions)
- [OL-4 — SDK initialization, batching, content, token enrichment](https://www.traceloop.com/docs/openllmetry/configuration)
- [OL-5 — Traceloop datasets/experiments](https://www.traceloop.com/docs/datasets/sdk-usage) / [experiments](https://www.traceloop.com/docs/experiments/introduction)
- [OL-6 — real-time monitors/evaluators](https://www.traceloop.com/docs/monitoring/introduction)
- [OL-7 — telemetry privacy/version note](https://www.traceloop.com/docs/openllmetry/privacy/telemetry)

### Braintrust

- [BT-1 — tracing model and captured fields](https://braintrust.dev/docs/guides/traces)
- [BT-2 — offline/online evaluation and immutable experiments](https://braintrust.dev/docs/guides/evals)
- [BT-3 — datasets, snapshots and Eval API](https://braintrust.dev/docs/annotate/datasets/use-in-evaluations)
- [BT-4 — OTel backend recipe](https://braintrust.dev/docs/cookbook/recipes/OTEL-logging)
- [BT-5 — self-host data/control plane](https://braintrust.dev/docs/admin/self-hosting)
- [BT-6 — self-host security and telemetry boundary](https://braintrust.dev/docs/admin/self-hosting/configure/security)
- [BT-7 — SDK repository license text](https://raw.githubusercontent.com/braintrustdata/braintrust-sdk/main/LICENSE)
