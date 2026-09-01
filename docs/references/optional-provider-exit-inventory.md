# 可选：Provider 与远端退出 inventory

状态：`reference-only / on-demand / out-of-roadmap`

本文是给一次具体 Provider 账户填写的脱敏清单，不是 W8 产品目标节点、远端删除脚本，也不是法律/隐私
签核。当前目标账户是用户报告的火山方舟个人账户；所有未确认字段保留为
`unknown`，不能用“控制台没看到”填成 `none`。

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
| region | endpoint 含 `cn-beijing`；实际账户/数据区待确认 | endpoint 字符串不能代替账户/数据区证明 | `unknown` |
| model / Model ID | `ark-code-latest` | Human 提供，2026-09-01 | `human-reported / actual-account-unverified` |
| account scope | 个人 | Human 提供；官方资料仅说明个人版产品范围 | `human-reported / scope-limited` |
| project / billing | 待填写脱敏标识 | 账户 owner | `unknown` |
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

## 5. 退出操作顺序（只在账户 owner 授权后执行）

下面是人工 runbook 的顺序，不是现在执行的命令：

1. 冻结 ZWorkbench 新 run、retry、schedule delivery 和 Webhook 触发；记录本地最后请求
   时间、run ID 和 owner state digest。
2. 在 Provider 控制台确认账户、region、project、套餐和账单；填写第 2 节 profile。
3. 逐项填写第 3/4 节数据和资源清单；任何范围不明时停止。
4. 在删除/注销前导出最小必要的账单、审计和恢复材料，并记录保存责任人；不导出 key
   或私有 Prompt/代码到仓库。
5. 先停用未来触发、取消/删除仍在运行的任务和 Webhook；保存脱敏结果/响应 ID。
6. 按官方流程提交数据/文件/备份删除或 retention 请求；记录提交时间、工单/响应 ID和
   预计完成时间；不把“已提交”写成“已清除”。
7. 确认没有必要的恢复/支持操作后，禁用/删除 API Key、解绑集成并复核账单；Key 删除
   只证明不能继续鉴权，不证明历史数据已删除。
8. 最后清理本地 case workspace、CODEX_HOME、composition owner export/backup 和 key
   引用，检查本地残留；本地零残留不等于 Provider 远端零残留。
9. 到达 Provider retention/静默期后复核延迟删除、备份和法定留存；若无法观察，保留
   `unknown / delegated`，由责任人签字，不由 Agent 猜测。

## 6. Gate A 当前结果

```text
provider_identity: partial
authentication: partial
data_scope_and_retention: unknown
remote_resource_inventory: unknown
remote_exit_and_deletion: unknown / not-performed
real_provider_read_only_staging: not-authorized
Gate A: HOLD / UNKNOWN
```

进入可选真实 Provider staging 前至少需要账户 owner 补齐：实际 model/project、key fingerprint、数据
类别、适用条款/生效日期、任务/Webhook/backup 的脱敏 ID、删除/停用入口、retention
或到期规则、账单责任人和退出验证证据。这里不要求把 key 值交给 ZWorkbench。

## 7. 与 1-6 和 W8 的关系

- 本清单是外部 Provider 试验的证据 baseline，不是 W8 产品开发节点，也不是 Gate A 自动放行。
- 在 Gate A 未闭合前，继续使用 loopback/fake Provider；不得读取真实 key 或执行真实
  Provider 业务请求。
- 可恢复写操作仍受 Gate B 独立约束；Provider 资料完整也不能放行本地写 effect。
- 本地写操作另受 [`w8-1-6-recoverable-write-and-runtime-boundary.md`](../plans/w8-1-6-recoverable-write-and-runtime-boundary.md) 的独立 Gate B 约束。
