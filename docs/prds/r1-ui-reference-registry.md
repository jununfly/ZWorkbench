---
doc-kind: product-requirements
authority: supporting
status: target
implementation-status: partial
---

# R1 界面引用注册表与本地评审标注模式

## Problem Statement

Human 与 AI 在评审工作台时，无法通过对话准确定位同一个界面元素。“左边卡片”“右下按钮”等描述会因视口、布局、运行状态和动态列表而产生歧义；截图坐标、CSS selector 与 DOM 顺序又会随重构失效。

手工维护 docs 元素映射表会形成另一份容易漂移的命名来源。用户已明确取消该设计，改为代码驱动的界面引用注册表。反馈过程还必须避免把页面正文、Run 数据或凭证带入 URL、剪贴板与外部平台。

## Solution

在 R1 工作台提供默认关闭、显式开启的本地评审标注模式。Human 悬停或选择主要语义元素时，看到边框、中文语义名和稳定引用；主动复制脱敏反馈 token 后，AI 可通过同一构建版本的 UI Reference Manifest 定位代码声明。深链接只定位界面元素，不恢复或执行业务状态。

完整合同是：代码通过统一 helper 声明引用，构建生成并校验 manifest，页面渲染真实引用属性，标注模式读取真实 DOM，生成脱敏 token，Human/AI 通过 manifest 回到代码。manifest 是代码的派生产物，不是第二个手工维护的注册表。docs 只说明协议、命名、安全与迁移规则，不列出元素映射清单。

## User Stories

1. As a Human reviewer, I want to explicitly enable local review mode, so that annotation appears only when I need it.
2. As a Human reviewer, I want to see a subtle highlight and Chinese semantic name on hover, so that I can identify the element under discussion.
3. As a Human reviewer, I want to select and retain an annotation target, so that I can describe it without losing my place.
4. As a Human reviewer, I want to copy a short feedback token with an explicit action, so that I control what enters my clipboard.
5. As a Human reviewer, I want the token to include a stable reference and mapping version, so that AI can locate the same semantic element.
6. As a Human reviewer, I want approved viewport and display-state context in the token, so that layout-dependent feedback is understandable without exposing business data.
7. As a Human reviewer, I want a local deep link to locate and highlight an element, so that I can return to the subject of a discussion.
8. As a Human reviewer, I want missing or hidden elements to be explained, so that a link never points at an arbitrary substitute.
9. As a Human reviewer, I want migrated and retired references to have explicit outcomes, so that old feedback remains interpretable.
10. As a Human reviewer, I want repeated list items to be distinguished within the current review session, so that selection does not silently resolve to the first row.
11. As a Human reviewer, I want annotation to preserve normal clicking, typing and keyboard focus, so that review does not alter task execution.
12. As a keyboard user, I want accessible review controls and visible focus, so that I can select, inspect and copy references without a mouse.
13. As a Human reviewer, I want to disable review mode completely, so that no overlay or background listener remains active.
14. As a Human reviewer, I want clipboard failure to be visible, so that I never assume a reference was copied when it was not.
15. As an AI collaborator, I want to resolve a token through the matching manifest to its code declaration, so that I can discuss and modify the correct semantic unit.
16. As an AI collaborator, I want ambiguous, unknown and incompatible references reported explicitly, so that I do not guess from CSS or coordinates.
17. As a UI developer, I want one code declaration to supply the runtime reference and generated manifest, so that I do not maintain a docs mapping table.
18. As a UI developer, I want stable machine identity separated from Chinese copy and accessible names, so that copy changes do not break references.
19. As a UI developer, I want repeated entities to reuse a structural reference, so that Run IDs and titles do not create unbounded reference names.
20. As a UI developer, I want duplicate declarations, invalid names and broken relationships to fail validation, so that an inconsistent manifest cannot ship unnoticed.
21. As a UI developer, I want semantic changes to require replacement or retirement metadata, so that old references never silently acquire a different meaning.
22. As a UI developer, I want rendered semantic elements checked against the manifest across states and viewports, so that generated metadata agrees with what reviewers see.
23. As a workbench user, I want tokens and links to exclude prompts, event bodies, credentials and local absolute paths, so that feedback does not weaken the product privacy boundary.
24. As an operator, I want review mode to make zero remote requests and telemetry calls, so that local review does not create an external retention obligation.
25. As an operator, I want annotation to leave Owner state and execution flows unchanged, so that UI feedback cannot become an approval or execution channel.
26. As a maintainer, I want any reused selector/highlighter dependency to have a pinned version, license and exit path, so that a small feature remains maintainable.
27. As a maintainer, I want a reusable skill extracted only after the product protocol has been exercised, so that the skill documents a tested workflow rather than replacing runtime behavior.

## Implementation Decisions

- **已确认的单一来源**：统一代码 helper 声明 `ui_ref`；构建从声明生成并校验 UI Reference Manifest。不得新增人工 docs 元素映射表。协议文档与本 spec 不承担具体元素清单的职责。
- **语义粒度**：只覆盖人会讨论、影响行为或信息理解的单元，例如工作记录列表、列表项、当前工作、运行事实、证据、预检操作及结果。装饰容器、分隔线、图标内部节点不注册。
- **字段分离**：稳定机器引用、中文语义名和无障碍名称分别维护。文案、布局和可访问名称变化不改变语义未变的引用。注册声明包含元素类型、父级引用、适用状态、代码来源和生命周期信息；manifest 与构建/映射版本绑定。
- **校验边界**：声明的引用全局唯一，名称合法，父级关系和迁移目标有效。注册表定义唯一性与动态实例重复是不同规则；一个列表项声明可渲染多个实例，不能以此关闭声明重复检测。
- **动态元素**：Run ID、标题和业务载荷不拼入结构引用。实例上下文与结构引用分离，使用当前评审会话内随机分配的 instance handle；不从 Run ID、标题、索引或其哈希派生。handle 与 UI 已有实体 key 的关联仅在内存保存，不成为 durable entity。同会话内已选且仍挂载的实例必须唯一解析，排序和普通重渲染保持关联；虚拟化卸载时返回 `unavailable`，同一实体重新挂载可恢复关联。实体删除、关闭评审、页面重载或切换工作区后 handle 失效且不得复用。跨会话 token 仅能解析结构及代码声明，实例结果为 `expired`；不得伪称已找到原业务记录。无 handle 的重复结构返回 `ambiguous`，不默认取首项。
- **真实 DOM**：运行时渲染 `data-ui-ref`，标注模式从真实元素读取引用并核对 manifest；不从截图坐标、CSS class 或 DOM tree order 创造身份。未登记节点不生成看似有效的反馈引用。
- **Token 合同**：版本化 `ui-ref/v1` token 只携带稳定引用、映射/构建版本、允许的视口类别、展示状态及必要的脱敏上下文。字段及限制由下方 Token v1 合同固定；不允许自由格式 context，不抽取页面文本推断上下文。展示状态不是 Owner 状态的授权或恢复指令。
- **禁止数据**：prompt、运行标题、完整 Run ID、原始事件、Owner snapshot、凭证、cookie、approval bearer token、输入框内容与本地绝对路径不得进入 token、overlay 或链接。代码来源定位保留在本地 manifest，不将本机路径复制进反馈。
- **深链接**：链接仅携带引用和映射版本，定位已存在的界面语义。不能携带业务状态、恢复 Run、启动任务、触发预检或 apply。默认关闭的评审模式不被链接静默开启；未开启时提示用户显式进入评审模式。
- **引用生命周期**：视觉重排不改 ref；语义改变创建新 ref，并声明 alias / replaced-by 或废弃结果。当前映射版本必须保留对紧邻上一发布映射版本的显式迁移声明；更早版本可返回 `incompatible`。初版用合成上一版本 fixture 验证兼容合同。禁止静默复用已废弃身份。迁移必须显示结果；未知引用或不兼容版本不回退到 CSS 猜测。
- **交互与退出**：评审模式默认关闭，仅本地显式启用。高亮层不接收指针事件，普通点击、Enter 和 Space 保留业务行为。独立评审面板列出当前已挂载语义目标（动态项仅显示中文结构名和短暂随机标记），用户通过面板中的“锁定目标”按钮选择，绝不向业务元素派发点击。悬停/聚焦只预览；面板提供键盘可达的目标选择、锁定、复制与清除操作。Escape 仅在评审面板拥有焦点时清除锁定；不拦截业务弹窗的 Escape。关闭面板恢复开启前仍存在的焦点目标，否则回到评审入口。复制必须由用户发起；失败可见。禁用/卸载释放 overlay、监听器和后台资源，保留正常焦点和无障碍语义。
- **所有权**：本模块只拥有界面引用元数据及短暂展示状态，不持有 Run、attempt、event、effect、approval 或 replay canonical state。已有展示数据沿用 Workbench Control Plane façade；不增加 Owner schema，不直接读取 SQLite、DSH/Codex session 或调用 Worker/Provider。
- **测试接缝**：以“UI Reference 解析与评审”公开合同作为一个主要接缝，覆盖生成/校验 manifest、解析 token/link、定位目标和禁用生命周期；真实页面集成验证该合同的可见结果。既有 façade 保持业务动作接缝，不为每个组件另建业务适配器。
- **依赖与 skill**：第三方 DOM picker/highlighter 的可复用性仍为 `unknown`，未选定依赖或前端框架。优先评估小型本地能力，验证版本 pin、许可证、依赖、关闭和退出。先验证产品切片并完成两三轮真实反馈，再考虑抽取 skill；skill 负责校验、定位与协作工作流，不实现另一套浏览器运行时。

### Token v1 固定合同

复制格式为 UTF-8 JSON 对象，序列化后不超过 1024 字节；拒绝重复键、未知键、类型错误、超限和未知协议版本。输入作为数据解析与文本展示，不解释为 HTML、脚本、指令或路径。以下是完整白名单，字段外信息不能通过嵌套对象或自由文本进入 token。

| 字段 | 必填 | 值及限制 |
|---|---|---|
| protocol | 是 | 固定 `ui-ref/v1` |
| ref | 是 | 1–128 个 ASCII 字符；小写字母开头，各点分段仅含小写字母、数字和连字符；必须能在指定 manifest 解析 |
| ui_map | 是 | manifest 规范化内容的 SHA-256，小写十六进制 64 位；不包含其自身 digest 字段计算 |
| build | 是 | 源码及构建输入 receipt 的 SHA-256，小写十六进制 64 位 |
| viewport | 是 | `compact`（CSS viewport 宽度小于 768px）或 `wide`（至少 768px） |
| state | 是 | `draft`、`loading`、`empty`、`created`、`running`、`recovering`、`completed`、`failed`、`denied`、`safe-stopped`、`unknown`、`not-applicable`；来自已有脱敏 view model 或静态展示合同，无依据时用 `unknown` |
| instance | 否 | 128-bit 安全随机 handle，编码为 32 位小写十六进制；仅动态实例定位使用 |

handle 不是凭证或可远程查询的业务标识。生成器仅从已校验 manifest 与允许的展示元数据取值；解析器验证字段并返回结构化错误，不能把非法输入回显到日志。复制失败保留本地选择并显示失败，不自动重试剪贴板写入。

深链接使用本地工作台入口及 `ui_ref`、`ui_map` 两个定位参数，分别遵循 ref 与 ui_map 的规则；不带 build、state、instance 或业务路由参数。入口按 manifest 的视图归属进行纯 UI 导航，不能加载指定 Run 或改变 Owner 状态。动态重复项的链接只定位结构，要求用户在本地选择实例；隐藏目标显示 `unavailable`。单个定位参数重复、未知定位参数或超限均拒绝。链接本身不是实例级复现保证。

### Manifest 获取与源码定位合同

构建输出确定性的 manifest 与 build receipt，随本地 UI artifact 一起保存；提供只读本地查询接口，按精确 ui_map/build identity 返回 manifest 或 `manifest-missing`，不联网下载历史版本。评审面板显示当前 identity 和本地查询说明，AI 可经项目本地工具读取同一产物。具体命令随前端宿主落定，但必须能在不启动业务 Run 的情况下查询。

manifest 包含 schema 版本、构建 receipt identity、视图归属、引用声明及迁移信息；声明来源包含仓库相对路径、声明符号和对应源码内容 digest。receipt 固定源码快照（包含未提交修改）及构建输入摘要，Git commit 可作为辅助来源但不能替代内容 identity。禁止 manifest 包含本机绝对路径或业务数据；不依赖易漂移的行号作为唯一定位依据。

解析分别返回“结构/代码来源结果”和“当前 DOM 实例结果”。代码定位前验证目标源码内容 digest；不匹配返回 `source-mismatch`，保留历史来源提示，不给出当前源码精确命中的结论。缺少指定产物时返回 `manifest-missing`；当前版本不匹配时仅能按显式迁移记录返回 `migrated` 或 `retired`，没有记录返回 `incompatible`。不得用当前 manifest 静默替代旧 manifest。alias 冲突、循环和不存在的目标在构建时拒绝。语义变化的 replaced-by 结果必须标明“替代元素”，不能表述为同一身份。

## Testing Decisions

测试公开输入输出和用户可见行为，不绑定组件内部状态、私有 helper、DOM 嵌套或 CSS 实现。以下阈值是待实现验收合同，不是已通过结果。

| 验证面 | 行为与失败路径 | 验收阈值 |
|---|---|---|
| 构建合同 | 有效声明生成确定 manifest；重复声明、非法名称、无效父级、失效迁移目标被拒绝 | 无效 fixture 全部拒绝；相同输入产物一致 |
| DOM 一致性 | 下方固定语义覆盖矩阵中的单元使用匹配 manifest 的真实引用 | 所有必测组合覆盖 100%；缺少声明不能缩小分母；未知/冲突引用不伪装成功 |
| 身份稳定 | 修改文案、布局和列表顺序；语义变更走显式迁移 | 未改语义的 ref 保持；旧 ref 不静默指向新语义 |
| 动态实例 | 多个相同结构 ref、空列表、列表重排、实例离开视图 | 同会话已选且挂载的实例准确定位率 100%，重排/重渲染仍命中；卸载为 unavailable，会话失效为 expired，无 handle 的重复项为 ambiguous；错误定位 0 |
| Token 与深链接 | 正常解析、1024 字节边界及超限、重复/未知键、非法枚举、未知版本、畸形输入、隐藏元素、alias、废弃和跨版本输入 | 无猜测性回退；不执行任何业务动作 |
| 版本与源码闭环 | 本地查询当前/上一版本产物、缺失 manifest、源码变化、alias 循环与冲突 | identity 匹配时定位准确；缺失/不匹配显式报错；静默替代 0 |
| 选择与焦点 | 面板锁定业务按钮，普通点击、键盘选择、清除、关闭及原焦点消失 | 锁定不执行按钮；普通点击只执行一次；仅面板消费评审按键；焦点可预测恢复 |
| 脱敏 | 用合成 prompt、标题、Run ID、事件、路径、凭证等污染页面与输入 | token、URL、overlay、日志和浏览器持久化中泄露 0 |
| 本地与副作用 | 开启、悬停、选择、复制、链接定位、关闭 | 远端请求/遥测 0；无自动剪贴板写入；无新增 Run/effect/approval 或 Worker/Provider 执行 |
| 正常模式与评审模式 | 对照执行既有预检、Run 展示和 effect 流程；测试点击、输入、焦点与键盘导航 | 行为合同一致；overlay 不截断或重复业务动作 |
| 退出 | 反复启停、卸载、复制失败与解析失败 | overlay/监听器/后台任务残留 0；正常交互可继续 |

既有 CompositionOwner、local read-only orchestration、replay 和安全负向测试提供行为先例：身份不足不推断成功、默认拒绝、模式隔离及敏感内容不落盘。新增 UI 测试沿用这些原则，通过 façade fixture 核对业务状态未变化，不复制 Owner 内部测试。

### 固定语义覆盖矩阵与完成门槛

以下是产品验收范围，不是“元素 → ref”映射表。实施时把此矩阵转为版本化测试 fixture，具体 ref 从代码生成 manifest 读取；fixture 必须独立断言各语义单元存在，不能只遍历已注册元素来计算覆盖率。

| 视图 | 必测语义单元 | 必测场景 |
|---|---|---|
| 首页 | 工作区/模式上下文、工作记录列表及动态项、当前意图/已记录文本、计划/下一步、产物区、运行事实、证据区、预检并运行操作及预检结果 | 无记录、草稿、加载、预检拒绝、running、completed、failed、safe-stopped、unknown；至少两个动态项重排与删除 |
| 任务详情 | 意图、准入检查/拒绝原因、执行身份与时间线、结果/错误、effect/approval/reconcile 展示、replay 模式说明 | denied、running、recovering、completed、failed、safe-stopped、unknown；只读不适用、缺失身份、待 reconcile 的展示 fixture |
| 记录视图 | 记录选择、事件列表及动态项、筛选、事件详情、结果、artifact metadata、replay metadata 与模式边界说明 | 加载、空事件、正常记录、无筛选结果、缺失 metadata/unknown、重复结构事件项 |

每个场景在 390px 和 1280px CSS viewport 宽度、正常与评审两种模式下执行；用 fixture 明确每个单元应为可见、可展开或不适用，并附不适用原因。不能将缺失实现标为不适用。可展开单元经只读展开后必须可定位；隐藏单元直接定位应返回 unavailable。审批/effect 等目标能力只通过已有记录或合成展示 fixture 验证，不因标注验收而启用执行能力。

最小纵向切片应覆盖一个静态区域、一组动态工作记录和一个业务按钮，在至少两类视口、正常与 unknown/空状态中完成“声明 → manifest → DOM → token → 代码定位”。兼容测试同时覆盖当前与上一兼容映射版本。切片通过仅表示协议链条成立，不代表本功能或整个 R1 完成。本功能完成必须通过完整矩阵、上述正负向测试及 identity/脱敏检查；整个 R1 还须独立通过主规格验收。前端宿主确定后补具体执行命令，不能将未执行的验收项标为通过。

## Out of Scope

- 人工或并行维护的 docs 元素映射表、对每个 DOM 节点编号、依赖像素坐标或 CSS 的身份系统。
- 远端反馈平台、截图/录屏/会话录制、页面内容上传、遥测和自动发布 Issue。
- 将反馈 token 作为认证、approval、业务状态恢复、recorded/simulated/live replay 或任务执行入口。
- 新 durable owner、Owner schema 修改、浏览器 scheduler、Worker/Provider 写操作及多用户协作系统。
- 未经证据选定第三方库、先建设通用生产反馈平台、用 skill 替代产品运行时。

## Further Notes

- 本 spec 是 [R1 工作台规格](issue-1-workbench-ui.md) 的补充，状态为 `target` / `partial`。
- 依据另一任务中用户关于“去掉 docs 映射表”的明确修正，以及对后续六项补正和引用生命周期的“同意，这些内容补进 R1 spec”。来源任务 ID：`01a08451-5660-7e61-b32d-d6812c049c0d`。
- 早期研究 brief 中“docs 映射表”的假设已被上述用户决定替代。该研究仍没有可用的外部选型 ledger，不能把候选可复用性写为已验证。
- 与 [工作台用户界面](../architecture/ta-workbench-user-surface.md) 和 [唯一 durable owner ADR](../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md) 保持一致。manifest 的“唯一来源”仅指界面引用元数据，不挑战 CompositionOwner 的业务所有权。
- 尚待实现细化：前端宿主与 fixture 在真实宿主下的代码组织。helper API、本地 manifest 查询命令、token 白名单、实例有效期、兼容窗口和覆盖分母已固定。这些细节不得削弱上述失败与隐私合同；无法证明安全唯一定位时保持不可用/歧义，不恢复业务状态。

## Implementation status

引用协议已实现：声明层、manifest 与 build receipt、结构与实例定位、token v1 与深链接、
引用生命周期与映射兼容、评审模式状态机、三视图语义单元声明与安全负向断言，均有产品代码
与行为测试。相关模块见 `src/zworkbench/ui_*.py`，验证入口见 [Repository README](../../README.md)。

前端宿主尚未选型。视图渲染是纯函数拼装的 HTML 字符串，评审模式是纯状态机；仓库中没有
样式、脚本、overlay 或服务入口，manifest 也没有构建钩子产出。因此本节区分两类未完成项：
**未验证**指实现存在但只有真实宿主能判定，**未实现**指该行为在当前代码中还不存在。

以下为 `unknown`，实现存在而判定依赖宿主：

| 未验证面 | 原因 |
|---|---|
| `keyboard-focus-order` | 原生 tab 顺序取决于真实 DOM 布局与浏览器策略 |
| `pointer-events-passthrough` | 只有真实引擎能确认高亮层不吞点击 |
| `clipboard-failure-visible` | 真实剪贴板权限拒绝及其可见表现属宿主行为 |
| `focus-restore-on-close` | 焦点是否可见地落到恢复目标属宿主行为 |

以下为**未实现**，当前测试不构成任何证据，不得计入验收：

| 未实现项 | 当前状态 |
|---|---|
| 390px / 1280px 两档视口执行 | 现有矩阵测试遍历视口名称但不改变渲染输入，断言的是同一份 markup；响应式行为属 CSS，尚不存在 |
| 正常模式与评审模式对照 | 评审模式当前不修改 markup，两模式相等的断言恒真；overlay 落地前该对照没有信息量 |
| 可展开单元展开后可定位 | 无展开状态实现 |
| 隐藏单元直接定位返回 `unavailable` | 视图层无隐藏态，该路径未被任何视图触发 |
| `not_applicable` 计数机制 | `coverage_report` 支持该参数，但三视图均未使用，未经真实场景检验 |

覆盖报告固定返回 `evidence: structural-only` 与 `accepted: false`。结构覆盖满格只表示
声明齐全。上述四项 `unknown` 与五项未实现同源于宿主缺位，会随宿主落地一并解决，不得
在此之前标注为 `not-applicable` 或计为通过。本功能验收未通过；整个 R1 仍须独立通过
主规格验收。
