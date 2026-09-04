# W8 真实远程 Provider 兼容性 findings

状态：`mixed / authorized Codex staging passed / loopback failover composition passed / real Ark fallback unknown-stop / Provider-side exit HOLD`
日期：2026-09-04
路线节点：`1-9-7`

本节点处理的是显式授权的真实远程 Provider 只读 staging，不是把真实 Provider 接入
ZWorkbench 默认产品路径。当前目标是火山方舟 Coding API：
`https://ark.cn-beijing.volces.com/api/coding/v3/responses`，配置 model 为
`ark-code-latest`。产品默认仍使用 fake/loopback Provider；远程账户、数据 retention、
任务/Webhook/备份和退出责任由 Provider/账户 owner 负责。

本轮真实 Codex runtime staging 已完成一次新的 case-local 只读 turn；它关闭的是授权
staging 子门，不是默认产品接入或完整 Provider 兼容性。此前一次把凭证写入 evidence 的
失败现场仍作为历史 unknown/stop 保留；按当前 Human 范围，本轮不对该现场执行撤销、轮换
或清理。

## 当前已经有的证据

最新的账户 owner 脱敏 staging summary：
[`evaluation/evidence/optional-real-provider/20260904T063832Z-32230/summary.json`](../../evaluation/evidence/optional-real-provider/20260904T063832Z-32230/summary.json)。
它记录了固定 Ark endpoint 的 5 次独立合成只读请求：HTTP `200` 为 `5/5`、语义
fixture 精确匹配为 `5/5`、`retry_count=0`，并记录了 `region=cn-beijing` 与新的
`project_fingerprint`。该 fingerprint 与 API Key fingerprint 不同，且没有原始请求/响应
落盘。它关闭了本次“授权只读 staging”的 transport、identity 和 semantic 子门，但不
改变 Codex runtime、failover、远端退出或生产适用性的状态。

仓库中已有历史脱敏 summary：
[`evaluation/evidence/optional-real-provider/20260901T082158Z-49449/summary.json`](../../evaluation/evidence/optional-real-provider/20260901T082158Z-49449/summary.json)。
它记录了一次真实 Ark 请求：HTTP `200`、`request_count=1`、`retry_count=0`、合成
fixture token 命中、响应结构和 digest 已保存、raw request/response 未持久化。

这条历史证据的等级是 `external/on-demand reachability`，只能证明：固定 endpoint 在当时
可达，并返回了包含合成标记的响应。最新 summary 的账户身份和人工 gate 已由 owner 在
本次 run 中确认，但 one-shot probe 本身仍不执行 Provider 资源盘点、退出或删除；这些
责任和结果仍需单独记录。因此最新证据也不升级为完整 `real Provider compatibility`。

最新真实 Codex + Ark summary：
[`evaluation/evidence/remote-codex-provider/20260904T083602Z-50607/summary.json`](../../evaluation/evidence/remote-codex-provider/20260904T083602Z-50607/summary.json)。
它记录固定 Codex `0.139.0` 经 `ark-real-staging` 完成恰好一次合成只读 turn：
`owner=completed`、thread/turn 已关联、`fixture_exact=true`、workspace 未变化、
effect 数量为 0、Codex 进程已退出、临时 runtime HOME 已清理、事件日志脱敏、
`raw_credential_persisted=false`、`retry_count=0`。该结果记为
`verified-for-authorized-read-only-codex-staging`。

## 本轮实现

### 受控 helper

[`scripts/run_optional_provider_probe.py`](../../scripts/run_optional_provider_probe.py) 现在
提供以下边界：

- 发送前要求非敏感的 `region`、64 位 SHA-256 `project_fingerprint`、请求预算、30 秒
  以内时限，以及 Key scope、data/retention、remote inventory、exit path、one-time
  authorization 五项确认；不完整时在任何网络请求前停止；
- Key 仍只从 stdin 读取，并只产生 SHA-256 fingerprint；不进入 argv、prompt、日志、
  owner、backup、artifact 或 summary 中；
- 固定 HTTPS Ark host/path、拒绝 redirect、绕过代理、限制响应体 1 MiB、单次请求无
  自动 retry；
- 解析响应时只保存顶层结构、ID/body digest、model 和合成语义布尔值，不保存原始响应；
- 支持 `--repeats 1` 或 `--repeats 5`。5 次是账户 owner 明确批准后的独立请求序列，
  不是失败重试；任一次 HTTP/语义失败都会停止后续请求；只有 5/5 精确返回合成
  `status=ok` 和 `answer=staging-fixture-001` 才标记
  `verified-for-authorized-read-only-staging`。

### 人工入口

[`scripts/optional-real-provider-staging.sh`](../../scripts/optional-real-provider-staging.sh)
现在在隐藏读取 Key 前要求账户 owner 填写实际 region、project fingerprint，选择 1 或
5 次请求，并逐项确认 S1–S6。它不会自动打开浏览器、创建远端资源或执行退出删除；真实
请求结束后只交接脱敏 `summary.json`。

真实 Codex runtime 另有独立入口
[`scripts/optional-real-codex-provider-staging.sh`](../../scripts/optional-real-codex-provider-staging.sh)
和 [runtime staging runbook](../references/optional-real-codex-provider-staging.md)。它使用
case-local Codex `CODEX_HOME`/workspace/owner、固定 Codex `0.139.0`、Ark
`model_providers.ark-real-staging` 配置、只读 sandbox、禁用 plugins/apps 和一次性
合成 turn；不改变默认 `local_read_only` 的 loopback-only preflight。

本轮还修复了 Codex app-server JSONL transport 的事件顺序竞态：selector 驱动的
reader 现在使用二进制 pipe 和显式有序缓冲，避免 `turn/completed` 与
`turn/start` response 同批到达时被漏读。H3 runner 连续 5 次真实 Codex
`0.139.0` + loopback Provider 均通过；产品 `CodexAppServerAdapter` 的同边界
smoke 也通过。该修复不改变本节点的真实 Ark gate，真实远程 Codex runtime 仍须
由账户 owner 通过上述 wizard 产生 owner-facing 证据。该步骤现已完成并产生了上面的
脱敏证据；结果仍不改变默认产品 Provider 路由或 H4/H5 声明。

### 首次真实 Codex + Ark 尝试（历史失败证据）

账户 owner 已执行一次 runtime staging，脱敏 summary 位于
`evaluation/evidence/remote-codex-provider/20260904T075000Z-44499/summary.json`。
Codex `0.139.0` 确实完成了 thread/turn，owner 状态为 completed，workspace unchanged、
effect=0、进程已退出；但结果必须保持 `unknown/stop`，原因有二：

- Codex 自动生成的 shell snapshot 将 API Key 原文写入了 evidence 目录，summary 的
  `raw_credential_persisted=true`；该目录不得共享，Key 应按暴露处理并轮换/撤销；
- Ark 这次 turn 的最终 `agentMessage` 没有对应 delta，旧 adapter 因只消费 delta 而
  记录空文本，导致 `fixture_exact=false`。

runner 现已修复这两条边界：Codex HOME 改为 evidence 外的私有临时目录并在退出后清理，
adapter 从 `item/completed` 的最终 `agentMessage` 提取文本；新增测试模拟 HOME 泄露，
并确认 summary 不保留凭证。旧目录仍是失败证据，不得覆盖成通过；按当前 Human 范围，
本轮不对该历史目录执行撤销、轮换或清理。

### 修复后真实 Codex + Ark staging

账户 owner 随后使用现有本地配置完成一次新的隐藏凭证注入，最新脱敏 summary 位于
`evaluation/evidence/remote-codex-provider/20260904T083602Z-50607/summary.json`。
本次运行满足授权只读 staging 的全部本地 gate：Codex `0.139.0` 和 Ark endpoint
身份已记录，CompositionOwner run 为 completed，thread/turn correlation 完整，
synthetic fixture 精确匹配，workspace unchanged，effect=0，进程退出，临时 HOME
清理成功，事件日志脱敏且 `raw_credential_persisted=false`。因此该子门为
`pass for authorized read-only Codex staging`；它不替历史失败 summary 改状态，也不
证明 failover、degradation、Provider-side exit 或生产兼容性。

### 隔离双 loopback Provider failover

为关闭本节点中“本地 owner-facing failover 合同”的缺口，新增了隔离 fixture
[`evaluation/fixtures/w8_remote_provider_failover/v1/router.py`](../../evaluation/fixtures/w8_remote_provider_failover/v1/router.py)
和 runner
[`evaluation/runner/run_w8_remote_provider_failover.py`](../../evaluation/runner/run_w8_remote_provider_failover.py)。
runner 在两个临时 `127.0.0.1` 端口启动 HTTP loopback Provider，不读取真实凭证、不访问
外部网络，也不修改默认产品 Provider 路由。

最新 evidence：
[`evaluation/evidence/w8-remote-provider-failover-20260904/summary.json`](../../evaluation/evidence/w8-remote-provider-failover-20260904/summary.json)。
结果为 `pass-with-composition`，2/2 场景通过：

- primary 返回 `429 RATE_LIMIT` 后只调用一次，secondary 返回合成 `fixture-ok`；owner
  记录 primary cooldown、`from_provider`、`to_provider`、failure reason 和 degradation；
- owner 关闭并重开后，router 从 owner event ledger 重建两个 route 的 cooldown；全路由冷却
  时直接 `safe_stop`，Provider 新调用为 0、fallback target 为 `null`；
- 两个场景均 `effect=0`，secret-shaped bytes 扫描为 0，所有 Provider identity 均包含
  provider/model/endpoint/transport。

这只关闭了 `owner-backed + loopback-composed` 的本地合同子门，不能替代真实 Ark 或任意
远程 Provider 的 failover/degradation 证据，也不能证明候选 Harness 原生拥有该 ledger。

### 真实 Ark fallback 解锁路径

为避免再次要求重复配置 Provider，新增
[`scripts/optional-real-ark-failover.sh`](../../scripts/optional-real-ark-failover.sh)
和 [`scripts/run_real_ark_failover.py`](../../scripts/run_real_ark_failover.py)。wizard 会
优先复用本地已有的 `ZWB_ARK_PROJECT_FINGERPRINT`/`ARK_API_KEY` 引用；没有现成引用时才
在本机隐藏读取 Key。runner 只向固定 Ark endpoint 发两次合成请求：第一路使用明确的
无效 model 作为可预期负向控制，第二路使用 `ark-code-latest`；两路共享同一 endpoint
和账户 scope，不自动重试。

这条路径可在一次本地运行中验证真实 Ark 的 HTTP 错误分类、owner-backed fallback
reason/target、cooldown、最终语义和 effect=0。它的结果命名为
`verified-for-authorized-real-ark-negative-control-fallback`，不能升级为瞬时故障/配额
耗尽证明、独立第二 Provider 或生产可用性。

本次复用本机已有的 `AICODING_API_KEY` 环境引用执行了该两请求 probe，没有重新生成或
配置凭证。结果保持 `unknown/stop`：primary 和 fallback 均收到 HTTP `401`
`AuthenticationError/Unauthorized`，所以没有观察到 primary 的无效 model 拒绝，也没有
得到 fallback 成功语义。runner 严格执行了两次调用、零 retry，CompositionOwner 已
`safe_stopped`，effect=0，脱敏扫描=0。证据：
[`evaluation/evidence/real-ark-failover/20260904T0955Z-existing-local-credential-rerun/case/summary.json`](../../evaluation/evidence/real-ark-failover/20260904T0955Z-existing-local-credential-rerun/case/summary.json)。

该 `401` 只说明本次现有本地凭证引用未通过 Ark 认证；不推断 key 的具体原因，也不
自动重试、轮换或撤销。真实 Ark fallback 仍为 `HOLD / unknown-stop`。

### Provider-side exit 收口路径

新增 [`scripts/optional-provider-exit.sh`](../../scripts/optional-provider-exit.sh) 与
[`scripts/record_provider_exit_receipt.py`](../../scripts/record_provider_exit_receipt.py)。
它们只引导账户 owner 在控制台/官方支持路径盘点 Coding task/run/queue、Webhook、备份、
数据 retention、API key、订阅、账单和账号状态，并写入只含状态与 SHA-256 fingerprint
的 receipt；不调用 Provider API，不执行删除、停用或注销。

任何 `unknown` 都会保留 `unknown/safe-stop`。即使 owner 记录了删除/注销结果，receipt
仍明确标记 `provider_remote_zero_residue=unknown/delegated`，因为 Coding endpoint 的
日志、缓存、备份、法定留存和已使用数据不能由本地 receipt 推断为零残留。当前
Provider-side exit 仍是 `HOLD / delegated`。本轮只读打开 Provider 控制台时没有现成登录
会话，页面被重定向到登录页；因此没有新增账户级 inventory 或删除/retention 事实，也不
绕过登录、不执行删除、停用或注销。

## 验证

本轮没有把真实凭证输入到 Agent 或仓库；本次复用本机已有的环境凭证引用执行了 2 次
真实 Ark fallback probe，未重新配置 Provider。此前已有 HTTP staging 的 5 次真实远程
合成请求，本次另由账户 owner 在本机按 wizard 完成了 1 次真实 Codex + Ark 只读 turn。已新增的
本地测试覆盖：

```text
PYTHONPATH=src python -m unittest tests.test_optional_provider_probe -v
```

覆盖空凭证、raw credential 不落盘、endpoint 固定、语义结构只保存布尔值、缺少人工
preflight 不能联网、S1–S6/预算校验，以及 5 次显式语义请求不是 retry。另覆盖 region
固定为 `cn-beijing` 以及 project fingerprint 不得复用 API Key fingerprint。运行时脱敏
结果已记录在上面的最新 summary；本次只消费其脱敏字段，不读取 Key 原文。

本轮新增的隔离 failover 回归与 evidence runner 验证为：

```text
PYTHONPATH=src python -m unittest tests/test_w8_remote_provider_failover.py
3/3 pass

PYTHONPATH=src python evaluation/runner/run_w8_remote_provider_failover.py \
  --output evaluation/evidence/w8-remote-provider-failover-20260904
pass-with-composition; 2/2 cases; loopback=only; effects=0; raw credential matches=0
```

测试覆盖 primary `RATE_LIMIT` → secondary fallback、fallback reason/target、cooldown
边界、CompositionOwner reopen 重建和 all-cooled zero-dispatch。runner 保存的 Provider
记录只有方法、路径、请求字节数和 HTTP 状态，不保存请求/响应正文。

真实 Ark fallback probe：

```text
printf '%s' "$AICODING_API_KEY" | PYTHONPATH=src python scripts/run_real_ark_failover.py \
  --output evaluation/evidence/real-ark-failover/<run> \
  --project-fingerprint <existing-64-hex-fingerprint> \
  --region cn-beijing --budget-requests 2 --max-duration-seconds 30 \
  --key-scope-confirmed --data-retention-confirmed --remote-inventory-confirmed \
  --exit-path-confirmed --one-time-authorization-confirmed
unknown/stop; 2/2 HTTP 401 AuthenticationError; retry=0; effects=0; raw credential matches=0
```

该命令中的 Key 只应来自本机环境/隐藏输入，不应复制到聊天或命令参数；上面的
`<run>` 和 fingerprint 仅为命令模板，不是新的凭证配置要求。

## 兼容性分层与当前状态

| 子门 | 证据要求 | 当前状态 |
|---|---|---|
| Transport/reachability | 固定 Ark endpoint 至少一次 HTTP 成功、无 redirect/代理绕过、无自动 retry | `pass for staging`：最新 5/5 HTTP 200，retry=0 |
| Provider identity | endpoint、model、实际 region、project fingerprint 与响应 model 可关联 | `pass for staging`：`cn-beijing` + 脱敏 project fingerprint 已记录 |
| Semantic compatibility | 显式授权的合成任务 5/5 精确语义通过 | `pass for staging`：最新序列 5/5 exact |
| Codex runtime compatibility | 固定 Codex app-server 通过 Ark 完成真实 read-only turn，并关联 thread/turn/owner | `pass for authorized staging`：20260904T083602Z-50607，Codex 0.139.0，1/1 turn |
| Safety/evidence | secret 原文 0 次、effect 0、workspace 只读、owner/evidence identity 完整 | `pass for latest staging`：raw credential 0、effect 0、workspace unchanged、HOME cleaned |
| Failover/degradation | 第二 Provider、fallback target/reason、cooldown 和 durable ledger | `pass-with-composition`：双 loopback + CompositionOwner evidence；真实 Ark negative-control probe `unknown/stop`（两路 401），production/independent remote 仍 HOLD |
| Remote exit | task/Webhook/backup/retention inventory、停止/删除结果和责任人 | `HOLD / delegated`：未执行 |

## 不声明与解锁条件

本节点当前不声明：

- 真实 Provider 已兼容 ZWorkbench 默认产品路径；
- Ark Coding API 与 Codex app-server 的完整工具、stream、schema、错误和限额语义兼容；
- 真实 Ark 的成功 failover、fallback/degradation ledger、全冷却 safe-stop；（loopback 组合证据除外）
- 真实项目、真实代码、写入、Git push、部署、任务、Webhook、备份或 live replay 安全；
- 远端数据已删除或账号已退出。

本次 HTTP staging 的 S1–S6 与真实 Codex runtime 的授权只读 staging 已由账户 owner
在本机完成并记录于脱敏 summary；后续若要宣称完整真实 Provider 兼容性，仍需要
真实 Provider failover/degradation 和 Provider 侧退出结果。当前已完成的双 loopback
证据只证明 owner-facing composition contract；真实 Ark runner 也只提供受控无效 model
fallback 证据，不能替代独立远程路由；如果任一数据范围、远端对象、
请求完成状态或退出结果未知，继续保持 `HOLD / safe-stop`。
