---
doc-kind: product-requirements
authority: supporting
source: https://github.com/jununfly/ZWorkbench/issues/8
source-id: github-issue-8
status: accepted
implementation-status: complete
---

# 通用 UI 引用评审能力与协议／运行时双 Skill

## Problem Statement

当前的界面引用注册表与本地评审标注能力已经在 ZWorkbench 的 R1 产品规格中形成了较完整的协议、运行时边界和验收合同。它解决了 Human 与 Coding Agent 之间准确指认界面元素的问题，但现有规格仍然同时携带 ZWorkbench 的产品视图、CompositionOwner 边界、具体状态、宿主形态、构建身份和验收矩阵。

如果其他项目直接复制 R1 规格，通常会出现三类问题：

- 把某个项目的视图、Run 状态或 Owner 语义误当成通用 UI 协议；
- 把协议规则、运行时实现和当前验收证据复制到多个地方，形成漂移的第二事实源；
- 让 Coding Agent 只能依赖项目作者的隐含经验，无法按稳定步骤设计、实现、验证或解析 UI 引用。

现有 R1 PRD 也不适合作为 skill 原样使用。PRD 描述的是 ZWorkbench 要提供什么以及如何验收；skill 描述的是 Agent 在不同项目中应如何工作。两者的生命周期、调用方式、事实源和完成判据不同。若直接把 R1 PRD 改名为 skill，会损失产品需求和验收证据，并把 ZWorkbench 专属细节永久加载到其他项目的工作上下文中。

因此需要保留 R1 PRD，同时抽取两个更通用、职责清晰且可组合的 skill：

1. 协议设计 skill：把“可讨论、可定位、可迁移、可验证”的 UI 引用要求整理成一个项目无关的协议 profile；
2. 运行时实现 skill：根据协议 profile 在具体项目中落地声明、manifest、DOM 标记、评审交互、解析和行为验证。

两个 skill 必须服务更多项目和 Coding Agent，但不能成为新的 UI 运行时、第二个产品架构或第二个 durable owner。

## Solution

保留现有 R1 PRD 作为 ZWorkbench 的产品需求、实现状态和验收证据来源；新增通用双 skill 能力。

协议设计 skill 面向产品负责人、架构师、UI 开发者和 Coding Agent，负责识别问题边界、定义稳定语义身份、规定 manifest／token／深链接／迁移／脱敏／副作用合同，并输出一个可被运行时实现 skill 消费的 UI Reference Protocol Profile。它只定义协议和验证要求，不直接实现浏览器 overlay、面板、剪贴板或业务视图。

运行时实现 skill 面向需要在具体项目中实现或改造该能力的 Coding Agent，负责读取已确认的协议 profile，发现项目的 UI 渲染、构建、源码定位和浏览器验证接缝，完成“代码声明 → manifest → DOM → review session → token／link → manifest／源码定位”的纵向闭环，并验证正常交互、失败语义、脱敏、无远端副作用和退出清理。它通过项目已有的 UI、Host、Control Plane 或 facade 接缝工作，不直接接管业务状态。

协议 profile 是两个 skill 的显式交接物。它包含协议身份、语义字段、生命周期、错误结果、信任边界、宿主能力假设和验收条件，但不包含项目的动态业务数据。两个 skill 可以独立安装；运行时 skill 不能依赖某个 skill 目录的隐式路径或未声明的跨 skill import。缺少或无法验证 profile 时，运行时实现进入 `unknown`／`HOLD`，不自行发明协议。

通用能力只抽取稳定的设计和工作流原则。ZWorkbench 的 `ui-ref/v1` 字段白名单、三个工作台视图、CompositionOwner 约束、具体 viewport、CLI、源码模块和现有证据继续作为项目 profile 或产品文档，不升级为所有项目必须采用的全局事实。

产品绑定关系：ZWorkbench 的具体产品需求、视图矩阵与验收历史继续由 [R1 界面引用注册表与本地评审标注模式](r1-ui-reference-registry.md) 维护；本 R2 只定义可复用的 skill 抽取与交接边界。`ZWorkbench-specific profile` 联调不属于本阶段实施范围，不是本阶段完成门槛；最终验收将其记录为 `deferred/unknown`，由项目维护者在后续独立工作中补充证据。

## User Stories

1. As a product owner, I want to keep the existing product PRD as the product source of truth, so that extracting a reusable skill does not erase product scope or acceptance history.
2. As a product owner, I want the reusable capability separated from ZWorkbench-specific views and states, so that other projects can adopt it without importing unrelated domain assumptions.
3. As an architect, I want a protocol-design skill and a runtime-implementation skill with separate responsibilities, so that protocol decisions are not silently changed during UI coding.
4. As an architect, I want the two skills connected by an explicit protocol profile, so that their handoff is inspectable and reproducible.
5. As a Coding Agent, I want to know whether I am designing a protocol, implementing an existing protocol, or auditing an implementation, so that I choose the correct workflow.
6. As a Coding Agent, I want the skill to stop with `unknown` or `HOLD` when the protocol profile is missing or contradictory, so that I do not invent a compatibility contract.
7. As a Coding Agent, I want the protocol skill to discover existing project conventions before proposing new identifiers, so that the project does not receive a second naming system.
8. As a UI developer, I want semantic UI elements to receive stable machine references from code declarations, so that layout changes do not invalidate feedback.
9. As a UI developer, I want semantic names, accessible names, visual styling and machine identity kept separate, so that copy and presentation changes do not silently change identity.
10. As a UI developer, I want the generated manifest to be derived from declarations, so that a manually maintained element mapping cannot drift from the implementation.
11. As a UI developer, I want manifest generation to be deterministic for the same declared semantics and build inputs, so that agents and reviewers can compare artifacts reliably.
12. As a UI developer, I want duplicate declarations, invalid names, broken parent relationships and invalid lifecycle links rejected early, so that an inconsistent manifest cannot ship.
13. As a UI developer, I want the protocol skill to distinguish semantic identity from source provenance, so that a comment or line-number change does not masquerade as a semantic migration.
14. As a UI developer, I want source provenance to include a repository-relative anchor and content identity, so that an agent can verify whether the historical declaration still matches the current source.
15. As a UI developer, I want the runtime skill to render only references that are present in the validated manifest, so that an undeclared DOM node cannot acquire a plausible identifier.
16. As a UI developer, I want repeated list items to reuse one structural reference, so that business identifiers, titles and list positions do not create unbounded reference names.
17. As a reviewer, I want repeated items distinguished only within the current review session, so that I can select the intended instance without exposing business identity.
18. As a reviewer, I want session instance handles to be random, memory-only and non-reusable after session close, so that a feedback token cannot become a business lookup key or credential.
19. As a reviewer, I want a reordered item to retain its session association, so that selection follows the entity rather than its previous position.
20. As a reviewer, I want an unmounted item reported as `unavailable`, so that the system does not silently select another visible item.
21. As a reviewer, I want a cross-session instance token reported as `expired`, so that the system does not pretend to recover a historical business row.
22. As a reviewer, I want a repeated structure without an instance handle reported as `ambiguous`, so that the first row is never chosen by default.
23. As an AI collaborator, I want to resolve a token against the exact mapping and build identity it names, so that I discuss the same semantic element the reviewer saw.
24. As an AI collaborator, I want source lookup to verify content identity before reporting a precise hit, so that a moved or changed declaration is not presented as current truth.
25. As an AI collaborator, I want missing artifacts reported as `manifest-missing`, so that a current artifact is not silently substituted for an unavailable historical one.
26. As an AI collaborator, I want older mappings to resolve only through explicit migration metadata, so that aliases and replacements remain explainable.
27. As an AI collaborator, I want incompatible, retired and replaced references clearly distinguished, so that I do not describe a replacement as the same identity.
28. As a reviewer, I want feedback tokens to use a versioned and strict whitelist, so that arbitrary page text cannot enter the collaboration channel.
29. As a reviewer, I want malformed, oversized, duplicated or unknown token fields rejected without echoing the input, so that hostile or accidental content is treated as data and not instructions.
30. As a reviewer, I want the token to carry only the minimum approved viewport and display context, so that feedback remains understandable without exposing product data.
31. As a security owner, I want prompts, event bodies, credentials, cookies, approval tokens, input contents and absolute local paths excluded from tokens, links, overlays, logs and persistent browser storage, so that review does not weaken the privacy boundary.
32. As a security owner, I want the protocol to state that a token is a locator rather than an authentication, approval, restore or execution capability, so that downstream agents do not treat feedback as authorization.
33. As a reviewer, I want deep links to locate an existing semantic element without restoring business state, so that following feedback cannot start a run or change an Owner.
34. As a reviewer, I want unknown link parameters, repeated parameters and incompatible mappings rejected explicitly, so that a link cannot smuggle in a hidden command.
35. As a reviewer, I want review mode disabled by default and enabled only by an explicit local action, so that ordinary product use is not altered by an annotation layer.
36. As a reviewer, I want hover and focus to preview a target while an explicit panel action locks it, so that pointing at a control never accidentally activates it.
37. As a reviewer, I want the highlight layer to pass pointer events through to the business element, so that normal clicking occurs once and remains owned by the product.
38. As a keyboard user, I want review controls to be reachable and visibly focused, so that I can inspect, lock, copy and clear references without a mouse.
39. As a keyboard user, I want review-specific keys consumed only in review mode and in the correct focus context, so that ordinary text input, dialogs and business shortcuts remain intact.
40. As a reviewer, I want the original focus restored when the review panel closes, so that disabling review does not strand focus in a removed element or on the document body.
41. As a reviewer, I want clipboard writes to happen only after an explicit user action, so that merely hovering or loading a page cannot copy data.
42. As a reviewer, I want clipboard failure to remain visible and preserve my selection, so that I never mistake a failed copy for a completed handoff.
43. As an operator, I want the review workflow to make no remote requests or telemetry calls by default, so that local feedback creates no unplanned retention obligation.
44. As an operator, I want the review workflow to leave Run, attempt, event, effect, approval and replay canonical state unchanged, so that UI feedback cannot become an execution channel.
45. As an operator, I want every review resource, listener, overlay and background task released on disable and unload, so that repeated review sessions do not leak state.
46. As a maintainer, I want third-party picker or highlighter dependencies evaluated for version pinning, license, footprint and exit path, so that a small collaboration feature remains replaceable.
47. As a Coding Agent, I want the protocol skill to record assumptions, unknowns and required host capabilities, so that a missing browser, renderer or artifact is not reported as a passing implementation.
48. As a Coding Agent, I want the runtime skill to prefer existing project seams and one public UI Reference Contract boundary, so that the implementation does not create one adapter per component.
49. As a Coding Agent, I want the runtime skill to use the project's existing facade for business data, so that it never reads a durable owner directly merely to annotate a page.
50. As a Coding Agent, I want the runtime skill to separate generated diff from applying a diff, so that implementing review support does not imply permission to modify a protected workspace.
51. As a Coding Agent, I want structural tests and real-engine tests reported separately, so that passing string assertions is not mistaken for browser behavior evidence.
52. As an evaluator, I want the generic skill tested against more than one project or isolated fixture, so that ZWorkbench-specific success is not mislabeled as cross-project portability.
53. As an evaluator, I want evidence to identify the project profile, skill version, protocol version, environment, browser capability and artifact identity, so that results can be reproduced and compared.
54. As an evaluator, I want missing browser or missing historical artifacts to preserve `unknown`, so that evidence thresholds cannot be gamed by skipping hard surfaces.
55. As a project maintainer, I want a project-specific profile to override generic defaults explicitly, so that local requirements are visible without forking the entire skill.
56. As a project maintainer, I want a protocol change to be versioned independently from a runtime implementation change, so that agents can determine whether compatibility testing is required.
57. As a project maintainer, I want a runtime implementation to fail loudly when it cannot satisfy a required protocol invariant, so that it does not ship a partial feature under a complete-sounding name.
58. As a Coding Agent, I want the skill package to work when installed without ZWorkbench source files, so that it can be reused by unrelated repositories and agents.
59. As a Coding Agent, I want the skill instructions to avoid duplicating stable project facts already available in the project profile, so that the skill remains short, discoverable and maintainable.
60. As a Human reviewer, I want the final report to state what is implemented, what is only designed, what is unknown and what remains on hold, so that I can make an informed acceptance decision.

## Implementation Decisions

- **产品规格与 skill 分离**：现有 R1 PRD 保留为 ZWorkbench 的产品规格、具体验收矩阵、实现状态和 Human 验收记录。新 skill 不替换、移动或删改 R1 的产品语义。

- **双 skill 职责**：建立两个独立的可安装 skill。协议设计 skill 负责设计、审查和版本化协议 profile；运行时实现 skill 负责在具体项目中实现和验证该 profile。两者不合并为一个覆盖设计和编码的长文档。

- **显式交接物**：协议设计 skill 的主要输出是 UI Reference Protocol Profile。运行时实现 skill 必须读取该 profile 或项目已有的等价合同；没有 profile、profile 不完整或存在冲突时只能输出 gap／HOLD／unknown，不得临时改变协议。

- **profile 的最小内容**：profile 至少声明协议版本、稳定引用的语义范围、引用命名规则、manifest identity、build/source provenance、结构与实例的关系、生命周期结果、token／link 的字段白名单、隐私禁止项、review mode 交互边界、宿主能力假设、验收阈值和未知处理方式。

- **profile 的数据边界**：profile 只能包含协议和允许的元数据，不包含 prompt、业务标题、完整 Run ID、事件正文、Owner snapshot、凭证、cookie、approval bearer token、输入框内容、生产数据或本机绝对路径。

- **通用身份模型**：稳定机器引用、语义名称、accessible name、视觉样式、源码 provenance、mapping identity 和 build identity 分开建模。视觉重排和文案变化不应静默改变未变化的语义身份。

- **声明与派生物**：项目通过统一声明接缝声明语义元素，构建过程生成并校验 manifest。manifest 是声明的派生产物，不是手工维护的元素清单，也不是 durable owner。

- **结构与实例分离**：结构引用描述可讨论的语义单元；动态实例只在当前 review session 中通过不可预测、内存保存的随机 handle 区分。handle 不从业务 ID、标题、索引、排序或其哈希派生，不成为 durable entity。

- **不确定性优先**：无法唯一解析时返回结构化的 `ambiguous`、`unavailable`、`expired`、`unknown`、`manifest-missing`、`source-mismatch` 或 `incompatible`。任何 fallback 都必须来自显式 profile 规则；CSS、坐标、DOM 顺序和当前首项不是合法的隐式 fallback。

- **生命周期与迁移**：语义未变的改名可以使用显式 alias；语义改变必须创建新身份，并使用 replaced-by 或 retired 结果说明关系。alias 冲突、自指、循环、缺失目标和替代目标冲突在构建或 profile 校验阶段拒绝。

- **历史 identity**：mapping identity 和 build identity 必须精确匹配。历史 manifest 缺失时不能用当前 manifest 静默回答；旧版本只能根据显式迁移窗口报告 migrated、retired 或 incompatible。

- **源码定位**：源码定位结果必须先验证 repository-relative provenance 和内容 identity。内容发生变化时保留历史来源提示，但返回 source-mismatch，不宣称当前源码精确命中。行号可以辅助显示，但不能成为唯一 identity。

- **token 合同**：token 使用版本化协议和固定字段白名单，限制大小、字段类型、重复键、未知键、枚举和值范围。解析器把输入当作数据，不把它解释为 HTML、脚本、指令、路径或授权。

- **深链接合同**：deep link 只能携带定位所需的引用和 mapping identity，并导航到已存在的 UI 语义位置。它不能带业务路由、Run identity、状态恢复参数、执行动作、approval 或 apply 指令，也不能静默开启 review mode。

- **隐私边界**：协议设计 skill 必须产生禁止数据清单；运行时实现 skill 必须在 token、URL、DOM、overlay、日志、clipboard、browser persistence 和 evidence 中验证该清单。真实凭证和生产数据永远不作为测试输入，敏感形状使用合成 canary。

- **review mode**：review mode 默认关闭并显式启用。高亮层不接收指针事件；业务元素的点击、Enter、Space、输入和焦点由产品继续拥有。锁定目标必须通过 review panel 的显式动作，hover／focus 只预览。

- **键盘和焦点**：运行时实现必须声明 review-specific 键盘消费范围、焦点顺序、可见焦点、清除行为和关闭后的焦点恢复。不得用全局监听器抢占业务弹窗、文本输入或未声明元素的快捷键。

- **clipboard**：复制必须由 Human 明确发起。成功与失败都要有可观察结果；失败不能回显宿主错误、不能自动重试、不能清除当前选择。

- **副作用和 ownership**：两个 skill 都不得创建新的 Agent loop、durable owner、scheduler、Provider 调用或业务执行入口。运行时实现只能通过项目已有的 UI facade／Control Plane 读取展示数据，不能直接写 durable owner 或改变 Run、effect、approval、replay canonical state。

- **宿主适配器**：运行时实现以一个公开的 UI Reference Contract 作为最高测试接缝，内部适配 manifest 生成、DOM 渲染、session instance、host navigation、browser driver 和 source lookup。适配器可以因 SSR、SPA、静态 HTML、原生应用或不同测试引擎而变化，但必须映射到同一外部行为合同。

- **能力发现**：运行时 skill 先发现项目的 UI 框架、构建入口、manifest 产物、源码定位能力、宿主边界、浏览器驱动和测试命令，再选择适配方式。缺失能力要记录为 unknown 或 blocked，不用另建隐式工具链掩盖缺口。

- **依赖策略**：第三方 DOM picker、highlighter、clipboard 或 browser helper 不是协议必需项。只有在收益明确时才引入，并记录固定版本、来源、许可证、资源释放方式、替代方案和退出路径。

- **协议与实现版本**：协议 profile、skill 版本、项目 runtime adapter、manifest schema、token schema、browser environment 和 evidence identity 分开记录。协议或 schema 变化后必须重新执行受影响的兼容性和安全验证。

- **技能可安装性**：两个 skill 可以独立安装和调用，不依赖 ZWorkbench 的源码、Python 模块、目录结构或内部命令。运行时 skill 可以消费项目 profile，但不能通过未声明的相对路径导入另一个 skill 的内部文件。

- **调用顺序**：默认工作流是先由协议设计 skill 形成或审核 profile，再由运行时实现 skill 执行实现和验证。若项目已有被接受的 profile，可以直接进入运行时 skill；若只要求审查现有实现，也可以只调用协议设计 skill。

- **调用模式**：初版两个 skill 使用显式 Human invocation，避免普通 UI 视觉设计任务被自动误触发。未来只有在触发词和边界经过多个项目验证后，才考虑把其中一个改为 model-invoked；改动必须评估额外的上下文负担。

- **报告格式**：两个 skill 都必须输出结构化结论，至少区分 `implemented`、`target`、`unknown`、`HOLD`、`blocked`、`migrated`、`retired`、`incompatible` 和 `source-mismatch`。报告必须包含 profile／artifact／environment identity、使用的证据、未覆盖项、下一证据、owner 和回滚路径。

- **不复制产品验收矩阵**：ZWorkbench 的三视图和具体场景矩阵仍由产品规格维护。通用 skill 只要求每个项目提供独立于 manifest 的语义覆盖矩阵，并验证缺失声明不会缩小分母。

- **当前产品绑定**：ZWorkbench 使用现有 R1 协议作为第一个 project profile。该 profile 可以复用既有 `ui-ref/v1`、manifest、动态实例、review host 和测试证据，但这些名称和数值不成为其他项目的强制默认值。

- **变更范围**：本 PRD 计划新增两个 skill 包及其协议 profile／fixture／验证说明，必要时补充项目文档导航。它不要求修改 CompositionOwner schema、DSH 主 Harness、Codex Worker bridge、Provider adapter 或现有业务执行流程。

## Testing Decisions

测试以公开输入、输出、失败结果和用户可见行为为主，不绑定私有 helper、组件树、CSS 类名、DOM 嵌套、内部状态机实现或某个前端框架的偶然结构。

### Protocol design skill

- 用协议设计 fixture 验证相同输入和相同 profile 约束能产生稳定、可审查的协议结果；不以模型是否复述了某段文字作为通过条件。
- 验证稳定引用、结构／实例分离、manifest identity、build/source provenance、生命周期迁移、token／link 白名单和未知结果的外部合同。
- 验证重复声明、非法命名、父级错误、alias 冲突、替代目标缺失、循环、未知协议版本、重复键、未知字段、类型错误、超限和恶意输入全部进入拒绝或结构化 unknown 路径。
- 验证协议建议不会把业务 ID、页面正文、凭证、绝对路径或 Owner canonical state 变成反馈身份或 token 上下文。
- 验证协议 profile 能明确标注宿主能力和证据边界；浏览器、历史 manifest 或源码 identity 缺失时不能生成“已验证”的结论。

### Runtime implementation skill

- 以 UI Reference Contract 作为主要 seam，验证从声明到 manifest、从 manifest 到真实 DOM、从 DOM 到 review session、从 token／link 到 manifest／源码定位的完整闭环。
- 用一个静态单元、一个动态重复单元和一个业务按钮形成最小纵向切片；在正常、空或 unknown 状态以及至少两类 viewport／宿主状态下验证。
- 结构测试验证 manifest 生成、声明唯一性、identity、迁移和解析结果；真实浏览器或等价引擎测试验证可见性、pointer passthrough、focus、keyboard、clipboard、deep link 和 review mode 生命周期。
- 动态实例测试覆盖至少两个相同结构项、重排、普通重渲染、卸载、重新挂载、删除、review session 关闭和跨 session 解析，并断言不会解析到错误实体。
- 交互测试验证 hover／focus 只预览，panel 显式锁定不触发业务按钮，普通点击恰好一次，业务输入和弹窗快捷键不被拦截，关闭后焦点可预测恢复。
- 退出测试验证反复启停、页面重载、宿主关闭、异常响应和复制失败后没有 overlay、listener、timer、后台任务或 session state 残留。
- 脱敏测试使用合成 prompt、标题、事件、Run identity、路径和 credential-shaped canary，检查 document、URL、token、overlay、日志和 browser persistence，泄露阈值为零。
- 本地副作用测试验证 review 操作不产生远端请求、遥测、Run、effect、approval、Worker、Provider 或 Owner canonical state 变化；任何无法证明的边界保持 unknown。
- 分层报告区分结构证据、宿主／浏览器证据、项目 profile 证据和 owner-backed 证据，不把一个项目的产品测试通过升级为通用 skill 已被多个项目验证。

### Cross-project portability

- 通用性不能只由 ZWorkbench 自身通过来证明。至少使用 ZWorkbench profile 加一个结构不同的独立项目或隔离 fixture 验证 skill 不依赖特定视图、语言、目录、框架、运行状态或 Owner 实现。
- 第二个 fixture 至少应在 SSR／静态渲染与客户端动态挂载、或不同 UI 框架／浏览器宿主边界中体现一个真实差异；如果没有第二个 fixture，跨项目能力标为 `unknown`，不能标为 `implemented`。
- 每个 fixture 记录 skill 版本、协议 profile 版本、runtime adapter 版本、构建／manifest identity、测试环境和浏览器能力。fixture 不使用真实凭证、生产项目或不可逆外部副作用。
- 两个 skill 的安装和最小调用必须在没有 ZWorkbench 内部模块的环境中完成；引用 ZWorkbench 的内容只能作为显式 project profile 或 evidence，不得成为隐式依赖。

### Prior art and regression

ZWorkbench 已有的 manifest 校验、token／deep link 解析、动态实例生命周期、真实宿主矩阵、键盘／焦点、clipboard 失败、脱敏、零远端请求、Owner state 不变和 review teardown 测试作为第一组行为先例。抽取 skill 不得删减这些产品测试；新 skill 的跨项目 fixture 和安装验证属于额外的 skill/evaluation 证据，不能替代产品测试。

完成门槛是：两个 skill 均能独立安装；协议 profile 可被独立读取；运行时 skill 在 ZWorkbench profile 上完成既有回归；至少一个非 ZWorkbench fixture 完成协议和运行时的适配验证；所有必需负向路径有明确结果；关键能力缺失时保留 unknown／HOLD；没有凭证、生产数据或大型历史 run 进入 skill、fixture、evidence 或 git。

## Implementation status

- `implemented`：协议设计与运行时实现两个独立 skill、`ui-reference-profile/v1` 校验器、严格运行时 evidence checker、双 validator conformance corpus，以及不依赖 ZWorkbench 模块的 `catalog-html` 完整 portability runtime 已落地。独立 fixture 已取得协议、静态闭环、动态 session、真实浏览器交互、覆盖矩阵和 unload teardown 证据；R1 的声明、manifest、动态实例、review mode、token、deep link、迁移、源码 provenance、脱敏和 owner 不变回归保持通过。
- `deferred/unknown`：本阶段不做 `ZWorkbench-specific profile` 联调验证；它不阻塞本阶段完成，后续证据由项目维护者负责。没有浏览器或指定历史 artifact 时，evidence checker 仍保留 `unknown`，不能由当前 artifact 静默替代。第三方 picker/highlighter 依赖仍不是协议必需项。
- `HOLD`：profile 缺失、字段冲突、证据结构不完整、敏感数据或未授权副作用会 fail closed。`blocked`：当前实现链无外部阻塞。
- 证据接缝：[profile contract tests](../../tests/test_ui_reference_profile.py)、[runtime skill tests](../../tests/test_ui_reference_runtime_skill.py)、[portability fixture tests](../../tests/test_ui_reference_portability.py)、[installation tests](../../tests/test_ui_reference_skill_installation.py)；R1 产品行为仍以其自身 `tests/test_ui_*.py` 和 [R1 PRD](r1-ui-reference-registry.md) 为准。
- 回滚边界：skill 只生成可审查的 diff 和 evidence；apply 仍由项目 policy／approval／effect receipt 拥有，任何 apply 必须有可恢复 rollback 路径。skill 不创建新的 Agent loop、durable owner、scheduler、Provider 或业务执行入口。

## Out of Scope

- 把现有 R1 PRD 直接改名、移动、删除或用 skill 取代。
- 把 ZWorkbench 的三个视图、CompositionOwner、Run 状态、DSH／Codex／Provider 边界或具体 CLI 变成所有项目的强制产品模型。
- 创建一个新的通用浏览器反馈平台、远端协作服务、截图／录屏／OCR 系统、遥测系统或自动 Issue 发布器。
- 用 token 或 deep link 实现认证、approval、业务状态恢复、任务执行、apply、Git push、部署或 live replay。
- 创建第二个 durable owner、浏览器数据库、隐式 scheduler、in-browser Agent loop 或跨项目业务状态同步。
- 自动从任意页面文本、坐标、CSS selector、DOM 顺序、截图或模型猜测生成稳定身份。
- 承诺支持所有前端框架、原生应用、浏览器和无障碍实现；没有适配器和证据的环境保持 unknown。
- 在没有明确版本、许可证、资源释放和退出路径的情况下强制引入第三方 picker／highlighter 依赖。
- 通过 skill 自动修改真实主工作区、生产配置、远端资源、Provider 账户、凭证或不可逆数据。
- 把一个项目的 native、plugin-composed、outer-composed 或 owner-backed 证据直接宣称为所有项目的通用通过证据。

## Further Notes

- 这是对现有 R1 产品能力的知识抽取和复用路线，不是 R1 的重新产品设计。R1 继续记录 ZWorkbench 的具体目标、实现状态、完整矩阵和 Human 验收。
- 通用 skill 的核心抽象应使用“协议 profile”“UI Reference Contract”“结构身份”“实例身份”“mapping/build identity”“显式 unknown”等 leading terms，减少不同项目之间的术语漂移。
- 两个 skill 的共享知识应通过显式 profile 或稳定的外部参考传递，不依赖安装目录之间的隐式文件引用。这样即使某个项目只安装运行时 skill，也能明确知道缺少什么输入。
- 初版优先抽取审核、定位、协议校验和实现工作流；不要把协议固定字段和浏览器行为代码搬进 skill 文本。skill 指导 Agent 调用项目能力，项目运行时才拥有真实行为。
- 当前 R1 产品文档及其索引继续独立维护产品范围和验收状态；新 skill 不复制未经当前代码、测试和运行证据重新确认的历史状态。
- 协议设计 → profile → runtime adapter → 静态与完整 runtime evidence 链条已由独立 `catalog-html` fixture 验证；`ZWorkbench-specific profile` 联调保持 deferred/unknown，不在本阶段发布或实现对应 ticket。
