# W8 1-6 火山方舟 Provider 退出与责任一手来源

状态：`evidence-captured / provider-exit-signoff-open / endpoint-boundary-incident-recorded` · 核查日期：`2026-09-01`
（Asia/Shanghai）

本记录服务于 W8 `1-6` 的真实 Provider 资格 gate：核对火山引擎/火山方舟
（Ark）及其 Coding API 的 endpoint、认证、远端对象、数据处理、保留、账户/账单
和退出责任。它只使用火山引擎/火山方舟官方文档、官方政策/条款和官方控制台/API
说明作为外部来源；不执行认证业务 API、不读取或使用凭证、不执行控制台删除或停用；
本轮另记录了一次未携带凭证的 endpoint 根路径边界观察，详见第 12 节，
也不构成推荐、法律意见、隐私/DPA 意见或 Provider 侧删除证明。

本轮只调查真实 Provider 资格 gate，不替代另一条“local recoverable write” gate。
本轮结论只描述证据和责任边界，不把任何 `official-unknown` 自动解释成“没有能力”。

## 1. 判定词与证据规则

| 判定 | 含义 |
|---|---|
| `official-verified` | 官方一手页面直接给出该事实；记录页面标题、URL 和章节/页面事实。 |
| `official-unknown` | 在本轮核对的官方一手页面中没有找到足以证明该命题的内容；不是对能力不存在的断言。 |
| `human-reported` | 由 Human 提供的信息；未由本轮官方页面直接证明，不作为官方能力或删除证明。 |
| `scope-limited` | 官方事实成立，但只适用于页面明示的产品、接口或账户范围，不能外推到 Coding API 或其他产品。 |

证据优先级是：官方产品/API 文档和官方控制台说明 > 官方隐私政策、数据处理协议
和服务条款 > Human 提供的信息。对于同一厂商的不同产品线，保留页面自身的适用
范围；`/api/v3` 的资源接口不能因为同属 Ark 就自动变成 `/api/coding/v3` 的
Coding Plan 能力。

## 2. Human 提供的信息

以下信息由 Human 提供，当前标签为 `human-reported`，不等同于官方已证明：

| 字段 | Human 提供的信息 | 当前边界 |
|---|---|---|
| Provider | 火山引擎/火山方舟（Ark） | 厂商身份由 Human 指定；产品适用范围仍以每个官方页面为准 |
| 接口 | OpenAI-compatible Coding API：`https://ark.cn-beijing.volces.com/api/coding/v3` | endpoint 形态可由官方 Coding Plan 文档交叉核对；Human 信息本身不证明实际账户已连接成功 |
| 认证 | Provider API key | 官方文档证明 API key 是一种认证/敏感凭证；本轮不读取、不验证任何 key |
| 账户范围 | 个人 | Coding Plan 官方页面面向个人开发场景；具体账户、项目、账单归属仍需账户所有者在控制台确认 |
| 远端状态 | 有远端数据、任务、Webhook、备份 | 本轮不把这些存在性当作官方事实；具体资源 ID、产品线、删除入口和 retention 仍是 `official-unknown` / externally-owned |

不得将 API key、Cookie、完整账户邮箱、私有请求内容或远端资源秘密复制到本记录
或后续 evidence。

## 3. W8 1-6 当前边界结论

| 命题 | 证据状态 | 本轮可说到哪里 |
|---|---|---|
| Coding Plan 的 OpenAI-compatible endpoint | `official-verified` | 官方 Coding Plan 快速开始页面的 `Base URL` 章节列出 `https://ark.cn-beijing.volces.com/api/coding/v3`。 |
| Coding Plan API key 获取和敏感凭证边界 | `official-verified` | 官方页面说明 API key 从控制台获取，属于敏感凭证，建议通过环境变量等方式注入；不能由本记录证明某个具体 key 或账户。 |
| API key 可停用、启用、删除 | `official-verified` | 官方“管理 API Key”页面列出状态/权限/最后使用时间/创建人查询及禁用、启用、删除；删除后不能继续用该 key 鉴权。 |
| 标准 Ark `/api/v3` 的 Response、File、异步视频任务 | `official-verified / scope-limited` | 官方标准 API 页面分别证明这些对象及部分删除/取消动作；这些页面不证明 Coding `/api/coding/v3` 暴露同样资源接口。 |
| Coding API 的通用远端任务/Webhook 生命周期 | `official-unknown` | 只找到标准视频生成任务的 `callback_url` 和任务删除/取消页面；未找到可外推到 Coding Plan 的通用 task、scheduler、Webhook 生命周期契约。 |
| Coding API 的备份 API、备份删除和 retention 生命周期 | `official-unknown` | 本轮所读 Coding Plan/API/条款页面未找到足以证明 Coding endpoint 有通用 backup API 或可验证备份删除接口的内容。 |
| Ark 广义服务的数据处理和存储边界 | `official-verified / scope-limited` | 专用条款说明模型服务可因合规审查、过滤、排障、产物查询、异常告警等处理/合理时间存储数据，且启用缓存、日志、监控、Managed Agents 等功能时会存入 Ark 存储；是否启用及是否适用于具体 Coding 调用仍需按产品配置确认。 |
| Coding/Agent 个人版数据授权撤回 | `official-verified / scope-limited` | 个人版数据授权协议写明授权期限为永久；终止操作可停止授权新的 AI Coding/Agent 数据，但已经使用的数据技术上无法撤回。该协议与其他 Ark 服务条款的适用范围不能由本轮自行合并解释。 |
| 账号注销、账单和资源退出 | `official-verified` | 官方账号注销页面和注销协议证明永久注销、45 天静默期、注销前迁移/备份/结清费用等事实；不能将账号相关信息删除承诺外推为所有 Provider 数据、备份或模型处理数据零残留。 |
| ZWorkbench 是否拥有 Provider 侧资源 | `human-reported / product-boundary` | 当前产品边界是不由 ZWorkbench 创建、管理或删除 Ark 侧任务、Webhook、备份、账号、项目或云资源；其退出责任 delegated to Provider/account owner，尚未进行真实远端退出操作。 |

因此，本 gate 的证据结果是：endpoint、API key 管理和供应商/账户级退出材料已有
官方事实；Coding API 的具体远端对象、Webhook/任务/备份生命周期、实际 retention
和此次账户资源清单仍不能签成“已验证退出”。当前远端删除状态为
`not-performed / not-verified`。

## 4. Coding Plan endpoint、认证与产品范围

### 4.1 Endpoint 和额度范围

**Finding `ARK-CODING-ENDPOINT-01` — `official-verified`。**

官方《Coding Plan 快速开始》的 `Base URL` 章节列出：

- Anthropic-compatible：`https://ark.cn-beijing.volces.com/api/coding`；
- OpenAI-compatible：`https://ark.cn-beijing.volces.com/api/coding/v3`；
- `https://ark.cn-beijing.volces.com/api/v3` 不消耗 Coding Plan 额度，可能产生额外 API 费用。

这证明 Coding Plan 文档公开了目标 OpenAI-compatible base URL，同时明确区分标准
Ark 数据面 URL 和 Coding Plan 额度路径；它没有证明某个本地 Harness 已经成功调用
该 endpoint，也没有证明 `/api/coding/v3` 具备标准 `/api/v3` 的全部资源接口。
[ARK-START]

### 4.2 API key 获取和注入

**Finding `ARK-CODING-AUTH-01` — `official-verified`。**

《Coding Plan 快速开始》的认证/配置说明将 API key 获取指向官方控制台。
《获取 API Key 并配置》的 `API Key`/配置章节把 API key 作为敏感凭证，并建议放入
环境变量；同页还列出可按项目、Model ID、推理接入点和 IP 限制权限。该事实支持
“认证路径是 Provider API key 的控制台凭证”，不支持把 key 值写入 ZWorkbench
配置导出、日志、回放或 backup，也不支持本轮验证某个账户实际使用了哪个 key。
[ARK-START][ARK-KEY]

### 4.3 API key 的生命周期

**Finding `ARK-CODING-AUTH-02` — `official-verified`。**

《管理 API Key》页面的 API Key 管理章节列出：可查询 key 状态、权限、最后使用时间、
创建人；可以禁用、启用和删除；删除 API Key 后不能继续使用其鉴权；API Key 与资源
项目绑定。由此可证明退出时存在 key 级撤销动作及项目归属核对点，但不能证明账号
注销会自动撤销所有 key，也不能证明 key 删除会删除已经产生的远端数据、任务、
Webhook、备份或账单记录。[ARK-KEY-MGMT]

### 4.4 Coding Plan 的适用范围

**Finding `ARK-CODING-SCOPE-01` — `official-verified / scope-limited`。**

《Coding Plan 套餐概览》的产品定位页面说明 Coding Plan 主要面向个人开发场景，
企业级开发需求应使用模型 API；Coding Plan 额度仅在 AI 编程工具中生效，不可用于
一般 API 调用；在非 AI 编程工具中使用该 Base URL/API key 可能被识别为滥用，导致
订阅停用或账号封禁。额度按 5 小时、周、月刷新，且在支持的工具间共享。

这证明官方将 Coding Plan 与一般模型 API 区分，并公开了可能停用/封禁的后果；它
不是对 ZWorkbench 是否属于“AI 编程工具”的适用性判断，也不是对个人账户能否把
该 endpoint 嵌入工作台的推荐或批准。[ARK-PLAN]

《Coding Plan 常见问题》的退订/自动续费问答说明可在费用中心退订，并要求至少在
下次扣费前 7 天取消自动续费；同页再次说明个人 Coding Plan 主要面向个人开发者，
团队协作建议使用模型 API，并提醒 Coding Plan API key/Base URL 不应在非 AI 编程
工具中使用。[ARK-FAQ]

## 5. 标准 Ark `/api/v3` 的远端对象与 Coding API 边界

以下是官方文档直接证明的标准 Ark 数据面事实。每一项都标注为
`scope-limited`，不能写成 Coding `/api/coding/v3` 已支持。

### 5.1 Response

**Finding `ARK-OBJECT-RESPONSE-01` — `official-verified / scope-limited`。**

《创建 Response》的请求章节给出标准接口 `POST /api/v3/responses`，返回 Response
对象；参数/字段包括 `store`（页面示例和字段说明中默认值为 `true`）、`expire_at`、
`previous_response_id`、`status` 等。这证明标准 `/api/v3` 有可存储的 Response 对象
和过期相关字段；未证明 Coding `/api/coding/v3` 暴露该接口或采用相同默认值。
[ARK-RESPONSE-CREATE]

**Finding `ARK-OBJECT-RESPONSE-02` — `official-verified / scope-limited`。**

《删除 Response》的接口章节给出 `DELETE /api/v3/responses/{response_id}`，返回
`deleted` 字段。这证明标准 Response 有官方删除动作；未证明删除会覆盖 Provider
内部日志、缓存、备份、账单或已用于其他处理的数据，也未证明 Coding Plan 调用生成
的对象可用该路径删除。[ARK-RESPONSE-DELETE]

### 5.2 File

**Finding `ARK-OBJECT-FILE-01` — `official-verified / scope-limited`。**

《上传文件》的上传/文件对象章节说明，文件会上传到 Ark 平台，供模型后续调用；
对象含 `file_id`、`expire_at`、TOS 信息和处理状态。该页面证明上传文件是 Provider
侧资源，并有过期/处理字段；未证明 Coding Plan endpoint 会创建同类 File，或其
具体保留期、备份复制和删除证明如何工作。[ARK-FILE-UP]

**Finding `ARK-OBJECT-FILE-02` — `official-verified / scope-limited`。**

《删除文件》的接口章节给出 `DELETE /api/v3/files/{file_id}`，并说明文件从存储空间
移除，删除后无法再用于推理且无法恢复。这证明标准 File 有不可逆的资源级删除动作；
不能把“从存储空间移除且无法恢复”扩展为 Provider 全部副本、日志、备份、法定留存
或模型处理数据均已零残留，也不能扩展到 Coding `/api/coding/v3`。[ARK-FILE-DELETE]

### 5.3 异步任务与 callback_url

**Finding `ARK-OBJECT-TASK-01` — `official-verified / scope-limited`。**

《创建视频生成任务》的接口章节给出 `POST /api/v3/contents/generations/tasks`，
响应返回任务 ID；请求参数包含 `callback_url` 和 `execution_expires_after`。这证明
标准视频生成 API 有异步任务、回调 URL 和执行过期参数。[ARK-VIDEO-TASK-CREATE]

**Finding `ARK-OBJECT-TASK-02` — `official-verified / scope-limited`。**

《取消或删除视频生成任务》的接口章节给出
`DELETE /api/v3/contents/generations/tasks/{id}`，并说明可取消排队任务或删除任务
记录。这证明该标准视频任务有官方取消/删除动作；页面没有证明这是 Coding Plan
通用任务、调度器、Webhook 或备份的统一生命周期。[ARK-VIDEO-TASK-DELETE]

### 5.4 对 Coding API 的严格限制

**Finding `ARK-CODING-OBJECT-BOUNDARY-01` — `official-unknown`。**

本轮找到的 `callback_url` 只位于标准视频生成任务页面；未找到官方 Coding Plan 页面
证明 `/api/coding/v3` 暴露通用任务、Webhook 注册/停用/删除、任务队列导出或远端
备份管理接口。故当前只能记录：

- 标准 `/api/v3` 的 Response/File/视频任务能力：`official-verified / scope-limited`；
- Coding `/api/coding/v3` 的同名或等价远端对象：`official-unknown`；
- Coding API 的通用 Webhook 生命周期：`official-unknown`；
- Coding API 的备份创建、导出、删除、retention 和最终清除证明：`official-unknown`。

“未找到”只限定在本轮核对的官方页面范围内，不是“火山方舟一定没有这些功能”。

## 6. 数据处理、授权、隐私与保留

### 6.1 Coding/Agent 个人版数据授权

**Finding `ARK-DATA-AUTH-01` — `official-verified / scope-limited`。**

《火山引擎数据授权使用协议》明确适用于 Coding Plan / Agent Plan 个人版订阅。
协议中“AI Coding/Agent 数据”包括调用期间输入与生成的文本、声音、图形、图片、
视频、软件等内容；授权目的包括机器学习/人工智能技术及模型的优化、开发、使用、
学术研究等。协议写明授权为非独家、不可转让、不可分许可（允许关联方和外包服务商
在协议范围内参与），且授权期限为永久。[ARK-DATA-AUTH]

**Finding `ARK-DATA-AUTH-02` — `official-verified / scope-limited`。**

同一协议的终止/撤回章节说明，用户可通过终止操作停止授权新的 AI Coding/Agent
数据；但已被使用的数据，协议明确称技术上无法撤回。协议还要求用户保证数据权利
来源，提示不应提供保密信息或商业秘密，个人信息原则上应避免提交。[ARK-DATA-AUTH]

这组事实只能说明该个人版授权协议写明的范围和责任，不能自行判断它是否覆盖所有
Ark 数据面、所有 Coding API 调用、某个具体账户的历史数据，或与其他产品条款发生
冲突时应如何解释。

同一页面还出现“使用本服务时应为合法成立并有效存续的法人或非法人组织”的表述，
与页面对 Coding/Agent 个人版的适用说明存在表面张力。本记录保留两项原文事实，
不作法律解释；适用性状态为 `official-verified text / human-or-legal-interpretation-required`。

### 6.2 Ark 大模型服务专用条款

**Finding `ARK-SERVICE-TERMS-01` — `official-verified / scope-limited`。**

《火山方舟大模型服务平台专用条款》（页面显示发布于 `2026-08-05`、生效于
`2026-08-11`）的数据处理条款说明：未经单独同意，不存储和使用数据训练/优化模型；
但可为合规审查、自动化过滤、排障、产物查询、异常调用告警处理而处理或在合理时间
存储数据；使用缓存、日志、AI 应用监控、可观测性、Managed Agents 等功能时，数据
会存入 Ark 提供的存储空间。[ARK-SERVICE-TERMS]

该条款同时说明，官方插件会将数据发送至插件处理；服务生成数据的准确性、合法性和
后续使用责任主要由用户承担；火山方舟可因异常使用、模型下架等情况停止服务。
这些是广义 Ark 服务条款中的官方事实，不证明本次 Coding endpoint 已启用每一项
功能，也不证明使用某一功能后存在可由 ZWorkbench 观察的删除完成信号。
[ARK-SERVICE-TERMS]

### 6.3 火山引擎隐私政策

**Finding `VE-PRIVACY-01` — `official-verified / scope-limited`。**

《火山引擎隐私政策》（页面显示生效于 `2024-06-21`）说明：中国大陆服务收集产生
的用户个人信息存储于中国大陆；个人信息原则上仅在提供服务所需期间保留，判断因素
包括提供服务、交易、系统安全、投诉/排障以及法律/合同义务等。[VE-PRIVACY]

**Finding `VE-PRIVACY-02` — `official-verified / scope-limited`。**

同一隐私政策的客户数据/退出相关章节说明：客户数据由用户完全拥有，平台原则上按
用户指示处理；客户数据来源、内容以及其中个人信息的合法性责任由用户承担；注销
账号后停止服务并删除或匿名化账号相关信息，但法律要求留存的除外。政策还说明撤回
授权不影响此前已经进行的处理，并对备份磁带等不切实际请求保留拒绝响应的权利；
用户可通过在线客服、控制台工单、热线等渠道处理请求。[VE-PRIVACY]

这里的“账号相关信息”不能改写成“所有 prompt/output/file/log/backup 已删除”。
政策中的“法律要求留存”、此前处理不受撤回影响、备份磁带请求例外，均使最终零残留
不能仅凭账号注销事实推出。

### 6.4 官方未找到的具体 retention 证据

**Finding `ARK-RETENTION-UNKNOWN-01` — `official-unknown`。**

本轮未找到一份同时明确绑定到
`https://ark.cn-beijing.volces.com/api/coding/v3` 的官方页面，能给出以下每项的
具体期限、对象清单和最终删除证明：

- Coding request/response 的服务端日志、缓存、可观测性记录和人工排障副本；
- Coding Plan 任务、Webhook payload、队列记录和失败重试记录；
- Provider/账户侧备份、快照、归档和灾备副本；
- 已停止授权但此前已被使用的数据；
- 账单、发票、税务和法定留存副本的删除/到期时间。

广义条款和隐私政策已证明存在处理、合理时间存储、法律保留和授权撤回限制；它们
没有为本次 Coding endpoint 提供一个可由 ZWorkbench 验证的逐对象 retention ledger。

## 7. API key、套餐、账单与账号退出

### 7.1 API key 退出

官方“管理 API Key”页面证明的最小退出动作是：确认 key 所属资源项目和权限，停止
使用后执行禁用或删除，并保留脱敏的状态/时间/操作者证据。页面没有证明：

- 删除 key 自动取消已排队任务；
- 删除 key 自动撤销 Webhook、插件、备份或其他项目成员权限；
- 删除 key 自动删除 Provider 已保存数据；
- 账号注销前是否系统性列举所有 key。

上述四项均为 `official-unknown`，不能以 API key 删除动作补齐。[ARK-KEY-MGMT]

### 7.2 Coding Plan 退订和自动续费

**Finding `ARK-BILLING-01` — `official-verified / scope-limited`。**

《Coding Plan 常见问题》的费用/订阅问答说明可在费用中心退订；取消自动续费应至少
在下次扣费前 7 天操作。该页面证明套餐订阅层面的停止入口和时间要求，不证明退订会
删除 prompt/output/file/task/Webhook/backup，也不证明历史账单和发票可立即删除。
[ARK-FAQ]

### 7.3 账号注销

**Finding `VE-ACCOUNT-EXIT-01` — `official-verified`。**

官方《账号注销》页面的注销流程和风险提示说明：账号注销是永久操作；页面警告数据、
资源、余额、账单和发票会被删除且无法恢复；提交注销后进入 45 天静默期，静默期内
不能登录或新购，期满自动完成注销；注销前需要处理欠费、域名、实例等必须处理事项。
页面还要求注销前导出并备份业务数据、存储文件、数据库备份、快照、历史账单/订单/发票。
[VE-ACCOUNT-CANCEL]

**Finding `VE-ACCOUNT-EXIT-02` — `official-verified`。**

《火山引擎账号注销协议》的注销前/静默期/责任章节说明：注销前需迁出或备份数据并
删除 API key，结清欠费、待付费用、余额、订单/权益等，并解除第三方绑定、生态伙伴
或组织关系；静默期内不能使用服务，官方不提供数据恢复/找回；注销完成后，法律/税务
等规定要求保留的信息可能继续保留；注销不免除注销前行为及责任。[VE-ACCOUNT-AGREE]

这证明账号所有者承担注销前的导出、备份、费用结清、key 删除、第三方解绑和历史
责任；不能将“永久注销”理解为所有远端数据、备份、法定留存或已使用数据均可由
ZWorkbench 观察到零残留。

### 7.4 通用火山引擎服务条款

**Finding `VE-SERVICE-TERMS-01` — `official-verified / scope-limited`。**

《火山引擎服务条款》的账号/客户数据/违约处置章节说明：账号注销后无法使用，账号
记录、功能等无法恢复；用户负责客户数据保护与备份；发生违规时火山引擎可停止传输、
删除内容并保存记录；用户还需同时遵守适用的产品协议。[VE-SERVICE-TERMS]

该页面证明客户备份责任、账号不可恢复和供应商处置权；它没有提供 Coding `/api/coding/v3`
逐对象的删除 API、备份 retention 或“注销后全部数据清除”保证。

## 8. 退出与责任矩阵

这里的“责任”区分 ZWorkbench 本地调用边界、Provider/账户所有者的外部资源边界，
以及条款中已经明确的用户数据和历史行为责任。它不是替任何一方签署合同或分配
法律责任。

| 对象/动作 | 官方已证明的事实 | 当前责任归属 | 当前状态 |
|---|---|---|---|
| Coding endpoint | `/api/coding/v3` 是官方 Coding Plan OpenAI-compatible base URL | 调用方负责确认实际 endpoint、区域、项目和套餐适用性 | `official-verified`; 实际连接 `human-reported` |
| API key | 可创建/查询/禁用/启用/删除；删除后不能继续鉴权；key 绑定项目 | 账户所有者/项目管理员执行撤销；ZWorkbench 不持有 key 值 | `official-verified`; 此账户动作未执行 |
| API key 中已产生的数据 | 官方没有证明删除 key 会删除数据或任务 | Provider/账户所有者按实际对象和政策核对 | `official-unknown` |
| Response/File/标准视频任务 | `/api/v3` 各有创建/删除或取消页面 | 使用这些标准资源的账户/项目 owner 负责逐对象退出 | `official-verified / scope-limited` |
| Coding 请求/响应对象 | 未找到 Coding endpoint 对应对象级删除契约 | Provider/账户 owner；ZWorkbench 不宣称代删 | `official-unknown` |
| Coding 任务/Webhook | 只证明标准视频任务有 callback_url 和删除/取消；未证明 Coding 通用生命周期 | 真实资源 owner 需在 Ark 控制台/官方支持路径确认 | `official-unknown`; Human 报告存在 |
| Coding/Provider 备份 | 未找到 Coding 备份 API、导出、删除和 retention 证据 | 账户/备份责任人和 Provider；ZWorkbench 不代管 | `official-unknown`; Human 报告存在 |
| 数据授权/撤回 | 个人 Coding/Agent 协议写明停止新数据授权；已使用数据技术上无法撤回 | 数据提供者/账户 owner 负责输入合法性和退出判断；Provider 按协议处理 | `official-verified / scope-limited` |
| Prompt、私有代码、个人信息 | 官方条款/隐私政策将数据合法性、个人信息和客户数据责任置于用户/客户侧，并提示不要提交保密信息 | 实际提交者/账户 owner 与数据负责人 | `official-verified`; 本次数据范围未盘点 |
| 套餐订阅/自动续费 | 费用中心退订；自动续费至少提前 7 天取消 | 订阅/账单 owner | `official-verified`; 未执行 |
| 账单/发票/税务 | 账号注销页面要求注销前导出；注销协议允许法律/税务留存 | 账单 owner、账户 owner 和 Provider 按留存规则处理 | `official-verified`; 具体期限 unknown |
| 账号注销 | 永久操作、45 天静默期、注销前需处理欠费/资源并导出备份；静默期不恢复数据 | 账户所有者/组织管理员 | `official-verified`; 未执行 |
| ZWorkbench local owner | W8 产品边界中只负责本地 run、停止新请求、凭证不落盘和本地 evidence；不创建/管理/删除 Ark 侧资源 | ZWorkbench composition owner/维护者 | `human-reported / product-boundary` |
| Provider 侧最终零残留 | 官方政策包含法律留存、此前处理不受撤回影响、备份请求例外 | Provider/账户 owner；不可由本地 fixture 证明 | `official-unknown / not-verified` |

## 9. 当前 unknown register

以下条目在本轮保留为 `official-unknown`，不以“控制台没看到”或“API key 已删除”
作为反证：

1. `/api/coding/v3` 的完整 endpoint 参考、请求/响应对象清单和对象级删除接口，是否
   与标准 `/api/v3` 不同或受 Coding Plan 工具约束。
2. Coding Plan 是否创建可独立列举的远端 task、run、queue、scheduler、retry 或
   workflow；它们的取消、删除、过期、导出和审计记录入口。
3. Coding Plan 通用 Webhook/integration 的创建、签名、停用、删除、重试和 payload
   retention；标准视频任务 `callback_url` 不能填补该项。
4. Coding 请求/响应、缓存、日志、可观测性、插件处理副本和排障副本的逐对象保留期、
   访问主体、导出接口和删除完成证明。
5. Provider/账户侧备份、快照、灾备副本、备份加密、恢复入口、retention 到期和删除
   证明；包括 Human 报告的“备份”具体属于哪个 Ark 产品。
6. “终止个人版数据授权”与“已使用数据技术上无法撤回”在具体数据类型、账户注销、
   模型优化和历史日志之间的实际映射。
7. 账号注销是否自动处理所有 API key、项目、Endpoint、任务、Webhook、插件授权和
   备份；官方注销页面要求用户主动删除/迁出/解绑，未给出一份对象级自动化清单。
8. 账单、订单、发票、税务、法定留存以及供应商备份的具体最长期限；注销页面的
   “删除且无法恢复”与法律/税务留存例外需按具体账户和适用条款核对。
9. 目标个人账户的真实地区、项目/组织、计费主体、资源 ID、key fingerprint、已发送
   数据类别和实际启用的 Ark 功能；本记录不读取控制台，也不使用凭证。

### 9.1 不应作出的负面结论

- 不能说“Coding API 没有任务、Webhook 或备份”，只能说本轮官方来源未证明其通用
  生命周期。
- 不能说“账号注销后远端数据全部删除”，只能记录账号注销、账号相关信息处理、法定
  留存和此前已处理数据之间的官方文字边界。
- 不能说“删除 API key 就完成退出”，它只证明该 key 不能继续鉴权。
- 不能说“标准 `/api/v3` 删除 Response/File/视频任务就能删除 Coding `/api/coding/v3`
  数据”。
- 不能说“本地 backup/restore pass 就证明 Provider 远端 backup 可恢复或可删除”。
- 不能说“OpenAI-compatible”意味着遵循 OpenAI 的合同、资源模型、Webhook、账单或
  退出流程；本记录的合同主体是火山引擎/火山方舟官方材料。

## 10. W8 1-6 证据结论

`official-verified` 的最小集合：

- Coding Plan 的 OpenAI-compatible endpoint 和与标准 `/api/v3` 的额度区分；
- API key 的控制台获取、敏感凭证属性、权限约束和禁用/启用/删除生命周期；
- 标准 Ark `/api/v3` 的 Response、File、视频生成任务以及相应对象级删除/取消页面；
- 个人 Coding/Agent 数据授权协议关于数据范围、永久授权、新数据停止和已使用数据
  无法技术撤回的文字；
- Ark 专用条款、火山引擎隐私政策、服务条款关于处理、存储、用户责任、法律留存、
  账号注销和供应商处置权的文字；
- Coding Plan 退订/自动续费、火山引擎账号注销和注销前数据/账单/凭证处理要求。

仍为 `official-unknown` 或未核实的关键集合：

- 目标 Coding endpoint 的实际远端对象及其逐对象退出接口；
- 通用 Coding 任务、Webhook、备份和 retention 生命周期；
- 目标个人账户中确实存在的资源、数据范围、组织/项目和账单状态；
- Provider 侧最终零残留和可复核删除完成证明。

当前本记录的退出责任结论是：ZWorkbench 可记录并约束自己的本地调用边界，但不
应宣称拥有 Ark 侧任务、Webhook、备份、账号或云资源；这些对象的真实清单、停用、
删除、保留和账单收尾属于 Provider/账户/项目责任人的外部操作。该产品边界是
`delegated-to-provider/account-owner`，Provider 侧删除状态是
`not-performed / not-verified`。

## 11. 官方一手来源索引

以下 URL 均为火山引擎/火山方舟官方文档或官方政策页面。页面内容可能更新；重新
审计时应记录新的页面标题、发布日期/生效日和核查日期。

### Coding Plan、认证和账单

- **[ARK-START] Coding Plan 快速开始** — [官方页面](https://www.volcengine.com/docs/82379/1928261?lang=zh)。核对章节：`Base URL`、认证/快速配置；页面事实：列出 Anthropic-compatible `/api/coding`、OpenAI-compatible `/api/coding/v3`、标准 `/api/v3` 的额度/费用区别，并指向控制台 API key。
- **[ARK-PLAN] Coding Plan 套餐概览** — [官方页面](https://www.volcengine.com/docs/82379/1925114?lang=zh)。核对章节：产品定位、额度和使用限制；页面事实：主要面向个人开发场景，企业需求使用模型 API，额度仅适用于 AI 编程工具，并说明非 AI 编程工具使用可能导致停用/封禁。
- **[ARK-CLI] Ark CLI：Coding Plan 个人版使用指南** — [官方页面](https://www.volcengine.com/docs/82379/2656115?lang=zh)。核对章节：`arkcli auth login`、`auth status`、Helper、套餐/模型/用量管理；页面事实：列出 Ark CLI 个人版认证和工具配置入口。
- **[ARK-KEY] 获取 API Key 并配置** — [官方页面](https://www.volcengine.com/docs/82379/1541594?lang=zh)。核对章节：`API Key`、权限和配置；页面事实：API key 是敏感凭证，推荐环境变量，可按项目、Model ID、推理接入点、IP 限制权限。
- **[ARK-KEY-MGMT] 管理 API Key** — [官方页面](https://www.volcengine.com/docs/82379/1361424?lang=zh)。核对章节：状态、权限、最后使用时间、创建人以及禁用/启用/删除；页面事实：删除后不能继续用该 key 鉴权，key 与资源项目绑定。
- **[ARK-FAQ] Coding Plan 常见问题** — [官方页面](https://www.volcengine.com/docs/82379/2165245?lang=zh)。核对章节：退订/自动续费、个人版定位和使用边界；页面事实：费用中心退订，自动续费至少提前 7 天取消，并提醒 Coding Plan key/Base URL 不应在非 AI 编程工具中使用。

### 标准 Ark 数据面对象（不外推到 Coding API）

- **[ARK-BASE] Base URL 及鉴权** — [官方页面](https://www.volcengine.com/docs/82379/1298459?lang=zh)。核对章节：数据面/管控面、标准数据面 `/api/v3`、API Key 与 Access Key 鉴权。
- **[ARK-RESPONSE-CREATE] 创建 Response** — [官方页面](https://www.volcengine.com/docs/82379/1569618?lang=zh)。核对章节：标准接口、`store`、`expire_at`、`previous_response_id`、`status`；页面事实：`POST /api/v3/responses`。
- **[ARK-RESPONSE-DELETE] 删除 Response** — [官方页面](https://www.volcengine.com/docs/82379/1584286?lang=zh)。核对章节：删除接口和响应；页面事实：`DELETE /api/v3/responses/{response_id}`，返回 `deleted`。
- **[ARK-FILE-UP] 上传文件** — [官方页面](https://www.volcengine.com/docs/82379/1870405?lang=zh)。核对章节：上传/文件对象；页面事实：文件上传至 Ark 平台供后续调用，含 `file_id`、`expire_at`、TOS 和处理状态。
- **[ARK-FILE-DELETE] 删除文件** — [官方页面](https://www.volcengine.com/docs/82379/1870408?lang=zh)。核对章节：删除接口和结果；页面事实：`DELETE /api/v3/files/{file_id}`，移出存储空间，删除后不能再推理且无法恢复。
- **[ARK-VIDEO-TASK-CREATE] 创建视频生成任务** — [官方页面](https://www.volcengine.com/docs/82379/1520757?lang=zh)。核对章节：任务创建参数/响应；页面事实：`POST /api/v3/contents/generations/tasks`，返回任务 ID，包含 `callback_url`、`execution_expires_after`。
- **[ARK-VIDEO-TASK-DELETE] 取消或删除视频生成任务** — [官方页面](https://www.volcengine.com/docs/82379/1521720?lang=zh)。核对章节：任务取消/删除；页面事实：`DELETE /api/v3/contents/generations/tasks/{id}`，可取消排队任务或删除任务记录。

### 数据处理、隐私、账号和退出

- **[ARK-DATA-AUTH] 火山引擎数据授权使用协议** — [官方页面](https://www.volcengine.com/docs/82379/1928265?lang=zh)。核对章节：适用范围、`AI Coding/Agent 数据`、授权目的、授权期限、终止/撤回、用户数据责任；页面事实：个人版适用说明、永久授权、停止新数据授权、已使用数据技术上无法撤回，并包含数据合法性/保密信息提示。
- **[ARK-SERVICE-TERMS] 火山方舟大模型服务平台专用条款** — [官方页面](https://www.volcengine.com/docs/82379/1104498?lang=zh)。核对章节：数据处理/存储、缓存/日志/监控/Managed Agents、插件和生成数据责任、停止服务；页面显示发布于 `2026-08-05`、生效于 `2026-08-11`。
- **[VE-PRIVACY] 火山引擎隐私政策** — [官方页面](https://www.volcengine.com/docs/6256/64902?lang=zh)。核对章节：中国大陆存储、保留期限因素、客户数据、账号注销、撤回授权、备份磁带请求和申诉/请求渠道；页面显示生效于 `2024-06-21`。
- **[VE-SERVICE-TERMS] 火山引擎服务条款** — [官方页面](https://www.volcengine.com/docs/6256/64903?lang=zh)。核对章节：账号注销、客户数据保护/备份、违规处置、产品协议关系；页面显示发布/生效于 `2024-06`。
- **[VE-ACCOUNT-CANCEL] 账号注销** — [官方页面](https://www.volcengine.com/docs/6256/64928?lang=zh)。核对章节：注销条件、45 天静默期、注销后果和注销前备份/导出；页面事实：永久注销、数据/资源/余额/账单/发票删除且无法恢复、静默期不能登录或新购。
- **[VE-ACCOUNT-AGREE] 火山引擎账号注销协议** — [官方页面](https://www.volcengine.com/docs/6256/157919?lang=zh)。核对章节：注销前迁出/备份、删除 API key、结清费用、解除绑定、静默期、法律/税务留存和注销前责任；页面事实：不提供静默期数据恢复/找回，法律/税务要求的信息可能继续保留。

## 12. 本轮操作声明

- 未执行任何带认证的 `https://ark.cn-beijing.volces.com/api/coding/v3` 业务请求，未发送 Prompt、代码、文件或用户数据；本轮曾对该 endpoint 发起一次未携带凭证的 `GET /`，服务端返回 `401 AuthenticationError`。该观察只作为 `non-evidence / boundary incident`，不计入任何 Provider 能力或退出结论。
- 未读取、粘贴、验证、保存或使用任何 API key、Access Key、Cookie、OAuth/session。
- 未在控制台执行退订、停用、删除、导出、注销或 Webhook/任务/备份操作。
- 本文件中的远端资源存在性、个人账户范围和实际接入信息，只有明确标记为
  `human-reported` 的部分来自 Human；其余结论均按官方来源 scope 限定。
