# 可选：真实 Provider 只读 staging 验证 runbook

状态：`out-of-roadmap / on-demand / real-request-HOLD` · 路线类型：`Acceptance / evaluation` · 核查日期：`2026-09-01`

本文把“真实 Provider 只读 staging”说成 Human 可以执行和签核的步骤。它不是
Provider adapter 实现，也不是授权申请，更不是把一次真实请求当成生产可用性证明。
它已从 W8 产品目标树移出，不是 ZWorkbench 核心开发的阻断节点；只有账户 owner
明确希望做一次真实 Provider 验证时才按需使用。
当前目标 Provider 是用户报告的火山方舟 Coding API：
`https://ark.cn-beijing.volces.com/api/coding/v3`。

## 0. 安全执行入口

如果确实要验证一次真实请求，请在 ZWorkbench 根目录运行
[`scripts/optional-real-provider-staging.sh`](../../scripts/optional-real-provider-staging.sh)。
它会在本机隐藏读取 API Key，并通过 stdin 传给本地 helper；Key 不进入聊天、命令行
参数、`.env`、仓库或 summary。helper 只向固定的 Ark HTTPS endpoint 发出一次请求，
禁止重定向、绕过代理、30 秒超时且不自动重试；输出只包含 HTTP 状态、digest、响应
结构和合成 fixture 是否命中，不保存原始请求或响应。

因此这里的“安全分享”不是把 Key 分享给 Agent，而是让你在本机执行真实请求后，
只把 `summary.json` 的路径或内容交给 Agent。若请求失败，也只分享脱敏 summary；
不要在聊天里粘贴 Key，也不要使用 `KEY=... command` 把 Key 放进命令行。

## 1. 本节点要回答的问题

只有在下面的问题都能用脱敏证据回答后，且账户 owner 明确触发本 runbook，才允许
发起一次真实的、只读的 staging 请求：

> 这一次请求发给了哪个 Provider / model / project，发送了哪些合成数据，使用了哪
> 条认证引用，产生了哪些本地和远端资源，如何停止，如何退出，以及这些事实能否在
> owner ledger 中复核？

“OpenAI-compatible”只描述协议表面，不能替代 Provider 的数据、retention、任务、
Webhook、备份或删除合同。

## 2. 当前结果

| 子门 | 必须具备的证据 | 当前状态 |
|---|---|---|
| S1 Provider identity | 固定 endpoint、region、实际 model ID、脱敏 project/billing 标识 | `partial`：`model_id=ark-code-latest` 已由 Human 提供，region/project 未确认 |
| S2 认证引用 | 只提供不可逆 key fingerprint；key 原文不进入聊天、仓库、日志、backup | `partial`：fingerprint 已收到，Key scope/有效性/撤销证据未确认 |
| S3 数据边界 | 本次会发送的 Prompt/output/error/usage/telemetry 类别、区域和 retention | `blocked`：Coding endpoint 逐对象 retention 未闭合 |
| S4 远端资源 | task/run/queue、Webhook、backup 等资源的脱敏 ID、owner、停止/删除入口 | `blocked`：inventory 未闭合 |
| S5 退出路径 | 停止请求、撤销 key、停用触发器、删除/导出请求、响应或工单 ID | `blocked`：退出验证未执行 |
| S6 人工授权 | 账户 owner 明确授权一次 staging 请求、预算上限和停止条件 | `blocked`：本批次尚无一次性授权记录 |
| S7 本地隔离 | 合成 Prompt、非敏感 workspace、case-local state、无 effect/scheduler/Webhook | `ready by design`：沿用 W8 第一切片约束 |

任一 S1–S6 为 `unknown`，结果就是 `HOLD / safe-stop`，不能用 S7 或 fake Provider
的通过结果抵消。

## 3. 解锁前由 Human 准备的脱敏字段

字段可以留在本地人工记录中，不需要把 secret 或私有数据交给 ZWorkbench。

```text
provider: 火山方舟 / Ark
product: Coding Plan（以账户控制台为准）
endpoint: https://ark.cn-beijing.volces.com/api/coding/v3
region: <账户/数据区域，不从 URL 猜测>
model_id: <实际使用的 Model ID>
project_fingerprint: <项目或账单归属的不可逆 fingerprint>
api_key_fingerprint: <key 的不可逆 fingerprint；不是 key 原文>
account_scope: 个人
budget_limit: <本次最大请求数 / 金额 / token 上限>
data_classes: <合成 Prompt、合成文件、output、error、usage、telemetry>
retention_basis: <官方页面/控制台/工单编号；不知道就写 unknown>
remote_inventory: <task/Webhook/backup 的脱敏 ID 或 none 的证据>
exit_owner: <账户 owner>
one_time_authorization: <授权时间、范围、有效期、停止条件>
```

禁止填写：API Key、Access Key、Cookie、OAuth/session、完整账户邮箱、真实 Prompt、
私有代码、真实文件内容、Webhook secret。

### 3.1 本次启动的人工填表包

目前已有的输入包括：`Provider=火山方舟`、
`endpoint=https://ark.cn-beijing.volces.com/api/coding/v3`、`account_scope=个人`、
`model_id=ark-code-latest`，以及“存在远端数据、任务、Webhook、备份”的存在性报告。
其中 model 和 API Key fingerprint 仍属于 Human 提供的脱敏事实，不能替代账户/项目
和 Provider 条款证据。请账户 owner 在本地控制台或本地终端完成填表；只把脱敏结果交给
评估，不要把原始 ID、邮箱或 secret 贴到聊天或仓库。

本次已收到的认证引用记录如下：

```text
api_key_fingerprint: 9c9020b16cb136d1f0cb71989fe3b81e0fc756742f6b7d2eb335ba2a84683451
fingerprint_algorithm: SHA-256
generated_at: 2026-09-01
source: Human local generation
```

这只能证明“有一条脱敏引用可用于后续关联”，不能证明 Key 有效、scope 正确、已被
撤销，或某次请求实际使用了它。

1. **确认实际身份**：`model_id=ark-code-latest` 已收到，但仍需从实际使用的 Coding
   配置/控制台确认账户/数据 `region`；项目或账单 ID 只在本地做不可逆 fingerprint。例如 secret 已在当前 shell
   环境变量中时，可运行：

   ```sh
   printf %s "$ARK_API_KEY" | shasum -a 256
   printf %s "$ARK_PROJECT_ID" | shasum -a 256
   ```

   输出只记录为 `api_key_fingerprint` 和 `project_fingerprint`。本次 API Key fingerprint
   已提供；仍需补 `project_fingerprint`。变量名按你的实际
   配置替换；不要把 key/project 原文写入命令参数、文件或聊天。

2. **逐项确认数据责任**：对 Prompt、代码/文件、output、error/usage/metadata、日志/
   telemetry、缓存、备份、Webhook payload 分别填写“是否发送、是否存储、处理目的、
   区域、retention、删除条件、官方页面/控制台/工单编号”。如果官方资料没有把事实
   绑定到本次 Coding endpoint，就填 `unknown`，不能用广义 Ark 条款补写成已确认。

3. **盘点远端对象**：在账户 owner 可见的控制台/API 范围内逐项查看 task/run/queue、
   scheduler、Webhook/integration、backup/snapshot、file/response 和 key/project。
   每项只记录资源类型、脱敏 ID fingerprint、owner、状态、创建来源、停止/删除入口、
   retention 和证据时间。用户已报告“存在”的类别不能填写 `none`；找不到具体对象
   时记录 `存在性已报告 / 具体对象 unknown`。

4. **写出一次性授权**：在真实请求前，由账户 owner 明确授权“一次、只读、合成数据、
   固定 model、固定 endpoint、无工具/文件写入/任务/Webhook/备份”，并给出最大请求数、
   token/金额、最长时长、失控时立即停止条件和授权失效时间。没有这段授权，
`S6=blocked`，不能因为运行本 runbook 或进入 ZWorkbench 其他节点而推定授权已经存在。

5. **只核对退出入口，不提前执行删除**：确认停止本地 run、取消远端 task、停用
   Webhook/schedule、撤销 key、提交数据删除/导出请求和保留期复核分别由谁负责，记录
   官方入口及预计响应/工单字段。真正发送 staging 请求后，才按第 4.3 节执行退出；
   “已提交删除”不等于“已清除”。

完成这五项后，把第 3 节字段和证据引用回填到本地版本；在此之前本节点可以继续做
preflight 文档工作，但真实 Provider 请求仍是 `not-authorized / HOLD`。

## 4. 解锁后的实际操作顺序

以下步骤现在不执行；只有第 3 节字段和 S1–S6 证据闭合后，才可以按顺序执行。

### 4.1 建立隔离 case

1. 新建一个 case-local 目录和空的非敏感 workspace；不要使用真实项目目录。
2. 使用固定的 Codex `0.139.0` 和同一个 SQLite composition owner。
3. 将 mode 固定为 `local-read-only-staging`；预先关闭 effect、scheduler、自动 retry、
   Webhook delivery 和 live replay。
4. 设置请求数、token/金额和最长运行时间上限；超限立即停止。
5. 认证只能通过运行时 secret 引用注入。先验证日志、event、export、backup 中没有
   secret 原文，再启动请求。

### 4.2 发送最小合成请求

只发一个不含个人信息、商业秘密或真实代码的固定 Prompt，例如：

```text
Return exactly JSON with keys: status and answer.
Use status="ok" and answer="staging-fixture-001".
Do not call tools, access files, create tasks, send callbacks, or write anything.
```

请求必须记录以下脱敏事实：

- `run_id`、`thread_id`、`turn_id`、时间和 adapter/schema 版本；
- Provider、model、endpoint、region、project fingerprint；
- 请求/响应数量、错误分类、完成状态和语义结果 digest；
- 网络目的地、effect 数量、远端资源 ID（如果 Provider 返回）；
- stop/revoke/cleanup 动作及结果。

若出现工具调用、文件写入、未知远端对象、Webhook、异步任务、未预期 callback、
认证范围漂移或无法判断请求是否完成：立即 `safe-stop`，保留证据，不 retry。

### 4.3 关闭并审计 case

1. 先停止本地 run、retry 和任何触发器；确认没有 pending effect。
2. 记录 owner state digest、事件完整性和本地 export/backup 路径。
3. 按账户 owner 的退出清单核对远端 task/Webhook/backup；只记录脱敏 ID 和响应/工单
   编号。
4. 删除本地 case-local workspace、state、export 和 key 引用；记录删除时间。
5. 对 Provider 侧无法观察的 retention、日志、缓存或备份残留，保留
   `unknown / delegated`，不得写成“已清除”。

## 5. 验收阈值

本节点的阈值是硬门，不做平均分：

| 维度 | 通过条件 |
|---|---|
| 身份 | 每个请求可绑定固定 Provider、model、endpoint、region 和 project |
| 认证 | secret 原文在输入、日志、owner、event、export、backup 中出现 `0` 次 |
| 只读 | effect、文件写入、Git、部署、任务创建、Webhook delivery 均为 `0` |
| 语义 | 确定性 staging 任务按既定 C5 合同重复 `5/5`，结果和错误分类可解释 |
| 可观测 | 必需事件字段完整率 `100%`，run/thread/turn/provider/result 可关联 |
| 退出 | 本地停止、导出、清理可复核；远端每个已知资源都有停止/删除结果或责任人 |
| 不确定性 | 任何未知数据范围、远端对象或 effect 都进入 `safe-stop`，不自动 retry |

通过这些阈值也只能得出 `verified-for-authorized-read-only-staging`，不能放行真实
项目写入、Git push、部署、远端任务/Webhook/备份管理或 live replay。

## 6. 当前阻断与下一动作

本轮未读取 API Key，未使用真实凭证，未向火山方舟发送业务请求，也未创建或删除远端
资源。本 runbook 当前仅完成 preflight，真实请求仍保持 `HOLD / not-authorized`。

解锁顺序：

1. 账户 owner 按第 3.1 节补齐第 3 节字段和 Provider inventory；当前还缺实际 region、
   project/billing fingerprint，以及 API Key scope/撤销生命周期证据；
2. 明确一次性授权、预算和停止条件；
3. 对 S1–S6 做人工签字/时间戳记录；
4. 再由 W8 runner 增加或执行真实只读 staging evidence；
5. 若仍有任何 unknown，回到 `HOLD / safe-stop`，不进入业务请求。

相关事实源：

- [`optional-provider-exit-inventory.md`](./optional-provider-exit-inventory.md)
- [`w8-1-6-recoverable-write-and-runtime-boundary.md`](../plans/w8-1-6-recoverable-write-and-runtime-boundary.md)
- [`optional-provider-exit-primary-sources.md`](./optional-provider-exit-primary-sources.md)
