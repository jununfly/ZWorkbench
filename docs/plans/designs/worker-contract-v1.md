# DSH–Codex Worker Contract v1

状态：`product execution / Stage 0 frozen`

本文冻结 DSH 主 Harness 与进程外 Codex Coding Worker 之间的第一版消息边界。它是
[目标架构](dsh-codex-hybrid-target-architecture.md) 中 Bridge 的输入校验合同，不是
Codex app-server 协议的替代品，也不启动 Worker、Provider、工具或 CompositionOwner。

## 1. Contract boundary

```text
DSH plugin / routing
        │ zworkbench.worker.v1 JSON envelope
        ▼
ZWorkbench Bridge + CapabilityFacade
        │ owner-backed decision / supervised process boundary
        ▼
Codex Coding Worker
```

CompositionOwner 仍是唯一 durable owner。Envelope 是跨进程的可验证消息；它不授权
Worker 直接写 owner 数据库，也不把 DSH/Codex session 变成 canonical state。

首期允许的执行范围是 case-local、fake/loopback Provider、只读或隔离 workspace。
真实写入、Git push、部署、Webhook 和 live replay 需要后续独立 gate。

## 2. Wire envelope

每个消息都必须是严格 JSON object，`schema` 固定为 `zworkbench.worker.v1`。
v1 的顶层字段固定如下：

```json
{
  "schema": "zworkbench.worker.v1",
  "message_type": "handshake.request",
  "identity": {
    "parent_run_id": "...",
    "child_run_id": "...",
    "attempt_id": "...",
    "dsh_session_id": "...",
    "dsh_turn_id": "...",
    "worker_run_id": "...",
    "codex_thread_id": "...",
    "codex_turn_id": "...",
    "event_id": "...",
    "artifact_id": "..."
  },
  "provider_identity": {
    "provider": "fake-loopback",
    "model": "fake-model",
    "endpoint": "http://127.0.0.1:11434",
    "transport": "loopback-only",
    "metadata": {}
  },
  "replay_mode": "normal",
  "policy_digest": "sha256:...",
  "environment_digest": "sha256:...",
  "workspace_digest": "sha256:...",
  "worker_artifact_identity": {
    "name": "codex-worker",
    "version": "...",
    "digest": "sha256:...",
    "source": "pinned-package"
  },
  "worker_schema_identity": {
    "name": "codex-app-server",
    "version": "...",
    "digest": "sha256:...",
    "source": "pinned-schema"
  },
  "capability_request": null,
  "payload": {}
}
```

所有 identity key 都必须出现。尚未暴露的身份使用字面值 `unknown`，不能猜测补齐。
`WorkerEnvelope.validate_worker_completion()` 会拒绝任何仍有 `unknown` 的完成结果。
`provider_identity`、payload 和 capability arguments 只允许非敏感描述；API key、token、
cookie、password、authorization 等原始凭证字段在进入 envelope 前即拒绝。

## 3. Message types and state meaning

v1 allowlist：

| `message_type` | 作用 | 是否可作为 Worker 完成 |
|---|---|---:|
| `handshake.request` | Bridge 请求建立 Worker contract | 否 |
| `handshake.response` | Worker 返回 artifact/schema 和 Codex identity | 否 |
| `capability.request` | 请求 Host Capability Facade 判定 | 否 |
| `capability.response` | 返回一个已记录的 capability decision | 否 |
| `event` | 传递可关联的运行事件 | 否 |
| `result` | 返回 Worker 语义结果和 artifact 引用 | 仅显式 `payload.status=completed` 且 identity 完整时 |
| `cancel` | 请求取消 Worker | 否 |
| `error` | 返回结构化错误或 safe-stop 原因 | 否 |

未知 `message_type`、未知 schema 或未知顶层字段立即产生 `safe_stop=true` 的
`SafeStopRequired`。版本兼容通过新 schema 处理，不通过猜测未知字段继续运行。

Worker `result` 的完成只表示 Codex Worker 完成自己的 contract。它不表示：

- parent Run 已完成；
- semantic result 已写入 CompositionOwner；
- diff 已应用到真实 workspace；
- approval/effect 已完成或已 reconcile。

Parent Run 仍须由 owner 检查 child 状态、所有关键 event/artifact、semantic result 和
unresolved effect 后才能完成。

## 4. Identity and provenance

`identity` 固定维护以下可查询关系：

```text
parent_run → child_run → attempt → dsh session/turn
           → worker_run → codex thread/turn → event/artifact
```

除 identity chain 外，完成态还必须有完整的：

- Provider identity：provider、model、endpoint、transport；
- Worker artifact identity：name、version、digest、source；
- Worker schema identity：name、version、digest、source；
- policy、environment、workspace digest；
- replay mode。

digest 是 provenance 绑定，不是内容本身。凭证只能以外部 credential reference 或
fingerprint 在更高层按既有安全规则管理，不能通过本合同传输 credential value。

## 5. Capability Facade

`CapabilityRequest` 固定包含：

```text
request_id
capability
operation
resource
effect_class
declared_permissions[]
arguments{}
```

第一版 allowlist 及其声明如下：

| capability | effect | permission |
|---|---|---|
| `workspace.read` | `none` | `workspace.read` |
| `workspace.list` | `none` | `workspace.read` |
| `test.run` | `local_process` | `process.local_read` |
| `artifact.emit` | `owner_record` | `owner.artifact_write` |
| `provider.infer` | `provider_request` | `provider.infer` |

`CapabilityFacade` 只返回 allow/拒绝决策，不执行请求。以下情况必须 safe-stop：

- capability 不在 allowlist；
- effect class 不在已知集合；
- capability 声明的 effect 与策略不一致；
- declared permissions 与策略不一致；
- parent/child/attempt/worker/event 等关联身份不完整；
- `recorded_view`、`simulated_replay` 或 `live_replay` 试图授权 Worker、Provider 或工具。

因此，replay 入口必须在更高层选择 `recorded_view` 或 `simulated_replay` 数据路径；
它不能把一个普通 capability request 换个 replay mode 后继续执行。

## 6. Fail-closed contract

| 输入问题 | v1 行为 | 完成状态 |
|---|---|---|
| 未知 wire message/schema/field | 拒绝并 `safe-stop` | 不可完成 |
| 未知 capability | 拒绝并 `safe-stop` | 不可完成 |
| 未知 effect | 拒绝并 `safe-stop` | 不可完成 |
| identity 缺失或为 `unknown` | 保留 unknown，完成校验失败 | 不可完成 |
| Provider/policy/artifact/workspace/environment 不完整 | 保留 unknown，完成校验失败 | 不可完成 |
| replay 请求真实执行 | 拒绝并 `safe-stop` | 不可完成 |
| 原始凭证进入消息 | 在构造/解析时拒绝 | 不可完成 |

本文件对应实现和行为测试：

- [`src/zworkbench/worker_contract.py`](../../../src/zworkbench/worker_contract.py)
- [`tests/test_worker_contract.py`](../../../tests/test_worker_contract.py)

## 7. Stage 0 exit criteria

`1-9-1` 只有在以下条件同时满足时完成：

1. v1 envelope 可以 canonical JSON round-trip；
2. identity、Provider、artifact/schema 和 environment/policy/workspace provenance 有固定字段；
3. unknown wire/capability/effect 都是可断言的 safe-stop；
4. replay 不可通过 CapabilityFacade 启动真实执行；
5. incomplete identity 不能伪装成 Worker completed；
6. 测试和文档不包含真实凭证、生产数据或历史运行产物。

完成本节点后，下一节点才可以实现 H1 Bootstrap；H1 不得把本契约的校验责任重新复制到
第二个 Agent loop 或第二个 durable owner 中。
