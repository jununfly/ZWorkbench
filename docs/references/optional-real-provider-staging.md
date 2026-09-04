# 可选：真实 Provider 只读 staging 验证 runbook

状态：`out-of-roadmap / authorized-read-only-staging-passed / real-Ark-failover-on-demand / exit-HOLD` · 路线类型：`Acceptance / evaluation` · 核查日期：`2026-09-04`

本文把“真实 Provider 只读 staging”说成 Human 可以执行和签核的步骤。它不是
Provider adapter 实现，也不是授权申请，更不是把一次真实请求当成生产可用性证明。
它已从 W8 产品目标树移出，不是 ZWorkbench 核心开发的阻断节点；只有账户 owner
明确希望做一次真实 Provider 验证时才按需使用。
当前目标 Provider 是用户报告的火山方舟 Coding API：
`https://ark.cn-beijing.volces.com/api/coding/v3`；本 helper 的本次 staging region 固定为
`cn-beijing`。如果账户/数据实际区域不同，应停下并单独评审对应 endpoint，不能把其他
区域名称翻译后填入本 run。

## 0. 安全执行入口

如果确实要验证一次真实请求，请在 ZWorkbench 根目录运行
[`scripts/optional-real-provider-staging.sh`](../../scripts/optional-real-provider-staging.sh)。
它会先要求账户 owner 确认 S1–S6 的非敏感前置门（实际 region/project fingerprint、
Key scope/撤销、数据/retention、远端 inventory、退出路径和一次性授权），再在本机
隐藏读取 API Key，并通过 stdin 传给本地 helper；Key 不进入聊天、命令行参数、`.env`、
仓库或 summary。helper 只向固定的 Ark HTTPS endpoint 发出请求，禁止重定向、绕过代理、
30 秒超时且不自动重试；输出只包含 HTTP 状态、digest、响应结构、合成 fixture 语义
布尔值和脱敏 preflight，不保存原始请求或响应。缺少前置门时 helper 在任何网络请求前停止。

因此这里的“安全分享”不是把 Key 分享给 Agent，而是让你在本机执行真实请求后，
只把 `summary.json` 的路径或内容交给 Agent。若请求失败，也只分享脱敏 summary；
不要在聊天里粘贴 Key，也不要使用 `KEY=... command` 把 Key 放进命令行。

## 0.1 真实 Ark fallback staging

如果要验证真实 Ark 的 owner-facing fallback 合同，而不是只验证单次连通性，运行：

```bash
./scripts/optional-real-ark-failover.sh
```

该入口固定执行两次独立合成请求：第一路使用明确不存在的 model，预期得到 Ark 的
模型拒绝；第二路使用 `ark-code-latest`，预期得到合成 fixture。两路都指向同一
`cn-beijing` Coding endpoint 和账户 scope，因此这是“真实 Ark + 受控负向控制”的
fallback 证据，不是第二个独立 Provider，也不是自然限流/故障恢复证明。两次请求都
不自动重试，最大请求预算为 2；失败时必须保留 `unknown/stop`。

runner 会把 provider/model/endpoint/HTTP status、fallback reason/target、cooldown、
CompositionOwner state digest 和语义布尔值写入脱敏 summary，不保存请求/响应正文或
API key。成功标签为
`verified-for-authorized-real-ark-negative-control-fallback`，仍不能放行默认产品路由、
真实项目写入、任务、Webhook、备份或 Provider-side exit。

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
| S1 Provider identity | 固定 endpoint、region、实际 model ID、脱敏 project/billing 标识 | `partial`：`model_id=ark-code-latest` 已由 Human 提供，实际 region/project 需本次 owner 确认 |
| S2 认证引用 | 只提供不可逆 key fingerprint；key 原文不进入聊天、仓库、日志、backup | `partial`：fingerprint 已收到，Key scope/有效性/撤销证据未确认 |
| S3 数据边界 | 本次会发送的 Prompt/output/error/usage/telemetry 类别、区域和 retention | `blocked`：Coding endpoint 逐对象 retention 未闭合 |
| S4 远端资源 | task/run/queue、Webhook、backup 等资源的脱敏 ID、owner、停止/删除入口 | `blocked`：inventory 未闭合 |
| S5 退出路径 | 停止请求、撤销 key、停用触发器、删除/导出请求、响应或工单 ID | `blocked`：退出验证未执行 |
| S6 人工授权 | 账户 owner 明确授权一次 staging 请求、预算上限和停止条件 | `blocked`：本批次尚无一次性授权记录 |
| S7 本地隔离 | 合成 Prompt、非敏感 workspace、case-local state、无 effect/scheduler/Webhook | `ready by design`：沿用 W8 第一切片约束 |

任一 S1–S6 为 `unknown` 时，该次运行就是 `HOLD / safe-stop`，不能用 S7 或 fake
Provider 的通过结果抵消。最新一次账户 owner 的 S1–S6 已由脱敏 summary 记录为
授权只读 staging 通过；这不自动授权新的 failover 请求或 Provider-side exit。

## 3. 解锁前由 Human 准备的脱敏字段

字段可以留在本地人工记录中，不需要把 secret 或私有数据交给 ZWorkbench。

```text
provider: 火山方舟 / Ark
product: Coding Plan（以账户控制台为准）
endpoint: https://ark.cn-beijing.volces.com/api/coding/v3
region: cn-beijing  # 先在 Ark 控制台/实际配置确认；不是从 URL 猜测，也不是 en_beijing 等翻译值
model_id: <实际使用的 Model ID>
project_fingerprint: <Ark Project ID 或 billing-scope ID 的 SHA-256；不是 ZWorkbench/项目名称/API Key>
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

1. **确认实际身份**：从实际使用的 Coding 配置/控制台确认 `region=cn-beijing`、
   `model_id=ark-code-latest` 和请求所属的 Ark Project/billing scope。这里的
   `project_fingerprint` 是实际 Project ID 或 billing-scope ID 的 SHA-256；它不是
   ZWorkbench、本地 workspace、项目名称、model、endpoint、region、API Key 或 API Key
   fingerprint。例如 Project ID 已在当前 shell 的非持久环境变量中时，可运行：

   ```sh
   printf %s "$ARK_PROJECT_ID" | shasum -a 256 | awk '{print $1}'
   ```

   只把输出的 64 位十六进制值记录为 `project_fingerprint`。变量名按你的实际配置替换；
   不要把 project ID 原文写入命令参数、文件或聊天。API Key fingerprint 由 wizard 在隐藏
   输入后单独生成，两个 fingerprint 不应相同；相同时 helper 会在网络请求前停止。

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

完成这五项后，把第 3 节字段和证据引用回填到本地版本；wizard 会把本次确认的非敏感
region/project fingerprint 与 gate 状态写入 summary。若任何一项未确认，helper 会在
任何网络请求前停止且 request_count=0；该次真实 Provider 请求仍是
`not-authorized / HOLD`。

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

连通性 probe 默认可发一个、或在账户 owner 明确批准预算后发最多五个不含个人信息、商业秘密或真实代码的固定 Prompt，例如：

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

one-shot 只能够证明 `transport + single semantic observation`，结果状态为
`transport-and-semantic-partial`，不能称为完整 Provider compatibility。若账户 owner
另行授权最多 5 次请求并将 `budget_requests` 设为至少 5，helper 支持显式
`--repeats 5`：这是 5 次独立合成请求，不是失败后的自动 retry；任一次失败即停止后续
请求。只有 5/5 HTTP 成功、5/5 精确合成语义、零重试和所有脱敏/退出门通过，才可标记
`verified-for-authorized-read-only-staging`。

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
| 语义 | 只有显式 `--repeats 5` 的确定性 staging 任务达到 `5/5`，结果和错误分类可解释；one-shot 仅为 partial |
| 可观测 | 必需事件字段完整率 `100%`，run/thread/turn/provider/result 可关联 |
| 退出 | 本地停止、导出、清理可复核；远端每个已知资源都有停止/删除结果或责任人 |
| 不确定性 | 任何未知数据范围、远端对象或 effect 都进入 `safe-stop`，不自动 retry |

通过这些阈值也只能得出 `verified-for-authorized-read-only-staging`，不能放行真实
项目写入、Git push、部署、远端任务/Webhook/备份管理或 live replay。

## 6. 当前阻断与下一动作

最新账户 owner 已完成 5/5 真实 Ark 只读语义 staging，并完成 1/1 真实 Codex + Ark
case-local turn；脱敏 summary 分别位于 `evaluation/evidence/optional-real-provider/`
和 `evaluation/evidence/remote-codex-provider/`。这关闭了授权只读 staging 子门，但
不能替代真实 Ark fallback 或远端退出证据；当前本 runbook 的下一步仍是按需触发，
完整 Provider exit 继续保持 `HOLD / delegated`。

解锁顺序：

1. 需要单独验证真实 Ark fallback 时，运行 `./scripts/optional-real-ark-failover.sh`，
   由账户 owner 重新确认本次两请求授权和停止条件；
2. 需要收口 Provider-side exit 时，运行 `./scripts/optional-provider-exit.sh`，盘点
   任务、Webhook、备份、数据、key、订阅、账单和账户状态；
3. 任一数据范围、远端对象、请求完成状态或 retention 结果未知，都回到
   `HOLD / safe-stop`，不进入批量删除或自动 retry。

相关事实源：

- [`optional-provider-exit-inventory.md`](./optional-provider-exit-inventory.md)
- [`w8-1-6-recoverable-write-and-runtime-boundary.md`](../plans/w8-1-6-recoverable-write-and-runtime-boundary.md)
- [`optional-provider-exit-primary-sources.md`](./optional-provider-exit-primary-sources.md)
