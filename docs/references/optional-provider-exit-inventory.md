# 可选：Provider 与远端退出 inventory

状态：`reference-only / on-demand / out-of-roadmap`

本文是给一次具体 Provider 账户填写的脱敏清单，不是 W8 产品目标节点、远端删除脚本，也不是法律/隐私
签核。当前目标账户是用户报告的火山方舟个人账户；所有未确认字段保留为
`unknown`，不能用“控制台没看到”填成 `none`。

## 0. 使用只读脱敏 receipt wizard

需要由账户 owner 盘点当前 Provider 状态时，运行：

```bash
./scripts/optional-provider-exit.sh
```

该 wizard 只打开官方控制台、收集当前状态和 SHA-256 fingerprint，并生成
`evaluation/evidence/provider-exit/<timestamp>-<pid>/receipt.json`。它是只读流程：不读取
API key、不调用 Provider API、不执行删除/停用/退订/注销，也没有 Provider-side action
阶段或 action 确认。账户保持 `active` 完全可以；若状态未知，receipt 保留
`unknown/safe-stop`。

重要安全边界：本 wizard 不负责执行任何真实 Provider 退出。若账户 owner 在官方控制台
另行完成了某项操作，必须由受控的独立证据流程提供脱敏结果；本地 recorder 只记录已观察
到的结果，不会执行该操作。即使人工完成了删除或注销，receipt 仍把最终远端零残留记为
`unknown/delegated`，不能把本地记录当作 Provider 证明。

### 产品可观测性字段

receipt 另外记录两个不涉及凭证或请求正文的观察值：

- `provider_console_observation=no-visible-error`：账户 owner 看到的控制台没有用户可见报错或异常；
- `provider_request_response_surface=not-exposed-by-provider`：该产品不向用户暴露逐次 request/response。

这两个值可以完整表达成熟云产品的用户侧观察结果，不要求调试 API，也不要求抓取请求或响应。
它们不等价于 Provider 后台没有日志、缓存、备份或 retention，因此
`provider_remote_zero_residue` 仍保持 `unknown/delegated`。

receipt 还按资源面记录 `surface_observations`：`task_or_run`、`backup_or_snapshot` 和
`retention_policy` 各自只能是 `visible-with-status`、`not-exposed-by-provider` 或
`unknown`。当某个资源面确实不由产品暴露时，对应状态会写成
`not-exposed-by-provider`；这不是 `none-observed`，也不是远端资源不存在的证明。
只有 `visible-with-status` 才要求继续填写该资源的实际状态；`unknown` 会保持
`unknown/safe-stop`。

对应的无交互校验器是
[`scripts/record_provider_exit_receipt.py`](../../scripts/record_provider_exit_receipt.py)，
只接受脱敏 fingerprint、预定义的账户范围类别和枚举状态，不接受原始账户标识、资源
ID、Key、Prompt 或响应正文。`account_scope` 只能是 `personal`、`team`、
`organization`、`service-account` 或 `unknown`；它不是邮箱、Project ID、组织 ID
或其他账户标识的替代字段。

## 1. 填写规则

- 只记录 Provider、产品、endpoint、region、model、项目的脱敏标识、resource ID
  fingerprint、状态、时间、责任人和官方来源。
- 禁止记录 API Key、Access Key、Cookie、OAuth/session、完整邮箱、Prompt、私有代码、
  文件内容或 Webhook secret。
- `human-reported` 是输入事实，不等于官方证明；`official-verified` 只覆盖官方页面
  明确写出的产品和接口范围。
- 如果一个资源的 owner、范围、retention、删除入口或结果不可确认，状态保持
  `unknown / safe-stop`，不要执行批量删除或自动 retry。

## 2. 当前 Provider profile

| 字段 | 当前值 | 来源/证据 | 状态 |
|---|---|---|---|
| Provider | 火山引擎/火山方舟（Ark） | Human 提供 | `human-reported` |
| 产品/套餐 | Coding Plan（待账户 owner 确认） | Human + 官方 Coding Plan 资料 | `partial` |
| OpenAI-compatible endpoint | `https://ark.cn-beijing.volces.com/api/coding/v3` | Human；官方 Coding Plan Base URL 页面交叉核对 | `official-verified / actual-account-unverified` |
| region | `cn-beijing` | Human 已确认；仍以账户/数据区实际配置为准 | `human-confirmed / staging-used` |
| model / Model ID | `ark-code-latest` | Human 提供，2026-09-01 | `human-reported / actual-account-unverified` |
| account scope | 个人 | Human 提供；官方资料仅说明个人版产品范围 | `human-reported / scope-limited` |
| project / billing | `9f5179ed9b7d69e37fa3a1fa5c5563f3a7f67fdf514647ebd5ef07f2c4196add`（SHA-256 fingerprint） | Human 提供；原始 Project/billing ID 未记录 | `human-confirmed / staging-used` |
| authentication path | Provider API Key | Human + 官方 API Key 资料 | `official-verified / target-key-unverified` |
| key fingerprint | `9c9020b16cb136d1f0cb71989fe3b81e0fc756742f6b7d2eb335ba2a84683451`（SHA-256） | Human 提供，生成于 2026-09-01；未记录 Key 原文 | `human-reported / target-key-unverified` |
| ZWorkbench ownership | 不创建、不管理、不删除 Provider 侧资源 | W8 产品边界 | `product-boundary` |

官方来源索引见 [`optional-provider-exit-primary-sources.md`](./optional-provider-exit-primary-sources.md)，
包括 Coding Plan endpoint、API Key 管理、数据授权、隐私、服务条款、账号注销和
标准 `/api/v3` 对象删除页面。标准 `/api/v3` 的对象能力不得外推到 Coding
`/api/coding/v3`。

## 3. 数据流 inventory

由账户 owner 针对实际使用的配置逐行确认。这里的“发送”包括 Prompt 中的代码、路径、
错误输出和工具结果；“Provider 副本”还包括日志、缓存、监控、排障和备份。

| 数据对象 | 是否发送 | Provider 是否存储/处理 | 目的 | retention/删除依据 | 是否含敏感信息 | 状态 |
|---|---:|---:|---|---|---:|---|
| Prompt / 指令 | unknown | unknown | 推理/服务处理 | unknown | 待确认 | `unknown` |
| 代码片段 / 文件 | unknown | unknown | 推理/上下文 | unknown | 待确认 | `unknown` |
| Model output | unknown | unknown | 响应/历史/排障 | unknown | 待确认 | `unknown` |
| 错误 / usage / request metadata | unknown | unknown | 计费/监控/排障 | unknown | 待确认 | `unknown` |
| 缓存 / 日志 / 可观测性 | unknown | unknown | 服务运行 | unknown | 待确认 | `unknown` |
| Provider 备份 / 灾备副本 | unknown | unknown | 业务连续性 | unknown | 待确认 | `unknown` |
| Webhook payload / integration data | Human 报告存在，具体范围待确认 | unknown | 任务/集成 | unknown | 待确认 | `unknown` |

官方资料已经说明广义服务可能因合规、过滤、排障、产物查询、异常告警、缓存、日志、
监控等处理或存储数据，也说明个人版已使用数据技术上无法撤回、法律/税务及备份存在
留存边界。这些事实不能替本次 Coding endpoint 填出逐对象 retention。

## 4. 远端资源 inventory

当前只登记“存在性线索”，不假设资源属于哪个 Ark 产品，也不假设由 ZWorkbench 创建。

| 资源类别 | 脱敏 resource ID/fingerprint | 创建来源 | 当前状态 | 数据范围/目标 | 停止/删除入口 | retention/到期 | 责任人 | 证据状态 |
|---|---|---|---|---|---|---|---|---|
| Coding task / run / queue | 待账户 owner 填写 | 待确认 | unknown | 待确认 | 待确认 | unknown | 账户 owner / Provider | `human-reported existence / details unknown` |
| Scheduler / future trigger | 待账户 owner 填写 | 待确认 | unknown | 待确认 | 待确认 | unknown | 账户 owner | `unknown` |
| Webhook / integration | 待账户 owner 填写 | 待确认 | unknown | 回调目标/权限待确认 | 待确认 | unknown | 集成 owner | `human-reported existence / details unknown` |
| Provider backup / snapshot | 待账户 owner 填写 | 待确认 | unknown | 待确认 | 待确认 | unknown | 备份 owner / Provider | `human-reported existence / details unknown` |
| File / Response / 标准 API 对象 | 待确认是否使用 | 待确认 | unknown | 待确认 | 标准 `/api/v3` 有对象级页面；不外推 Coding | unknown | 项目 owner | `scope-limited` |
| API key / project permission | 只填 key fingerprint | 账户 owner | unknown | project/scope 待确认 | 禁用/删除 key | 不等于数据删除 | 账户 owner | `official-key-lifecycle / target-unverified` |
| Billing / subscription / invoice | 待填写脱敏标识 | 账户 owner | unknown | 账单/税务范围 | 退订/注销前结清 | 法律/税务留存 unknown | 账单 owner | `official-account-exit / target-unverified` |

## 5. 真实退出与本 wizard 的边界

本仓库不提供 Provider-side 删除、停用、退订或注销命令，也不把这些动作嵌入 inventory
wizard。以下只定义责任边界，不构成一键操作流程：

1. 用本节第 0 节的 wizard 只读记录当前 task/Webhook/backup/data/key/billing/
   subscription/account 状态和 retention 证据 fingerprint；不执行任何改变状态的动作。
2. 如果账户 owner 另行决定在 Provider 官方控制台操作，应只在 Provider 自己的范围和
   二次确认界面中完成；该操作不由 ZWorkbench 发起，也不由本 wizard 确认或代办。
3. 操作结果只能以账户 owner 交接的脱敏官方 receipt、工单或控制台证据作为输入；本地
   recorder 只写入状态和 fingerprint。提交请求不等于清除完成，最终远端零残留仍是
   `unknown/delegated`。
4. 账户不注销、订阅不取消、Key 不撤销时，分别记录实际状态（例如 `active`、
   `not-touched`、`not-performed`），不得为了让节点通过而执行这些动作。

## 6. Gate A 当前结果

```text
provider_identity: partial
authentication: partial
data_scope_and_retention: unknown
remote_resource_inventory: unknown
remote_exit_and_deletion: unknown / not-performed
real_provider_read_only_staging: authorized-read-only-staging-passed
real_ark_failover: unknown/stop; existing local credential returned 401 on both bounded routes
remote_exit_and_deletion: unknown / not-performed
Gate A: HOLD / UNKNOWN (no existing Provider console session; remote exit remains delegated)
```

进入新的真实 Provider staging 或执行退出前，账户 owner 仍需确认：本次授权、数据类别、
适用条款/生效日期、任务/Webhook/backup 的脱敏 fingerprint、删除/停用入口、retention
或到期规则、账单责任人和退出验证证据。这里不要求把 key 值交给 ZWorkbench。

## 7. 与 1-6 和 W8 的关系

- 本清单是外部 Provider 试验的证据 baseline，不是 W8 产品开发节点，也不是 Gate A 自动放行。
- 默认产品路径继续使用 loopback/fake Provider；已完成的真实只读 staging 是单独的
  owner-authorized evidence，不会自动成为默认路由或退出授权。
- 可恢复写操作仍受 Gate B 独立约束；Provider 资料完整也不能放行本地写 effect。
- 本地写操作另受 [`w8-1-6-recoverable-write-and-runtime-boundary.md`](../plans/w8-1-6-recoverable-write-and-runtime-boundary.md) 的独立 Gate B 约束。
