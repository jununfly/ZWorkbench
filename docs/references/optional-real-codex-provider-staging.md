# 可选：真实 Codex runtime + Ark 只读 staging

状态：`out-of-roadmap / on-demand / authorized-read-only-staging-passed / broader-compatibility-HOLD` · 路线类型：`Acceptance / evaluation` · 核查日期：`2026-09-04`

本文用于验证一条受控的真实 runtime 边界：固定的 Codex app-server 是否能在
case-local、只读环境中，通过火山方舟 Ark 完成一个合成 turn，并把 thread/turn
关联到 ZWorkbench CompositionOwner。它不是默认产品路径，也不是生产兼容性证明。
Codex 的运行时 HOME 是一次性的私有临时目录，不会作为 evidence 交接；case-local
evidence 只保留 owner、脱敏事件和 summary。

## 1. 固定范围

本 runner 固定使用：

```text
Codex executable: /opt/homebrew/bin/codex
Codex version: codex-cli 0.139.0
Ark base URL: https://ark.cn-beijing.volces.com/api/coding/v3
Ark request endpoint: https://ark.cn-beijing.volces.com/api/coding/v3/responses
Model: ark-code-latest
Account/data region: cn-beijing
Codex model provider config: ark-real-staging
Sandbox: read-only
Approval policy: never
Plugins/apps: disabled
Turns: exactly 1
Retry: 0
```

Codex 使用 `model_providers.ark-real-staging.env_key="ARK_API_KEY"` 从子进程环境
读取认证。API Key 由账户 owner 本机隐藏输入，经 stdin 进入 runner，再只注入被监督
的 Codex app-server 子进程；不进入命令行参数、Worker envelope、CompositionOwner、
事件日志、artifact 或 summary。Codex 自身可能把继承环境写入 shell snapshot，因此
`CODEX_HOME` 位于 evidence 目录之外的私有临时目录，并在 app-server 退出后清理；清理
失败时结果必须保持 `unknown/stop`。事件日志只保存协议方法、字段名和类型等脱敏摘要。

## 2. 运行入口

由账户 owner 在 ZWorkbench 根目录执行：

```bash
./scripts/optional-real-codex-provider-staging.sh
```

运行前必须重新确认本次授权，而不能把之前 direct HTTP probe 的授权自动延伸到
Codex runtime。wizard 会在请求 Key 前要求确认：

- Provider、model、`region=cn-beijing` 和项目/账单 fingerprint；
- API Key 权限及停用/删除/撤销路径；
- 本次 Coding endpoint 的数据类别、retention 和删除依据；
- task/run/queue、scheduler、Webhook、backup、file、response 等远端对象清单；
- 本地停止、清理与 Provider 侧退出责任；
- 恰好一个合成、case-local、只读 Codex turn，90 秒上限、无重试。

### project_fingerprint 的填写规则

它是实际 Ark Project ID 或 billing-scope ID 的 SHA-256，不是：

- `ZWorkbench` 或本地 workspace/project 名称；
- model、endpoint 或 region；
- API Key 或 API Key fingerprint。

如果 ID 只存在于本机环境变量中，在本机计算：

```bash
printf %s "$ARK_PROJECT_ID" | shasum -a 256 | awk '{print $1}'
```

只把输出的 64 位十六进制值填入 wizard。不要把原始 ID 或 Key 发送到聊天、日志或
仓库。

## 3. 结果解释

成功 summary 的 `compatibility_status` 为
`verified-for-authorized-read-only-codex-staging`，必须同时具备：

- Codex app-server 实际返回 thread/turn 并完成 turn；
- Ark 配置、model、region 和 project fingerprint 已记录；
- CompositionOwner 中有对应 run、thread/turn、event/environment digest 和 state digest；
- case-local workspace 前后相同、effect 数量为 0、Codex 进程已退出；
- 临时 Codex HOME 已清理，且 evidence 目录不包含 Codex runtime HOME；
- 没有发现 API Key 原文写入 case-local evidence；
- synthetic fixture 语义精确匹配。

summary 只交接脱敏内容，位置通常是：

```text
evaluation/evidence/remote-codex-provider/<timestamp>-<pid>/summary.json
```

失败时也只交接 summary；不要自动重试或粘贴 Codex/Provider 原始错误正文。

最新一次成功 staging：
`evaluation/evidence/remote-codex-provider/20260904T083602Z-50607/summary.json`。
该 summary 的 `compatibility_status` 为
`verified-for-authorized-read-only-codex-staging`，并满足 `owner=completed`、
`fixture_exact=true`、workspace unchanged、effect=0、进程退出、临时 HOME 清理、
事件脱敏和 `raw_credential_persisted=false`。此前
`20260904T075000Z-44499` 的失败 summary 仍保持原状；本轮不对其执行撤销、轮换或清理，
也不将其覆盖成通过。

如果 summary 的 `raw_credential_persisted` 为 `true`，立即停止共享该 evidence 目录，
按 API Key 泄露处理并在 Provider 侧轮换/撤销该 Key；不要通过聊天发送原文，也不要只
删除 summary 后继续使用同一个目录。修复后的 runner 会把 Codex HOME 放到目录外并在
结束时清理，需重新执行一次性 wizard 才能产生新的安全证据。

## 4. 当前不声明

这条证据仍不代表：

- ZWorkbench 默认 `local_read_only` 路径允许远程 Provider；
- DSH 主 Harness → Worker → Codex → owner 的完整远程链路已经通过；
- H4 cancel/timeout/crash/recovery 或 H5 recorded/simulated/live replay 已通过；
- Provider failover、fallback/degradation ledger 或全冷却 safe-stop 已通过；
- 真实项目、真实代码、写入、Git、任务、Webhook、备份或生产数据安全；
- Provider 侧远端资源已经删除或账户已经退出。

上述成功只关闭授权只读 Codex staging 子门；任何数据范围、远端对象、请求完成状态或
退出结果不确定时，完整 Provider 兼容性继续保持 `HOLD / safe-stop`。
