# W3：开源替代方案与组合件 findings

状态：研究 findings，未作最终推荐  
研究日期：2026-08-30  
目标：单用户个人开发者工作台，覆盖通用任务、代码项目、自动/定时任务、多 Provider、可观测/回放/评测与调试。  
范围：执行型 Harness、代码 Agent、通用编排/调度、Provider 网关、工作流/重试、评测/观测组件。

## 1. 证据方法与边界

本笔记按 `zj-research` 的 multi-repository technical comparison 分支执行。统一 brief、criteria、候选仓库和抓取预算保存在 [v6 request](./w3-open-source-alternatives.v6.request.json)；fresh collection 的 sealed ledger 在 [v6 ledger response](./w3-open-source-alternatives.v6.ledger-response.json)，运行状态在 [v6 collection status](./w3-open-source-alternatives.v6.collection-status.json)。ledger 的 `observedAt` 为 `2026-08-30T03:04:22.134Z`。

sealed ledger 覆盖 10 个仓库、40 个 commit-pinned 文件、79 条 canonical Evidence；它提供候选仓库的 `stars`、`topicMatch` 和 immutable revision。表中的热度只使用该 ledger；`topicMatch` 是采集器的关键词匹配量，不是能力评分，也不是推荐分数。每条能力判断都同时给出官方文档、源码、规范或发布记录；没有证据的地方保持 unknown，不把“未查到”写成“没有”。

两项补充候选（Temporal、Inspect AI）在官方资料中证明相关，但其 GitHub tree 含 `commit` 类型的 submodule/gitlink，当前 pinned compiler 返回 `unsupported entry type: commit`，所以没有伪造 sealed ledger。它们的能力结论来自官方文档，热度不进入下表；许可证与人工 commit ref 只作为未封存补充，不能与 ledger 数字等价。

## 2. 快速比较矩阵

| 项目（官方仓库） | 分层与角色（非最终推荐） | 热度：ledger stars / topicMatch | 能力覆盖（由一手资料证明） | 可组合性 | 许可证 / 维护 / 所有权风险 |
|---|---|---:|---|---|---|
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands/tree/f26d734a848297d8dcf460b0bb739174e76511f0) | 执行型 Harness 候选；当前仓库边界更准确地说是 Agent Canvas 前端/控制面 | 85,583 / 9 | Agent Canvas 产品资料覆盖 coding agents、automations、webhook/schedule、多个 backend 与 LLM；仓库 AGENTS 又明确该 repo 是 frontend，因此不能把此 repo 单独等同于完整 agent server。[[E:625319f43fbb2215e4f72e5b](https://github.com/OpenHands/OpenHands/blob/f26d734a848297d8dcf460b0bb739174e76511f0/AGENTS.md)] [[E:da7eef95433ce23f9db913d2](https://github.com/OpenHands/OpenHands/blob/f26d734a848297d8dcf460b0bb739174e76511f0/AGENTS.md)] | 前端 API、provider connections、MCP、ACP agent backend；需把 backend、automation backend 和前端边界分开核对。[[E:707c4dfd6a42f7271452a2ac](https://github.com/OpenHands/OpenHands/blob/f26d734a848297d8dcf460b0bb739174e76511f0/AGENTS.md)] | MIT；维护活跃只由本次 pinned snapshot/CI/release 文件证明，长期治理、backend 所有权边界与可独立复用性仍需核查。[[E:15376a4cce65feaf5eae3ee7](https://github.com/OpenHands/OpenHands/blob/f26d734a848297d8dcf460b0bb739174e76511f0/AGENTS.md)] [LICENSE](https://github.com/OpenHands/OpenHands/blob/f26d734a848297d8dcf460b0bb739174e76511f0/LICENSE) |
| [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5) | 代码 Agent / 专长执行器；不是完整个人工作台 | 20,171 / 15 | 官方 README 明确：让用户选择的 LM 自主使用工具，修复真实 GitHub repo、做安全漏洞任务或自定义任务；同时有 SWE-bench / batch / trajectory 资料。[[E:2163da933db2962c6f331d82](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/README.md)] | 单一 YAML 配置、工具/环境/模型可配置，适合作为代码任务执行器；没有被一手资料证明的内建计划调度、通用 Run 状态或跨 Harness 观测接口。[[E:33132d6d855675885cd0258e](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/README.md)] | MIT；官方 README 有版本/能力新闻，但长期维护主体、升级兼容契约和工作台集成责任仍未知。[[E:8e522216eb64767940a945dd](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/README.md)] [LICENSE](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/LICENSE) |
| [anomalyco/opencode](https://github.com/anomalyco/opencode/tree/dc4449df0d52199704ea4989a5a993ebbc605612) | 执行型 Harness / 开发者 CLI 候选 | 202,413 / 4 | 官方 README 将其定义为 open source AI coding agent；内置 `build`（开发全权限）、`plan`（只读并在 bash 前询问权限）和 `general` subagent。[[E:5511387e6a465a389c910a00](https://github.com/anomalyco/opencode/blob/dc4449df0d52199704ea4989a5a993ebbc605612/.opencode/glossary/README.md)] [[OpenCode docs](https://opencode.ai/docs/)] | 官方 docs 证明 provider、agent、plugin、MCP/API 等扩展面；其 session/server 协议适合作为嵌入点，但定时任务、跨 Run replay、评测与权限总账未由本轮证据证明。[[E:104cec52a85e599ed8a4eba1](https://github.com/anomalyco/opencode/blob/dc4449df0d52199704ea4989a5a993ebbc605612/AGENTS.md)] [[OpenCode providers](https://opencode.ai/docs/providers/)] | MIT；项目拥有多包/协议/生成 SDK 边界，升级时需同步 public Protocol/Server HttpApi；维护集中在 anomalyco，治理和 API 稳定性风险需单独验证。[[E:ca9d45928a8e62ae8b235633](https://github.com/anomalyco/opencode/blob/dc4449df0d52199704ea4989a5a993ebbc605612/AGENTS.md)] [LICENSE](https://github.com/anomalyco/opencode/blob/dc4449df0d52199704ea4989a5a993ebbc605612/LICENSE) |
| [aaif-goose/goose](https://github.com/aaif-goose/goose/tree/8ae4e4ba02836529790f47109b8785e8b42843a7) | 执行型 Harness 候选；也可作为可嵌入 Agent runtime | 53,669 / 7 | 官方 README 定义为 native open source AI agent，提供 desktop、CLI、API，面向 code、workflows 和一般任务；称支持 15+ providers、70+ MCP extensions。[[E:1a9d2b7df8403cf0e86f3f67](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/AGENTS.md)] [[E:70c8049e0a5649752283d460](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/AGENTS.md)] [[Goose README](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/README.md)] | agent loop 正在从 legacy loop 迁移到 state machine；provider、extension、MCP、custom distribution 是明确组合面，但迁移期间双路径会增加行为兼容与测试成本。[[E:d754c39f74327f8e5b07ac65](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/AGENTS.md)] [[E:f4a35813b470f4f7d372e38a](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/AGENTS.md)] | Apache-2.0；官方 README 指向 AAIF/Linux Foundation 与 governance，但实际 roadmap、state-machine 完成时点和长期决策权仍需跟踪。[[LICENSE](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/LICENSE)] |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph/tree/11ee185999b86bfea2d8c0e69cef9a5e37acf686) | 通用编排 / Agent workflow framework；组合件，不是现成工作台 | 40,685 / 5 | 官方 README 定义为 low-level orchestration framework，覆盖 stateful、long-running agents、durable execution、human-in-the-loop、memory。[[E:61f66f1e555eec67fd46c909](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/AGENTS.md)] [[E:03f9392fcf4b093d446b3409](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/AGENTS.md)] [[LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)] | Python/JS SDK、prebuilt agents、server/API、interrupts/checkpoint 等组合面；官方自己把它定位为 low-level，项目/文件/Shell/Git/权限/Provider gateway 仍需工作台拥有或另接。[[E:6bde8bfff41ffe22b1462ba6](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/README.md)] | MIT；LangChain 生态与 LangSmith 是明显的组织/产品耦合面；是否接受完全脱离 LangChain 的长期边界需验证。[[E:e5084ef764f8507a65fc7a46](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/AGENTS.md)] [LICENSE](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/LICENSE) |
| [temporalio/temporal](https://github.com/temporalio/temporal/tree/c044bf16b1cc47a4db80669a987484dba6145331) | 通用编排 / 工作流、调度、重试组件；不是代码 Agent | 未纳入 ledger；热度 unknown | 官方文档证明 Workflow Execution 会保留 Event History，可从历史重放以恢复状态；Schedules 可在指定时间启动 Workflow Execution；Retry Policy 提供失败后的声明式自动重试、backoff 和最大尝试次数。[[Temporal workflows](https://docs.temporal.io/workflows)] [[Temporal schedules](https://docs.temporal.io/schedule)] [[Temporal retry policies](https://docs.temporal.io/encyclopedia/retry-policies)] | 强 durable execution / replay / schedule / retry 语义，适合承载 Agent Run 外壳；它不提供代码编辑、模型 Provider、Agent tool loop 或个人工作台 UI。[[Temporal workflows](https://docs.temporal.io/workflows)] | 官方 pinned LICENSE 为 MIT；本次 compiler 因 gitlink 未产出 ledger，GitHub stars、维护活跃度和所有权风险不纳入量化，人工 ref 仅供复核。[[LICENSE](https://github.com/temporalio/temporal/blob/c044bf16b1cc47a4db80669a987484dba6145331/LICENSE)] |
| [BerriAI/litellm](https://github.com/BerriAI/litellm/tree/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee) | Provider 网关 / 路由 / 成本与限流组件 | 57,554 / 11 | 官方 ARCHITECTURE 将 SDK + AI Gateway 分开：Proxy 提供 auth、rate limiting、budgets、routing，SDK 负责 provider call、转换与 streaming；也记录 cost/logging。[[E:3e2b6a62a55edfd7aa5694cb](https://github.com/BerriAI/litellm/blob/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee/ARCHITECTURE.md)] [[E:7eefb0cb2e7f848c67986cfc](https://github.com/BerriAI/litellm/blob/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee/ARCHITECTURE.md)] | OpenAI-compatible gateway、provider transformations、router/fallback、cache、hooks 与 spend logging；不证明 Agent state、权限审批、项目 sandbox 或 replay。[[E:408910254d8b2110dab42b6c](https://github.com/BerriAI/litellm/blob/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee/ARCHITECTURE.md)] [[E:736a66227ecead287f93fe6b](https://github.com/BerriAI/litellm/blob/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee/ARCHITECTURE.md)] | 非 enterprise 目录 MIT；enterprise 目录由独立 `enterprise/LICENSE` 约束，不能只看 GitHub API 的 SPDX/NOASSERTION。供应商适配数量与 proxy 变化会带来升级/兼容成本。[[LICENSE](https://github.com/BerriAI/litellm/blob/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee/LICENSE)] |
| [langfuse/langfuse](https://github.com/langfuse/langfuse/tree/f6e56cbb6c6c001805e90c263efca995a3fd33ba) | 观测 / 评测 / 调试组件 | 33,912 / 11 | 官方定位为 open source LLM engineering platform，覆盖 developing、monitoring、evaluating、debugging；tracing 文档以 trace/span/observation 记录 LLM application。[[E:cf300c55dfd86e0dd8a6fd65](https://github.com/langfuse/langfuse/blob/f6e56cbb6c6c001805e90c263efca995a3fd33ba/.agents/AGENTS.md)] [[E:fc2f23fe47f87a5c62fcec45](https://github.com/langfuse/langfuse/blob/f6e56cbb6c6c001805e90c263efca995a3fd33ba/.agents/AGENTS.md)] [[Langfuse tracing](https://langfuse.com/docs/tracing)] | SDK/OTel、trace、scores/evals、datasets、self-host 文档；它是观测与评测面，不是 Agent execution loop、scheduler 或权限系统。[[Langfuse self-hosting](https://langfuse.com/docs/deployment/self-host)] | 核心 MIT Expat；`ee/`、`web/src/ee/`、`worker/src/ee/` 等按 `ee/LICENSE`，并有 ClickHouse copyright/组织所有权边界，部署与升级须按目录审计。[[LICENSE](https://github.com/langfuse/langfuse/blob/f6e56cbb6c6c001805e90c263efca995a3fd33ba/LICENSE)] |
| [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix/tree/37916d7351002222fc5a3ee8560528834da85134) | 观测 / 评测 / 数据集组件；不是工作台执行基座 | 11,244 / 7 | 官方文档定位为 AI Observability and Evaluation；tracing、LLM evals、datasets/experiments、OpenInference integration 均有独立入口。[[E:55995bbebf4e8fe70529133f](https://github.com/Arize-ai/phoenix/blob/37916d7351002222fc5a3ee8560528834da85134/.agents/skills/README.md)] [[E:924f4c39a7e0672325962eb9](https://github.com/Arize-ai/phoenix/blob/37916d7351002222fc5a3ee8560528834da85134/.agents/skills/README.md)] [[Phoenix docs](https://arize.com/docs/phoenix)] | CLI 可 fetch traces、annotate spans/traces、inspect datasets、query GraphQL；OpenInference instrumentation 覆盖多个 Agent/LLM/Provider，适合跨 Harness 接入，但不能替代 Run 状态与重试。[[E:c17eea7fdf501af5d2e62231](https://github.com/Arize-ai/phoenix/blob/37916d7351002222fc5a3ee8560528834da85134/.agents/skills/README.md)] | ELv2；其 license 对分发、提供托管服务等有明确限制条件，商业/内部共享部署前必须做法务核查，不应按 MIT 组件处理。[[LICENSE](https://github.com/Arize-ai/phoenix/blob/37916d7351002222fc5a3ee8560528834da85134/LICENSE)] |
| [UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai/tree/fbee5b35c656f1c7653af3adf682172033ee0590) | 评测组件 / 专长执行器；不是生产工作台 | 未纳入 ledger；热度 unknown | 官方站点将其定义为 open-source framework for LLM evaluations，并提供 agents、datasets、solvers、scorers、custom scorers 等一手入口。[[Inspect AI](https://inspect.aisi.org.uk/)] [[Using agents](https://inspect.aisi.org.uk/agents.html)] [[Datasets](https://inspect.aisi.org.uk/datasets.html)] [[Scorers](https://inspect.aisi.org.uk/scorers.html)] | 可将 agent 作为被测对象，以 dataset/solver/scorer 运行离线评测；不证明其提供个人项目 sandbox、定时调度、Provider gateway、长期 Run replay。 | 官方 pinned LICENSE 为 MIT；由于 compiler gitlink 限制没有 sealed ledger，维护、所有权和热度不与其他候选横向量化。[[LICENSE](https://github.com/UKGovernmentBEIS/inspect_ai/blob/fbee5b35c656f1c7653af3adf682172033ee0590/LICENSE)] |
| [open-telemetry/semantic-conventions](https://github.com/open-telemetry/semantic-conventions/tree/755ed8741bcb97be98563edb1374d1eefff7ef71) | 观测规范 / 组合件；不是运行时 | 639 / 0 | 官方 README 说明 semantic conventions 为采集、生产和消费 telemetry data 提供共同属性语义；GenAI 页面已迁移到 GenAI semantic conventions repo。[[E:51edf5ca037ee9732f86fa28](https://github.com/open-telemetry/semantic-conventions/blob/755ed8741bcb97be98563edb1374d1eefff7ef71/README.md)] [[E:ddc482537329ea296aa02d62](https://github.com/open-telemetry/semantic-conventions/blob/755ed8741bcb97be98563edb1374d1eefff7ef71/README.md)] [[OTel GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/)] | 可作为跨 Harness/Provider 的事件属性共同语义；不提供 collector、storage、UI、replay 或 Agent loop。本次 ledger 的 `unknownCriteria` 明确保留 `execution_harness`，不能把规范误当执行基座。[[E:2cb8cef6026a19079f5a2006](https://github.com/open-telemetry/semantic-conventions/blob/755ed8741bcb97be98563edb1374d1eefff7ef71/docs/README.md)] | Apache-2.0；规范仓库的维护/版本治理与运行产品所有权分离，采用时仍需钉定 GenAI semconv 版本，避免属性漂移。[[LICENSE](https://github.com/open-telemetry/semantic-conventions/blob/755ed8741bcb97be98563edb1374d1eefff7ef71/LICENSE)] |
| [Aider-AI/aider](https://github.com/Aider-AI/aider/tree/5dc9490bb35f9729ef2c95d00a19ccd30c26339c) | 代码 Agent / 专长执行器 | 48,587 / 4 | 官方 README 定义为 terminal AI pair programming；证明 codebase map、Git 自动 commit/diff/undo、lint/test，以及连接 cloud/local/几乎任意 LLM。[[E:44aebc8c53289738294dd325](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/README.md)] [[E:8699b4479d1137d2ee96d5ba](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/README.md)] | CLI/脚本化、repo map、Git、lint/test 和多模型连接是清晰组合面；没有被一手资料证明的 unattended schedule、跨 Run event ledger、权限审批或 replay。[[E:2a18548c20c0706cc792621f](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/README.md)] [[Aider LLMs](https://aider.chat/docs/llms.html)] | Apache-2.0；维护主体集中于 Aider-AI，README 的 release history/leaderboards 不等于 API 稳定承诺，嵌入时需隔离 CLI 进程与升级影响。[[E:74f596b6f31619cdd67e311b](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/README.md)] [LICENSE](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/LICENSE.txt) |

## 3. 分层 findings

### 3.1 执行型 Harness

**OpenHands。** 一手 README 描述的是 Agent Canvas：self-hosted developer control center，可启动 coding agents 与 automations，连接 local/remote/cloud backends、webhook/schedule、Slack/GitHub 等；同一 commit 的仓库 AGENTS 又写明“only the agent-canvas frontend”。因此“OpenHands”必须拆成产品族/前端 repo/backend/automation backend 四个边界来研究；当前证据支持它是工作台控制面候选，不支持把 `OpenHands/OpenHands` repo 单独视为完整、可嵌入的 agent server。[[OpenHands README](https://github.com/OpenHands/OpenHands/blob/f26d734a848297d8dcf460b0bb739174e76511f0/README.md)] [[E:625319f43fbb2215e4f72e5b](https://github.com/OpenHands/OpenHands/blob/f26d734a848297d8dcf460b0bb739174e76511f0/AGENTS.md)] [[OpenHands automations](https://docs.openhands.dev/openhands/usage/agent-canvas/prebuilt-automations)]

**OpenCode。** 一手资料证明它是面向开发者的 coding agent，而非通用 scheduler：build/plan/general 三种 agent、provider、plugin、MCP/API 是明确表面；session durability、权限提示或持久化细节要进一步以 source/API contract 核查。它可进入“执行基座候选”层，但本 findings 不把它提升为最终主基座。[[OpenCode README](https://github.com/anomalyco/opencode/blob/dc4449df0d52199704ea4989a5a993ebbc605612/README.md)] [[OpenCode agents](https://opencode.ai/docs/agents)] [[OpenCode plugins](https://opencode.ai/docs/plugins)]

**Goose。** 一手 README 同时证明 general-purpose local agent、desktop/CLI/API、code/workflows/everything、15+ providers 和 MCP extensions；源码维护说明还明确记录 agent-loop 从 legacy 到 state machine 的迁移。它的能力覆盖比专门代码 Agent 宽，但迁移中的双路径是集成时必须锁定的未知/风险，不把“支持 15+ providers”推断为统一能力契约。[[Goose README](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/README.md)] [[E:d754c39f74327f8e5b07ac65](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/AGENTS.md)]

### 3.2 代码 Agent / 专长执行器

**SWE-agent 与 Aider。** SWE-agent 的官方边界是 LM 使用 tools 修复真实 GitHub repositories、漏洞或自定义任务，并有 SWE-bench、batch 和 trajectories；Aider 的边界是 terminal pair programming，具备 repo map、Git、lint/test 和多模型。二者都能覆盖“理解—修改—测试—Git”的代码闭环，但本轮一手资料没有证明它们拥有个人工作台需要的 scheduler、跨任务生命周期、权限总账、可回放事件模型或 Provider gateway。因此记录为专长执行器，而非完整工作台。[[E:2163da933db2962c6f331d82](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/README.md)] [[E:44aebc8c53289738294dd325](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/README.md)]

### 3.3 通用编排 / 调度

**LangGraph。** 官方定位是 low-level orchestration framework；durable execution、interrupt/human-in-the-loop、memory、long-running stateful agent 均被证明，适合作为工作台内部 Run graph/state 子系统。它不应被误选成“带代码工具、项目权限、Provider 路由和 UI 的现成 Harness”。[[LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)] [[LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)] [[E:6bde8bfff41ffe22b1462ba6](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/README.md)]

**Temporal。** 官方 Workflow docs 明确把 Event History replay 作为恢复机制；Schedule 独立于 Workflow Execution，Retry Policy 声明式控制失败重试。它能覆盖“长流程、定时、重试、恢复、事件历史”这条横切线，但不覆盖 Agent loop、代码编辑、模型路由或工作台交互；这是强组合件而不是代码 Agent。[[Temporal workflows](https://docs.temporal.io/workflows)] [[Temporal schedules](https://docs.temporal.io/schedule)] [[Temporal retry policies](https://docs.temporal.io/encyclopedia/retry-policies)]

### 3.4 Provider 网关

**LiteLLM。** 官方 architecture 把 gateway/proxy 与 SDK 分开，明确支持 auth、rate limits、budgets、routing、fallback、provider transformations、streaming、cost/logging。它能集中 Provider 适配、限额、故障转移与成本信号；但不应把这些能力扩大为 Agent Run、工具权限、项目 sandbox 或 replay。enterprise 目录独立许可证是所有权/升级审计点。[[E:7eefb0cb2e7f848c67986cfc](https://github.com/BerriAI/litellm/blob/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee/ARCHITECTURE.md)] [[E:736a66227ecead287f93fe6b](https://github.com/BerriAI/litellm/blob/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee/ARCHITECTURE.md)] [[LiteLLM proxy](https://docs.litellm.ai/docs/simple_proxy)]

### 3.5 工作流 / 重试组件与观测的边界

Temporal 的 retry/replay 是执行可靠性；Langfuse、Phoenix、OpenTelemetry 是记录/诊断/语义；三者不能互相替代。尤其是 Event History replay（重建 workflow 状态）不等于完整 Agent replay：模型返回、工具副作用、文件系统、网络、时间和 Provider 路由仍需要工作台定义 snapshot、替身或不可重放标记。这个区分来自 Temporal 对 activity/result/event history 的官方 replay 描述，以及观测项目对 trace/span/dataset/eval 的官方边界。[[Temporal workflows](https://docs.temporal.io/workflows)] [[Langfuse tracing](https://langfuse.com/docs/tracing)] [[Phoenix docs](https://arize.com/docs/phoenix)] [[OTel GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/)]

### 3.6 评测 / 观测组件

**Langfuse。** 官方资料覆盖 LLM engineering、monitoring、evaluating、debugging、trace/span/observation、self-host；因此是 Agent Run 观测/评测候选，不是执行基座。其 MIT core 与 `ee/` 许可证分界必须作为部署审计输入。[[E:cf300c55dfd86e0dd8a6fd65](https://github.com/langfuse/langfuse/blob/f6e56cbb6c6c001805e90c263efca995a3fd33ba/.agents/AGENTS.md)] [[Langfuse tracing](https://langfuse.com/docs/tracing)] [[Langfuse self-hosting](https://langfuse.com/docs/deployment/self-host)]

**Phoenix。** 官方资料证明 tracing、LLM evaluation、datasets/experiments、GraphQL/CLI 与 OpenInference integration；它可作为跨多个 Harness/Provider 的观测与评测组件，但不是 scheduler、权限系统或 durable Run runtime。ELv2 是实质性采用风险，不能按宽松 MIT 依赖处理。[[E:924f4c39a7e0672325962eb9](https://github.com/Arize-ai/phoenix/blob/37916d7351002222fc5a3ee8560528834da85134/.agents/skills/README.md)] [[Phoenix docs](https://arize.com/docs/phoenix)] [[Phoenix license](https://github.com/Arize-ai/phoenix/blob/37916d7351002222fc5a3ee8560528834da85134/LICENSE)]

**Inspect AI。** 官方站点的一级概念是 evaluations、datasets、solvers、scorers 和 agents，说明它适合离线或任务式评测 harness，而不是生产工作台。它进入“评测组件”而不是主执行基座；由于未进入 sealed ledger，热度和维护不能与其他候选横比。[[Inspect AI](https://inspect.aisi.org.uk/)] [[Using agents](https://inspect.aisi.org.uk/agents.html)] [[Scorers](https://inspect.aisi.org.uk/scorers.html)]

**OpenTelemetry Semantic Conventions。** 官方定义是共同 telemetry attributes 的语义，且 GenAI 规范页面已迁移；它能提供事件/trace 字段的跨实现词汇，但不是 collector、storage、UI 或 replay runtime。sealed ledger 的唯一 `unknownCriteria` 正是 `open-telemetry/semantic-conventions × execution_harness`；该 unknown 必须保留。[[E:ddc482537329ea296aa02d62](https://github.com/open-telemetry/semantic-conventions/blob/755ed8741bcb97be98563edb1374d1eefff7ef71/README.md)] [[OTel GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/)]

## 4. 容易误选与明确不匹配

这些不是对项目质量的否定，而是“放错层”的风险：

1. **把 `OpenHands/OpenHands` repo 当完整 Harness。** pinned AGENTS 明确它是 frontend；产品 README/文档描述的 backend、automation backend、ACP agent 和 cloud/VM backend 需要分别确认所有权、接口和部署边界。
2. **把 LangGraph 当现成个人工作台。** 它是 low-level orchestration；没有本轮证据证明它自带项目文件权限、Shell/Git 工具策略、Provider gateway、计划任务 UI 或全局 Run ledger。
3. **把 Temporal 当 Agent。** 它提供 Workflow execution/replay/schedule/retry；没有代码 Agent 的 LM/tool loop、repo context 或模型 Provider。
4. **把 LiteLLM 当 Harness。** 它解决 LLM gateway/router/cost/limit/logging；没有被证明拥有 Agent state、工具审批、项目 sandbox 或任务回放。
5. **把 Langfuse/Phoenix/OTel/Inspect AI 当执行内核。** 它们分别解决 trace/eval/semantic convention/evaluation；不能自动拥有工具副作用、权限状态、调度和恢复责任。
6. **把 SWE-agent/Aider 当通用自动化平台。** 它们的一手边界强在代码修改、测试、Git、轨迹或多模型接入；scheduler、无人值守权限、跨项目 Run 生命周期和统一观测未被证明。

## 5. 分开的风险账本

### 热度

只有 10 个 ledger 候选有可复核的 stars/topicMatch：OpenCode 202,413；OpenHands 85,583；LiteLLM 57,554；Goose 53,669；Aider 48,587；LangGraph 40,685；Langfuse 33,912；SWE-agent 20,171；Phoenix 11,244；OpenTelemetry Semantic Conventions 639。它们是同一观察时点的 GitHub snapshot，不是质量、维护能力或适配度评分。Temporal 与 Inspect AI 的热度保持 unknown，不用本次未封存 API 查询结果补齐。

### 能力覆盖

当前一手资料证明的覆盖形状是：

- 执行循环 / 开发交互：OpenHands 产品族、OpenCode、Goose；
- 代码闭环：SWE-agent、Aider，另有 OpenHands/OpenCode/Goose 的产品级证据；
- stateful durable orchestration：LangGraph；
- schedule/retry/replay：Temporal；
- Provider routing/gateway/cost：LiteLLM，另有各 Harness 自己的 provider surfaces；
- trace/eval/dataset/semantic vocabulary：Langfuse、Phoenix、Inspect AI、OpenTelemetry。

这是一张 coverage map，不是把各项能力相加后的“全能候选”。没有证明的 scheduler、replay、审批、sandbox、凭证控制和统一事件契约仍是未知或工作台自有责任。

### 可组合性

组合表面被一手资料证明的主要是：MCP/ACP/extension/plugin、Provider API、SDK/API、workflow graph/checkpoint、Temporal Workflow/Activity/Schedule、LiteLLM gateway、OTel/OpenInference instrumentation、Langfuse/Phoenix/Inspect 的 trace/eval/dataset 接口。组合成本的未知部分包括：事件字段的共同最小契约、模型/工具调用的 replay 语义、文件和网络 snapshot、权限审批与副作用幂等、跨项目的 Run identity、版本升级兼容。

### 许可证 / 维护 / 所有权

- MIT：OpenHands、SWE-agent、OpenCode、LangGraph、Temporal、Inspect AI；Apache-2.0：Goose、Aider、OpenTelemetry；这些是 pinned LICENSE 的文本事实，不等于没有供应链或维护风险。
- LiteLLM 与 Langfuse 都有 enterprise/ee 目录的许可证分界；必须按目录核查，而不是只读取仓库 API 的单一 SPDX 字段。
- Phoenix 为 Elastic License 2.0，使用、分发、托管服务和衍生工作的法律边界需要单独审计。
- 本次 collection 的 pinned revision 证明了一个可复核快照，但不自动证明 release cadence、响应 SLA、治理独立性、兼容承诺或长期所有权；这些在 findings 中保持为风险/unknown。

## 6. 明确未知与下一轮验证门槛

以下未知不能从本次研究推断为 negative capability：

- OpenHands backend/automation backend 的独立仓库、API/版本、沙箱、凭证与 replay 责任边界；
- OpenCode/Goose/SWE-agent/Aider 在无人值守定时运行、并发、暂停恢复、幂等和危险副作用审批上的正式语义；
- LangGraph 与 Temporal 组合时，Agent tool side effect、模型 response、时间/网络和文件系统如何实现确定性或近似回放；
- LiteLLM 的统一工具调用/流式/结构化输出/成本/故障切换契约在每个目标 Provider 上的共同最小集；
- Langfuse/Phoenix/OTel/Inspect 如何共同记录一次 Agent Run 的 prompt、tool call、artifact、权限决定、环境快照和脱敏字段；
- 所有候选的长期维护主体、治理变更、破坏性升级策略、SBOM/供应链安全和分叉成本；
- Temporal、Inspect AI 因 compiler gitlink 限制未进入 sealed ledger，故其 GitHub stars/topicMatch/ledger Evidence 仍 unknown。

下一轮应以小型验证集实测，而不是依据本表作推荐：代码项目闭环、定时失败重试、人工审批、Provider 故障切换、工具副作用回放、跨 Harness trace/eval、许可证扫描和升级演练。W3 本身到此只完成发现、筛选和分层，不产生主基座或组合路线的最终决定。

## 7. 证据与产物索引

### sealed collection

- [brief/request v6](./w3-open-source-alternatives.v6.request.json)
- [sealed ledger response v6](./w3-open-source-alternatives.v6.ledger-response.json)
- [collection status v6](./w3-open-source-alternatives.v6.collection-status.json)
- compiler：`zj-research-cli/v1`，artifact lock 指向 `ZHarness@9172aa0674bf7a7cabcd47383407e0d5068de8f2`

### 官方一手资料入口

- OpenHands：[pinned README](https://github.com/OpenHands/OpenHands/blob/f26d734a848297d8dcf460b0bb739174e76511f0/README.md)、[Agent Canvas docs](https://docs.openhands.dev/openhands/usage/agent-canvas)、[automations](https://docs.openhands.dev/openhands/usage/agent-canvas/prebuilt-automations)
- SWE-agent：[pinned README](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/README.md)、[official docs](https://swe-agent.com/latest/)、[trajectories](https://swe-agent.com/latest/usage/trajectories/)
- OpenCode：[pinned README](https://github.com/anomalyco/opencode/blob/dc4449df0d52199704ea4989a5a993ebbc605612/README.md)、[docs](https://opencode.ai/docs/)、[providers](https://opencode.ai/docs/providers/)、[agents](https://opencode.ai/docs/agents)
- Goose：[pinned README](https://github.com/aaif-goose/goose/blob/8ae4e4ba02836529790f47109b8785e8b42843a7/README.md)、[official docs](https://goose-docs.ai/docs/)、[governance](https://github.com/aaif-goose/goose/blob/main/GOVERNANCE.md)
- LangGraph：[pinned README](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/README.md)、[overview](https://docs.langchain.com/oss/python/langgraph/overview)、[durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- Temporal：[workflows](https://docs.temporal.io/workflows)、[schedules](https://docs.temporal.io/schedule)、[retry policies](https://docs.temporal.io/encyclopedia/retry-policies)、[manual pinned ref](https://github.com/temporalio/temporal/tree/c044bf16b1cc47a4db80669a987484dba6145331)
- LiteLLM：[pinned architecture](https://github.com/BerriAI/litellm/blob/d44d281d1d873fe3bf813e931bed27a8ac3ae7ee/ARCHITECTURE.md)、[proxy docs](https://docs.litellm.ai/docs/simple_proxy)、[routing](https://docs.litellm.ai/docs/routing)
- Langfuse：[pinned agent guidance](https://github.com/langfuse/langfuse/blob/f6e56cbb6c6c001805e90c263efca995a3fd33ba/.agents/AGENTS.md)、[tracing](https://langfuse.com/docs/tracing)、[self-hosting](https://langfuse.com/docs/deployment/self-host)
- Phoenix：[pinned skills index](https://github.com/Arize-ai/phoenix/blob/37916d7351002222fc5a3ee8560528834da85134/.agents/skills/README.md)、[official docs](https://arize.com/docs/phoenix)、[OpenInference](https://github.com/Arize-ai/openinference)
- Inspect AI：[official docs](https://inspect.aisi.org.uk/)、[agents](https://inspect.aisi.org.uk/agents.html)、[datasets](https://inspect.aisi.org.uk/datasets.html)、[scorers](https://inspect.aisi.org.uk/scorers.html)、[manual pinned ref](https://github.com/UKGovernmentBEIS/inspect_ai/tree/fbee5b35c656f1c7653af3adf682172033ee0590)
- OpenTelemetry：[pinned README](https://github.com/open-telemetry/semantic-conventions/blob/755ed8741bcb97be98563edb1374d1eefff7ef71/README.md)、[GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- Aider：[pinned README](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/README.md)、[LLMs](https://aider.chat/docs/llms.html)、[Git](https://aider.chat/docs/git.html)、[lint/test](https://aider.chat/docs/usage/lint-test.html)

## 8. 结论边界

本文件回答“哪些项目值得进入同一决策矩阵、各自位于哪一层、哪些容易误选、证据和未知是什么”。它没有在候选之间作最终推荐，也没有修改 `docs/plans/personal-workbench-wayfinder.md`。
