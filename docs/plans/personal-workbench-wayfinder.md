# 个人工作台：Wayfinder 决策地图

状态：🧭 研究完成，W1/W5 已确认，W6-0.1 fixture/阈值已冻结，C1–C7 fixture 证据完成，条件性交接 W7
载体：local-markdown tracker（本文件是唯一地图与票据载体）  
创建日期：2026-08-30  
当前基线：仓库只有 `README.md`，尚无实现、领域词汇、ADR 或既有架构约束。

## Destination

先对现有开源 Agent Harness、代码 Agent、编排/调度、Provider 和观测/评测工具做证据化能力盘点，再决定 ZWorkbench 应采用现成项目、以一个项目为主基座加薄层、多个项目组合、分叉改造，还是自建某个缺失的深模块。最终产出应包含产品边界、信任边界、采用姿态、候选基座、组合边界和验证门槛，足以交给后续 roadmap/spec/implementation 阶段。  
本轮只找路、定决策和边界，不实现工作台本身；默认不从零重写已有能力。

## Notes

- 领域：个人任务执行、Agent Harness、代码开发、自动化/定时任务、LLM Provider、可观测性、事件记录与回放、评测和调试。
- 研究对象由用户点名：DeepSeek Harness、Pi Agent Harness、Codex Harness；名称对应的确切开源仓库、维护主体和项目边界必须先由一手资料核实，不对名称做未经验证的假设。
- 必须优先使用官方文档、官方仓库源码、发布记录、协议/规范和一手 API 资料；stars 等热度信息与能力事实分开记录。
- 研究结果应保留可复核来源、明确未知项和版本/提交锚点；研究票据不负责作最终推荐。
- 研究的第一产物不是“哪个项目最好”，而是能力地图：已有能力、复用方式、集成接口、缺口、替代成本和必须由 ZWorkbench 自有的部分。
- 采用顺序：能力盘点 → 场景/硬门槛 → 采用姿态（单基座/组合/分叉/自建）→ 试点验证 → 才进入实现设计。
- 辅助决策方法已加入 W6：用 ATAM 识别质量属性场景、架构风险、敏感点和权衡点；用 CBAM 量化场景收益、风险降低、集成/运维/迁移成本和锁定成本；用自动化与持续评估把结论变成可重复的验证门禁和上游漂移监测。
- 用户已给出的硬目标：完成各种任务；自动任务和定时任务；运行/集成个人开发项目；可观测、可回放，用于评测/调试/排障；多家 LLM Provider；尽可能优秀的代码开发能力。
- 术语暂定：`工作台` 是面向单个用户的统一入口；`Harness` 是负责 Agent 运行循环、工具/项目接入、状态与安全边界的执行基座；`Provider` 是模型/推理服务适配方；`回放` 是基于已记录输入、工具调用、输出和环境信息重建一次运行，而不是只查看日志。

## Decisions so far

- 用户目标已确定：工作台必须同时覆盖通用任务、自动化/定时、个人项目集成、可观测性/回放/评测/调试、多 Provider 和高质量代码开发。
- 本阶段边界已确定：先产出决策和边界，不直接实现。
- 默认载体已确定：使用本地 Markdown 地图，不依赖外部 issue tracker。
- 用户补充的方向已确定：先调研现有开源项目及其工具/能力，再决定是以一个项目为主还是多个项目组合；不能预设从一行代码开始自建全部能力。
- W4 已解析出一个重要边界：现有观测/评测系统普遍能复用为记录、查询、实验和评分后端，但不能自动提供工作台所需的执行回放、副作用隔离、环境快照和 artifact lock；这些必须进入 ZWorkbench 的自有边界。
- W3 已完成能力分层：OpenHands/OpenCode/Goose 属于执行型 Harness 候选；SWE-agent/Aider 更适合作为代码专长执行器；LangGraph/Temporal/LiteLLM/Langfuse/Phoenix/Inspect AI/OpenTelemetry 分别位于编排、调度、Provider、观测/评测和规范层，不能把这些层简单相加成一个“全能基座”。
- W2 已完成对象核实：DeepSeek 对应 `deepseek-ai/deepseek-harness`，Pi 对应 `earendil-works/pi`，Codex Harness 暂按 `openai/codex` 的 OSS CLI/app-server 映射；三者能力形状明显不同，尤其是 DeepSeek 仍为 developer preview、Pi 不内建权限/沙箱、Codex 的通用调度仍未证实。
- W6 已转入 roadmap-driven 跟踪：评估矩阵、ATAM、CBAM、持续评估和 W7 交接节点记录在 [`personal-workbench-roadmap.json`](./personal-workbench-roadmap.json)，其 Markdown 视图为 [`personal-workbench-roadmap.md`](./personal-workbench-roadmap.md)。Wayfinder 仍保存决策地图，roadmap JSON 保存节点/决策历史。
- W6 已完成 C1–C7 的 `W6-0.1` fixture 与阈值规格：共享隔离项目、假 Provider、负向权限动作、故障注入、recorded/simulated replay 和单人运维演练；关键安全、副作用、事件完整和回放边界采用零容忍/100%门槛，其余阈值作为首轮冻结基线，结果后才可由 ATAM/CBAM 校准。
- W6-0.1 已获 Human 确认并冻结为首轮基线：C1/C5 样本量与通过标准、安全/回放零容忍、C3/C4 恢复语义、个人/小团队运维门槛、`pass-with-composition` 判定和首轮阈值变更纪律均已确定。C1–C7 的候选无关 fixture 证据已形成；候选 C2–C7、C7 真人运维工时和 G0/G7 仍为 unknown，W6 不签最终采用，只条件性交接 W7。

## Not yet specified

- 首批任务已有首轮 C1 实测和运行时长基线：DeepSeek Harness、Codex Harness 在两个 fake Provider 上均为 5/5；C2–C6 已形成候选无关 fixture 合同证据，C7 机器流程 12/12 pass，但候选 adapter 与真人运维成本仍待验证。
- “适合个人开发者或小团队”的首轮基线已固化：安装 ≤90 分钟，升级/备份恢复/预制故障排查各 ≤30 分钟，无需额外专家，MVP 常驻人工维护服务 ≤3 个；参考 fixture 维护服务 2 个，真人时间与候选成本仍待验证。
- 已确定最小权限、项目级沙箱、危险副作用审批和无人值守限制；凭证、网络、文件系统、进程、数据留存/外发和部署的细化策略仍待后续票据。
- 本地优先、远程执行、云端服务和混合部署的边界；个人数据、源码、运行轨迹和模型请求的留存/外发策略。
- 任务、计划任务、Agent Run、工具调用、项目、Provider、评测样本、回放记录之间的领域关系和生命周期。
- 候选 Harness 是主基座、可插拔执行器，还是仅借鉴其代码/协议；是否允许“编排层 + 多个专长执行器”的组合。
- ZWorkbench 的采用姿态：直接采用、单一主基座加薄层、多个项目拼装、分叉改造，或仅自建明确缺失的深模块。
- 可观测性、确定性重放、时间/网络/模型替身、评测集与回归门禁的最低可用定义。
- Provider 抽象需要统一到什么程度，以及模型特性、工具调用、上下文、流式输出和成本/限额信息的共同最小接口。
- 调度的语义（时区、错过触发、重试、并发、幂等、暂停/恢复、人工接管）和故障后的责任归属。
- 与个人项目的集成表面（目录、Git、依赖、测试、构建、部署、IDE/终端、MCP/API 等）及兼容性承诺。
- 许可证、维护活跃度、升级/分叉成本、供应链风险和候选项目的长期所有权。
- 形成最终推荐所需的基准任务、评分权重、硬门槛、试点范围和停止条件。

## Out of scope

- 本轮不写工作台代码、不搭建运行环境、不接入真实账号、不迁移个人项目、不创建定时任务。
- 不把“支持多 Provider”扩展为自研模型、训练/微调模型或覆盖所有模型供应商的商业产品。
- 不建设面向多租户、团队协作、计费、企业合规或高可用 SaaS 的完整平台；除非后续重新定义 Destination。
- 不替代 IDE、终端、Git 托管平台或 CI/CD 平台；只研究工作台与它们的集成边界。
- 不以 stars、营销页面或未经提交锚定的二手文章作为能力结论。

## Frontier

当前 frontier 是所有未认领、无未完成阻塞项的开放票据：

- [W7 — 选择采用姿态：现成项目、单一基座、组合拼装、分叉还是自建薄层 [G]](#w7--选择采用姿态现成项目单一基座组合拼装分叉还是自建薄层-g)

W8–W9 已写成清晰的后续问题，但依赖 W7 的采用姿态，暂不冒充当前 frontier。

---

## W1 — 定义 Destination 与首批成功标准 [G]

状态：✅ 已完成 · HITL · 用户确认

### Question

对于第一阶段个人工作台，哪些任务类型必须在首个可用版本中做好，哪些只需保留扩展位？请在以下维度上定出“够用”的成功标准：

1. 通用任务、代码任务、自动/定时任务三类的优先级；
2. 单次任务与长流程任务的最长可接受运行时间；
3. 代码开发能力中必须具备的闭环（理解、修改、测试、审查、提交、部署中的哪些环节）；
4. 对失败可见、可解释、可恢复和可回放分别达到什么程度。

推荐默认：第一阶段以“个人项目上的可审计代码任务 + 少量可恢复自动化”为主，通用任务作为同一运行内核的第二入口；暂不承诺覆盖所有任务类型。

### Resolution

用户确认默认方案：第一阶段以个人项目上的可审计代码任务为主，辅以少量可恢复自动化；通用任务作为次要入口。后续需要在 W6 中把代码闭环、最长运行时间、失败恢复和回放等级转成可执行的硬门槛与评分项。

---

## W2 — 核实 DeepSeek Harness、Pi Agent Harness、Codex Harness 的对象身份与能力证据 [R]

状态：✅ 已完成 · AFK research · Poincare

### Question

用户点名的三个名称分别对应哪些官方/一手开源项目、仓库、版本和维护主体？对每个候选，以同一套标准核实并记录：

- 运行循环、工具系统、项目/工作区隔离、上下文与状态持久化；
- 代码编辑、测试、命令执行、Git 和人工审批能力；
- MCP/API/插件等扩展面，以及 Provider 抽象的实际边界；
- 自动化/定时任务是否是内建能力、可组合能力，还是缺失；
- 轨迹、事件、日志、回放、评测和调试能力的实际实现；
- 安全模型、沙箱、网络/凭证控制、失败恢复和并发；
- 许可证、最近维护、发布/提交锚点、已知未知项和集成成本。

特别要求：若名称不存在唯一对应项目，必须把歧义作为结果保留，并列出需要用户确认的候选映射；不能用相近项目替代原对象而不说明。

研究交付物必须包含能力清单，并对每项标记“可直接复用 / 需适配 / 需自有 / 未知”，同时记录对应集成面和证据强度。

⛔ blocked by：无

### Resolution

三个名称的纳入对象分别核实为 `deepseek-ai/deepseek-harness`、`earendil-works/pi` 和暂按 `openai/codex` OSS CLI/app-server。DeepSeek 的覆盖面最完整但版本仍是 developer preview；Pi 的运行循环、Provider、session/evals 和扩展面清晰，但明确不内建权限/沙箱且没有被证实的通用 scheduler；Codex 的 app-server、项目工具、Provider 配置、沙箱和 rollout trace 较强，但面向用户的通用 cron/schedule 仍未知。三者的 session/operation/rollout replay 都不能自动承诺外部副作用 exactly-once。

证据与完整 findings：[W2 — 点名 Harness 研究](./research/w2-named-harnesses.md)；采集阻塞状态：[W2 — collection status](./research/w2-named-harnesses.collection-status.json)

---

## W3 — 发现并筛选必要的开源替代方案与组合件 [R]

状态：✅ 已完成 · AFK research · Noether

### Question

在点名候选之外，哪些开源项目值得进入同一决策矩阵？按“执行型 Harness、代码 Agent、通用编排/调度、Provider 网关、工作流/重试、评测/观测组件”分层发现，至少核实 OpenHands、SWE-agent、OpenCode、Goose、LangGraph、Temporal/同类工作流组件是否与目标重叠；仅在一手资料证明相关时纳入更多候选。

输出应区分：

- 可作为主执行基座的项目；
- 只能作为专长执行器或子系统的项目；
- 与本目标不匹配但容易被误选的项目；
- 热度、功能覆盖、可组合性和所有权风险四类证据。

研究交付物必须说明每个候选能被 ZWorkbench 复用的具体模块、复用前提、与其他候选拼装时的重叠状态，以及不应重复自建的能力。

⛔ blocked by：无

### Resolution

研究将候选拆成不同层，而不是给出一个虚假的全能排名：OpenHands/OpenCode/Goose 是执行型 Harness 候选；SWE-agent/Aider 是代码专长执行器；LangGraph 是状态化编排框架；Temporal 提供 durable workflow、schedule、retry、event-history replay；LiteLLM 是 Provider gateway；Langfuse/Phoenix/Inspect AI/OpenTelemetry 分别覆盖观测、评测和语义规范。当前证据支持“先选一个主执行候选，再按明确缺口接入组合件”，不支持一开始把多个 Harness 拼成统一平台。

证据与完整 findings：[W3 — 开源替代方案与组合件研究](./research/w3-open-source-alternatives.md)；提交级 sealed ledger：[W3 — evidence ledger](./research/w3-open-source-alternatives.v6.ledger-response.json)

---

## W4 — 研究可观测性、回放与评测基础设施的可行边界 [R]

状态：✅ 已完成 · AFK research · Avicenna

### Question

哪些开源方案能为 Agent Run 提供可检索的结构化事件、工具调用和模型交互记录、trace/span 关联、脱敏、成本/延迟指标、失败诊断、确定性或近似回放，以及离线/在线评测？核实 Langfuse、Arize Phoenix、AgentOps、OpenTelemetry GenAI 语义约定及必要的替代方案，重点回答：

- 它们记录什么，不能记录什么；
- 回放依赖哪些环境快照、模型替身、网络/时间控制；
- 是否能跨多个 Harness/Provider 保持统一事件模型；
- 自托管、许可证、数据敏感性和升级成本；
- 哪些能力必须由工作台自己拥有，不能外包给观测系统。

研究交付物必须给出“观测/记录/回放/评测”的能力边界，以及跨候选 Harness 统一事件模型时应由 ZWorkbench 自有的最小内核。

⛔ blocked by：无

### Resolution

现有方案普遍覆盖观测/记录，并可支持数据集、实验或评分，但“session replay”、trace 导入和实验 rerun 都不能直接等同于确定性执行回放。OpenTelemetry GenAI 约定适合做跨 Harness/Provider 的低层事件词汇，却不是完整的事件溯源或回放协议。ZWorkbench 至少必须自有 canonical event ledger、脱敏策略、Replay contract、副作用/状态快照、运行 artifact lock、评测编排与跨后端语义降级；研究中的 GitHub sealed ledger 因匿名 API 配额阻塞，stars、topic match、HEAD/commit 级比较仍未知。

证据与完整 findings：[W4 — 可观测性、回放与评测研究](./research/w4-observability-replay-evaluation.md)

---

## W5 — 定义自动化权限、数据和故障信任边界 [G]

状态：✅ 已完成 · HITL · 用户确认

### Question

个人工作台在本地执行、远程执行和混合执行之间，允许 Agent 触碰哪些资源？请定出至少以下规则：

- 文件系统、Shell、网络、浏览器、凭证、Git push、发布/部署的默认权限；
- 哪些工具调用需逐次审批，哪些可按项目/任务授予能力；
- 计划任务无人值守时能否自动写代码、运行命令、发送消息或部署；
- 数据和轨迹的保留、脱敏、加密、删除及向 Provider 外发边界；
- 超时、重试、重复触发、部分成功、模型异常和人工接管的责任与状态。

推荐默认：本地优先、项目级沙箱、最小权限、危险副作用默认审批；无人值守任务只能执行可回滚且幂等的动作，部署和外部发送保持人工门槛。

⛔ blocked by：无

### Resolution

用户确认默认方案：本地优先、项目级沙箱、最小权限；危险副作用默认审批；无人值守任务仅允许可回滚且幂等的动作；部署、Git push 和外部消息发送保持人工门槛。凭证/网络/数据留存与外发、超时重试和部分成功的具体状态机仍需在后续票据中细化。

---

## W6 — 统一评估矩阵与试点门槛 [G]

状态：✅ Codex · HITL · W6-0.1 fixture 证据完成；不签最终采用，条件性交接 W7

### Question

在 W1–W5 的事实和边界之上，如何为所有候选定义同一套评分、硬门槛和最小验证集，并确保方案适合个人开发者或小团队？需要决定能力权重（代码闭环、任务覆盖、自动化、Provider、观测/回放、安全、维护/许可证、集成成本、运维负担）、证据等级、必须实测的场景和不可接受的失败。

“适合个人开发者或小团队”是硬约束，不是通过其他能力加分可以抵消的软指标。至少检查：

- 安装、升级、备份、恢复和排障是否能由一个主要维护者完成；
- 是否需要持续运行的复杂分布式基础设施，及其成本是否与个人收益相称；
- 本地优先、单机/小规模部署、离线或低依赖模式是否可行；
- 失败、权限、数据删除、版本回滚和供应链问题是否有清晰责任边界；
- 是否有可用的 CLI/API、文档、测试和迁移路径，避免只能依赖内部专家；
- 许可证、商业版边界、关键维护者集中度和分叉成本是否可接受。

辅助决策策略：

1. **ATAM。** 以首批代码任务、可恢复定时任务、审批拦截、双 Provider、记录/回放和故障恢复为质量属性场景，逐个记录刺激、环境、响应、响应度量；识别风险、非风险、敏感点和权衡点。至少覆盖代码成功率、安全性、可恢复性/回放、可观测性、Provider 可移植性、可操作性、成本和可维护性，不用单一综合分隐藏架构冲突。
2. **CBAM。** 对每个候选或新增组合件记录场景收益、风险降低、一次性集成成本、持续运行成本、升级/迁移成本、学习与排障成本、锁定成本和退出成本；先过硬门槛，再用“增量组件带来的收益是否值得增量复杂度”决定是否引入 Temporal、LiteLLM、观测/评测后端或第二个 Harness。
3. **自动化 + 持续评估。** 建立版本化、可重复、无真实副作用的最小评测集；在候选版本、配置、Provider、Prompt/Tool schema 或工作台边界变化时自动运行，并持续记录任务成功率、人工介入率、未授权动作拦截率、恢复率、事件完整率、回放一致性、延迟、Token/基础设施成本和维护工时。上游升级、Provider 漂移或关键指标越过阈值时暂停升级或重新进入 W6/W7，而不是沿用旧结论。

推荐默认：先用 ATAM 找出不可接受的风险和组合冲突；用 CBAM 判断每个外加组件是否值得其复杂度；再以自动化持续评估验证一个主 Harness 的试点。只有当第二个 Harness 或自建模块在明确场景上带来超过其运维/集成成本的可测量收益，才允许升级为组合路线。

推荐默认：分层比较，不把执行 Harness 与组合件硬排在同一榜单；执行 Harness 首轮纳入 DeepSeek、Pi、Codex、OpenCode、Goose，Temporal/LangGraph、LiteLLM、Langfuse/Phoenix、Inspect AI/OpenTelemetry 单独作为编排、Provider、观测和评测组合件评估。

推荐的最低验证集：真实个人项目上的“理解—修改—测试—解释 diff”代码闭环；安全任务的审批拦截；可回滚且幂等的定时任务；中断后的恢复/重试；两个 Provider 上的同一任务；完整事件记录与 recorded/simulated replay；跨候选的评测样本复跑。安全违规、未授权副作用、无法恢复的状态丢失、关键事件缺失和许可证不满足均为硬失败，不用平均分掩盖。

推荐的评分权重（仅用于通过硬门槛后的排序）：代码闭环 25%、运行状态/恢复 15%、自动化/调度 10%、观测/回放/评测 15%、Provider 可移植性 10%、个人/小团队可操作性 15%、集成/维护/许可证 10%。每项能力同时记录“官方证据 / 实测通过 / 实测失败 / 未知”，不把未验证当作负分；ATAM/CBAM 的风险与成本结论单独呈现，不被平均分抹平。

跟踪路线图：[W6 roadmap — 评估矩阵与持续验证](./personal-workbench-roadmap.md)；评估资产：[评估矩阵](./w6-evaluation-matrix.md)、[ATAM 模板](./w6-atam-template.md)、[CBAM 模板](./w6-cbam-template.md)、[持续评估协议](./w6-continuous-evaluation.md)。

⛔ blocked by：无（W1、W2、W3、W4、W5 已完成）

### Resolution

Human 已全部同意推荐阈值。`W6-0.1` 作为首轮冻结基线：C1/C5 的样本量与成功标准、安全与回放采用零容忍门槛，C3/C4 以幂等和安全终止定义恢复，C7 采用单人运维时间/服务数量门槛；允许 `pass-with-composition`，但必须验证组合整体并经 CBAM 证明增量复杂度可接受。首轮执行期间不得因候选表现临时改阈值；首轮结束后才可基于证据提出新版本。

评估规格：[W6 C1–C7 Fixture 与阈值](./w6-fixtures-and-thresholds.md)；首轮结果：[W6-0.1 首轮候选基线](./w6-baseline-candidate-findings.md)；持续评估：[W6 自动化与持续评估协议](./w6-continuous-evaluation.md)。

W6–W7 交接结论：C2–C6 fixture contract 已通过，C7 fixture 为 12/12 machine
process pass，但真人运维计时为 `0/12`，五个候选的关键 C2–C7 仍为 `unknown`。
因此不签署最终采用、不进入 ZWorkbench 产品实现；W7 采用“一个主 Harness + 必要
薄层”作为待验证姿态，先绑定 DeepSeek Harness 或 Codex Harness 的固定版本，
补齐候选 adapter、真人 C7 runbook、许可证/升级/回滚/退出证据，再决定采用、
组合、替换或停止。交接包：[W7 采用姿态交接包](./w7-adoption-posture-handoff.md)。

---

## W7 — 选择采用姿态：现成项目、单一基座、组合拼装、分叉还是自建薄层 [G]

状态：⬜ OPEN · HITL · 未认领

### Question

基于 W2–W6 的能力盘点和验证结果，ZWorkbench 应选择哪一种采用姿态：

- 直接采用一个现成项目，仅做配置和外围集成；
- 选择一个主 Harness，ZWorkbench 只拥有跨项目的薄编排/产品层；
- 组合多个专长项目，由 ZWorkbench 负责统一任务、权限、状态和观测；
- 分叉一个项目，在其运行内核上长期维护差异；
- 只有在证据表明现有项目无法提供关键能力时，才自建明确的深模块。

必须明确：候选项目哪些能力直接复用、哪些通过适配器接入、哪些必须由 ZWorkbench 自有；组合是否会引入重复状态、事件模型、权限模型和升级耦合；什么实测缺口才足以引入第二个 Harness 或开始自建。

推荐默认：先选一个主候选做试点，加一层尽可能薄的 ZWorkbench 边界；只有出现可测量的能力缺口时才组合第二个项目。自建仅限跨候选的产品能力或明确不存在的深模块，不从零重写已有 Agent 运行循环。

⛔ blocked by：至少一个候选固定版本 C2–C7 adapter、真人 C7 计时、许可证/升级/回滚/退出审计

---

## W8 — 确定 Provider 抽象和模型能力降级策略 [G]

状态：⬜ OPEN · HITL · 未认领

### Question

多 Provider 的“支持”是统一 API、按能力协商，还是允许不同 Harness 各自使用原生接口？定义工具调用、流式输出、上下文窗口、结构化输出、缓存、成本/限额、隐私策略和故障切换的共同最小契约，以及当 Provider 不具备某项能力时的显式降级方式。

⛔ blocked by：W2、W3、W6、W7

---

## W9 — 形成分阶段采用路线与停止条件 [G]

状态：⬜ OPEN · HITL · 未认领

### Question

以 W7/W8 的路线为前提，第一阶段试点应选择哪个候选、哪类项目和哪组任务？第二阶段何时引入替代 Harness、独立调度器或观测系统？定义每阶段的退出条件、可接受迁移成本、回滚方式和“停止投入/改选基座”的信号。

⛔ blocked by：W7、W8

---

## Ticket protocol

- 每次只认领并解决一个决策票据；研究票据可以并行运行。
- 认领格式：在标题状态中加入 `🔒 <claimer>`；完成后加入 `✅`，并在票据下记录带来源的 Resolution。
- 票据 Resolution 不直接写入 `Decisions so far` 的细节；地图只追加一句结论和本票据的锚点链接。
- 新问题只有在已经能精确表述时才升级为新票据；仍受未决前提影响的内容留在 `Not yet specified`。
- 进入实现前，W6–W9 必须完成，且必须保留明确的未知项、验证门槛和退出条件。
