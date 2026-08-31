# W7 Codex C7 真实远端退出责任包

状态：`product-boundary-defined / externally-delegated / signoff-open` · 日期：`2026-08-31`
适用范围：Codex `0.139.0` + 一个 SQLite composition owner · `acceptance/evaluation`

本文解决的不是“删除本地 fixture 文件”，而是：当 ZWorkbench 真实接入远端
Provider、账户、调度、备份或第三方项目后，谁负责停止、撤销、删除、核对和承担
供应商 retention。本文目前只建立清单和人工 runbook，不执行任何真实远端操作，
也不是法律、隐私、数据保护或供应商合同意见。

## 1. 当前事实边界

| 对象 | 当前状态 | 不能推出的结论 |
|---|---|---|
| C7 loopback fixture Provider | `observed-case-local-only` | 不证明真实 OpenAI/其他 Provider 账户没有数据 |
| composition owner SQLite、case workspace、case `CODEX_HOME` | 已有本机 export/delete machine contract | 不证明远端 backup、组织 retention 或账户数据已删除 |
| npm registry、GitHub source/release/attestation URL | 本轮只读证据来源 | 不属于 ZWorkbench 用户资源，也不需要在本轮删除 |
| OpenAI/其他 Provider 账户、API key、OAuth/session、组织、账单 | `unknown / human-inventory-required` | 不能假设不存在，也不能假设某个个人或企业条款适用 |
| 远端 prompt/output/file/log/telemetry、任务、webhook、backup | `unknown / human-inventory-required` | 不能由 loopback 运行或本地日志推断远端 retention |
| 火山方舟个人 API 账户 | `human-reported / externally-owned`；endpoint 为 `ark.cn-beijing.volces.com/api/coding/v3`，用户确认有远端数据、任务、Webhook 和备份 | ZWorkbench 不创建或管理这些资源；Provider/账户所有者负责其控制台、删除入口、retention、账单和责任人 |

真实退出的起点不是执行 `delete`，而是由账户所有者或明确授权管理员确认：本次
实际使用了哪个账户、哪个 Provider、哪个地区/组织、传输了哪些数据、创建了哪些
资源，以及保留和删除规则在哪里。

## 2. 远端资源责任清单

以下表格是每次真实退出前必须填写的 inventory。`resource_id` 只填控制台 ID、
项目 ID 或脱敏 fingerprint，不填 token、API key、cookie、完整 email 或私有代码。

| 类别 | 可能资源/触发来源 | 要记录的数据 | 删除/撤销动作 | 第一责任人 | 当前状态 |
|---|---|---|---|---|---|
| 认证身份 | ChatGPT 登录、API key、OAuth/session、service account | 认证路径、账户/组织标识、key fingerprint、创建者 | 注销 session、撤销 key/token、移除成员/权限 | 账户所有者/组织管理员 | `unknown` |
| Provider 数据 | prompt、output、上传文件、缓存、请求日志、usage | 数据类别、时间范围、项目/组织、是否含私有代码/个人数据 | 按供应商入口删除/导出/关闭数据功能；记录响应 ID | Provider 账户管理员 + 数据负责人 | `unknown` |
| 火山方舟 Provider 数据 | 由用户确认存在；具体数据对象待账户所有者确认 | request/output/file/log/usage 的实际范围、时间、项目和敏感数据类别 | 由账户所有者按火山方舟对应控制台/API/支持流程处理；不是 ZWorkbench 的删除动作 | 个人账户所有者 + 数据负责人 | `externally-owned / delegated` |
| 远端任务 | scheduler、queue、workflow、agent run、CI/CD job | job/run ID、schedule、未来触发时间、owner | 先停用未来触发，再取消/删除未完成 run | 任务 owner | `unknown` |
| webhook/integration | webhook、GitHub/GitLab app、Slack/邮件、MCP/connector | integration ID、回调目标、权限范围、secret fingerprint | 删除 webhook/app 授权，轮换相关 secret | 集成 owner | `unknown` |
| 火山方舟任务/Webhook/备份 | 用户确认存在，但不是由 ZWorkbench 创建或管理 | task/job ID、schedule、webhook/integration ID、backup ID、retention | 由账户所有者/Provider 责任人按其自身流程处理；ZWorkbench 不执行跨系统删除 | 账户所有者 + Provider 任务/备份责任人 | `externally-owned / delegated` |
| 远端 backup/retention | object storage、Provider backup、组织归档、快照 | backup ID、位置、加密/访问者、retention/deletion policy | 删除或提交 retention 删除请求；记录不可立即删除的到期时间 | 备份/数据 owner | `unknown` |
| 发布与制品 | registry package、容器、CI artifact、下载链接 | artifact/version/digest、发布者、公开范围 | 撤回/删除（如允许），撤销发布权限；保留必要 provenance | 发布 owner | `not-in-scope-unless-published` |
| 账单与组织 | subscription、API project、预算、付款、seat | org/project/billing ID、未结费用、seat、合同联系人 | 取消订阅/项目/seat；确认不会因删除丢失发票责任 | 组织/账单 owner | `unknown` |
| 第三方项目权限 | repository、cloud project、local network target | project/repo ID、scope、bot/user 权限 | 移除 app/member/token，核对审计记录 | 项目 owner | `unknown` |

### 2.1 认证路径必须单独记账

不能写“Codex 已退出”而不写认证路径。至少选择并记录实际使用的一个或多个：

| 路径 | 退出审查重点 |
|---|---|
| ChatGPT/个人服务登录 | 个人服务条款、账号 session、个人 workspace 数据、共享/自动化边界 |
| OpenAI API key / project | API project、key、组织权限、请求数据/日志、usage/billing、数据处理条款 |
| 企业/团队 Provider 账户 | 组织管理员、成员/seat、合同/DPA、审计/retention、离职或项目移交 |
| 其他 Provider | 该 Provider 自身的条款、API key、数据删除和 retention 证据 |
| 纯本地模型/无远端 Provider | 只需证明无外部网络、无远端账户/数据写入；不能把本地数据删除冒充远端退出 |

如果无法确定实际路径，状态就是 `unknown`，不得执行批量删除，也不得签 C7。

### 2.2 本项目实际拥有的退出范围

当前明确的产品边界是：ZWorkbench 不在火山方舟或其他 Provider 侧创建、管理或删除
任务、Webhook、备份、云资源、账户或 project。它只是使用用户提供的 API endpoint
发起请求。因此本项目不要求把火山方舟的每个远端资源 ID 交给 ZWorkbench，也不把
Provider 侧“已删除”伪装成项目自己的测试结果。

ZWorkbench 必须负责的，是本地和调用边界：

- 停止本地 run、schedule、retry 和新的 Provider 请求；
- 不把 API key 值写入配置导出、日志、回放或 backup，只保存必要的引用/fingerprint；
- 对发送到 Provider 的数据做明确的边界提示和最小化控制；
- 删除本地 composition state、缓存、export 和 key 引用；
- 向账户所有者明确说明：Provider 侧数据、备份、账单和 retention 由其账户/供应商
  责任人处理，ZWorkbench 不承诺远端零残留。

只有当未来版本开始替用户创建或代管远端资源，才需要重新打开本节的资源级 inventory
和真实删除演练。

## 3. 人工执行顺序

这些步骤只能由账户所有者或有明确授权的管理员在场完成。Agent 可以协助读取
脱敏清单和保存证据，但不代持凭证、不猜账户、不代点不可逆删除。

### A. 冻结新写入

1. 停止 ZWorkbench 新 run、schedule delivery、retry 和 webhook 触发。
2. 记录冻结时间、当前 run IDs、composition owner state digest 和最后一次 Provider
   请求时间。
3. 发现仍有活动 run、未知 worker 或未来 schedule 时，先 `safe-stop`，不进入删除。

### B. 建立资源清单和恢复窗口

1. 账户所有者在对应 Provider/组织控制台确认账户、组织、项目和地区。
2. 按第 2 节逐项登记资源 ID、数据类别、创建来源、责任人和删除入口。
3. 记录需要保留的合规/账单/审计材料、恢复窗口和 Provider 规定的 retention；不把
   “控制台没有看到”当作“没有远端数据”。
4. 保存脱敏 inventory 快照；任何 token、API key、cookie 或私有内容不得进入日志。

### C. 导出最小必要材料

在删除前只导出继续承担责任所需的最小材料：candidate/version/commit、composition
schema、run/event/result/replay metadata、资源 ID、删除请求号和责任人。对 prompt、
私有代码、个人数据和 secret 默认脱敏；导出物必须有 digest、存放位置、访问范围和
到期删除时间。

### D. 停用远端活动资源

按资源清单逐项停用：未来 schedule、队列、workflow、CI job、webhook、connector、
bot/app 权限。停用后重新列举，确认不会产生新的 Provider 写入或自动重建资源。

### E. 删除远端数据和备份

1. 依据实际 Provider/组织 runbook 删除或提交删除请求；不得把一个 Provider 的命令
   套用到另一个 Provider。
2. 若删除动作会同时撤销唯一管理凭证，先确认仍有已授权的恢复/支持路径；若没有，
   `safe-stop`。
3. 记录每项动作的时间、控制台/API 操作结果、请求/工单 ID、操作者和返回状态。
4. 对无法立即删除、供应商备份、法律保留或账单记录，记录政策来源、预计到期时间、
   责任人和下一次复核日期；不得写成“零残留”。

### F. 撤销凭证和第三方权限

在确认数据删除/retention 请求已提交且没有必要的管理操作后，撤销 API key、OAuth
token、session、service account、repository/cloud permissions，并核对审计日志中
没有新的使用。只保存 key fingerprint 和撤销结果，不保存 secret 本身。

### G. 本地收尾与退出签核

1. 按现有 owner-backed runbook 删除 local export/import、composition DB 副本、case
   `CODEX_HOME` 和临时 workspace；保存删除前后清单。
2. 复核 Provider、组织、backup、billing、webhook、第三方项目的状态；每项必须是
   `revoked/deleted/retained-with-policy/explicitly-not-in-scope`，不能是 `unknown`。
3. 由账户/数据/备份/项目责任人分别签名；同一人在个人项目中可以兼任多个角色，但
   角色不能省略。

## 4. 责任人与证据模板

每个真实远端资源至少绑定以下责任角色：

| 角色 | 责任 |
|---|---|
| 账户/组织 owner | 确认真实账户、授权管理员、组织和地区；执行控制台级操作 |
| Provider/data owner | 确认发送的数据类型、删除入口、retention 和供应商响应 |
| Composition owner | 冻结 run、停止重试/调度、导出本地 ledger、证明没有新写入 |
| Backup/retention owner | 处理远端备份、快照、归档和不可立即删除的期限 |
| Project/integration owner | 撤销 webhook、仓库、云项目、connector 和 bot 权限 |
| Maintainer | 保存脱敏证据、更新状态、报告残余风险，不代替法律签核 |

单项操作记录模板：

```text
exit_run_id:
operator:
authorization_reference:
provider_and_account_path:
region_or_org:
resource_category:
resource_id_or_fingerprint:
data_categories:
created_by_or_trigger:
action: suspend | revoke | delete | retention-request | verify | not-in-scope
T_start:
T_end:
provider_request_or_ticket_id:
before_snapshot_digest:
after_snapshot_or_response_digest:
retention_exception_and_due_date:
verification_method:
result: deleted | revoked | retained-with-policy | not-in-scope | unknown
operator_notes:
```

不得以 `unknown` 作为最终退出结果。若供应商只承诺延迟删除或无法提供可观察的
最终清除证明，最终结果应为 `retained-with-policy`，并附政策来源、期限和责任人。

## 5. Safe-stop 条件

出现以下任一情况，暂停当前项并保留证据：

- 账户、组织、地区、Provider 或认证路径无法确认；
- 资源 ID、数据范围、责任人或删除入口不明确；
- 只有个人权限但目标资源属于团队/组织，或授权范围不足；
- 没有可恢复的删除前导出、恢复窗口或供应商支持路径；
- 发现未知 schedule、worker、webhook、API key 或新的 Provider 写入；
- Provider 的删除/retention 结果无法观察，或实际结果与政策不一致；
- 需要把 token、API key、cookie、私有代码或个人数据复制到 evidence；
- 删除动作会影响其他用户、生产项目、账单、法定留存或第三方资源，且没有明确授权。

Safe-stop 不是失败，也不是“没有资源”；它的结果应为 `unknown/stop`，等待账户
所有者或责任人补充事实。

## 6. C7 关闭条件

### 6.1 当前产品边界的关闭条件

对当前 ZWorkbench 产品范围，远端资源生命周期不是 ZWorkbench 自有的 C7 操作门。
要关闭“产品是否承担远端删除”的边界问题，只需确认：

1. ZWorkbench 不创建、不管理、不删除 Provider 侧任务、Webhook、备份、云资源、账户
   或 project；
2. ZWorkbench 能停止本地 run、schedule、retry 和新的 Provider 请求；
3. API key 值不进入配置导出、日志、回放或 backup，只保存必要的引用/fingerprint；
4. 产品文档明确说明数据会离开本地边界，Provider 侧数据、备份、账单和 retention
   由账户所有者/供应商负责，ZWorkbench 不承诺 Provider 侧零残留；
5. 未来一旦开始代管或自动创建远端资源，重新打开第 2 节资源级 inventory 和真实
   删除演练。

这些条件满足后，产品层可将 `remote_resource_lifecycle` 标记为
`delegated-to-provider/account-owner`。这不等于 Provider 侧数据已删除，也不替代
账户所有者自己的退出、合同、隐私或 retention 判断。

### 6.2 账户所有者主动退出 Provider 的条件

如果用户另外要退出自己的火山方舟账户，则仍需账户 owner/admin 完成资源级清单：
实际账户、数据、任务、Webhook、备份、账单和 retention 各有 action、责任人、时间、
结果和证据。无法观察最终清除时，应记录 `retained-with-policy` 及政策来源和到期日，
不能写成“零残留”。这是一项独立的账户退出审计，不是当前 ZWorkbench 产品实现的
前置输入。

当前结论：`remote_resource_lifecycle = delegated-to-provider/account-owner`；
`provider_side_deletion = not-performed/not-verified`。本文件完成的是产品责任边界
和账户退出准备，不是远端删除证明；C7/G7 仍因其他未签核门保持 `unknown/stop`。

## 7. 当前已确认的 Provider/认证事实

根据当前工作台信息，先记录以下事实：

| 字段 | 当前值 | 解释 |
|---|---|---|
| Provider 接入协议 | 多个模型厂商的 OpenAI-compatible API；已确认火山方舟 endpoint `https://ark.cn-beijing.volces.com/api/coding/v3` | 这是传输/请求协议兼容，不是统一的合同主体、账户或删除入口 |
| Provider 数量 | `one-confirmed / broader-set-unresolved`；当前确认火山方舟 | 配置上按厂商和 endpoint 分开记录；退出动作由各 Provider/账户所有者负责，不能合并撤销 |
| 认证方式 | 火山方舟使用该厂商 API key；其他厂商仍待确认 | 只记录 key fingerprint，不记录 key 值 |
| 账户范围 | 火山方舟：`personal`；其他厂商：未确认 | 不能把一个厂商的账户范围外推给其他厂商 |
| 地区、组织、project、账单、retention | 火山方舟 endpoint 含 `cn-beijing`；账户/数据地区及其余字段仍 `unknown` | 需要账户 owner 在对应控制台确认，endpoint 地名不等于完整数据/合同地区结论 |
| ZWorkbench 对远端资源的所有权 | 不创建、不管理火山方舟侧任务、Webhook、备份或云资源 | ZWorkbench 只负责本地调用生命周期和数据边界；Provider 侧资源退出由账户所有者负责 |
| 远端资源存在性 | 火山方舟：用户报告数据、任务、Webhook、备份均存在 | `human-reported / externally-owned`；本项目不以本地删除证明远端零残留 |
| 当前 fixture 远端状态 | `none-observed` | fixture 使用 loopback fake Provider；不代表真实工作台远端没有资源 |

如果未来要审计账户所有者自己的 Provider 退出，账户 owner/admin 可填写每个厂商一行；
这不是当前 ZWorkbench 产品实现的前置输入：

| 厂商 | endpoint host（不含 secret） | 账户范围 | org/project | 地区 | key fingerprint | 数据/retention | 账单 owner | 退出责任人 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| 火山方舟 | `ark.cn-beijing.volces.com/api/coding/v3` | 个人 | 待确认 | endpoint 为 cn-beijing；账户/数据地区待确认 | 仅记录 fingerprint | 数据、任务、Webhook、备份：用户报告存在；retention 由账户所有者确认 | 待确认 | 个人账户所有者 | `externally-owned / delegated` |
| 其他模型厂商 | 待确认 | 待确认 | 待确认 | 待确认 | 待填写 | 待确认 | 待确认 | 待确认 | `unknown` |

只提供厂商名称、endpoint 的 hostname、账户类别和脱敏 ID 即可；不要提供 API key、
密码、Cookie、完整账户邮箱或私有请求内容。ZWorkbench 不执行“批量注销所有 Provider”，
也不能把 `OpenAI-compatible` 当成 OpenAI 服务条款或统一退出流程。只有用户明确要
退出个人 Provider 账户时，才需要账户所有者继续填写资源级清单。

## 8. 关联证据

- [`w7-codex-c7-findings.md`](./w7-codex-c7-findings.md)
- [`w7-codex-c7-single-operator-runbook.md`](./w7-codex-c7-single-operator-runbook.md)
- [`w7-codex-c7-primary-sources.md`](./research/w7-codex-c7-primary-sources.md)
- [`w7-codex-c7-notice-commercial-boundary.md`](./research/w7-codex-c7-notice-commercial-boundary.md)
