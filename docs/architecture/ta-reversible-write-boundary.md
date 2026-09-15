---
doc-kind: architecture-cross-cutting
authority: primary
authority-id: architecture.cross-cutting.reversible-write-boundary
---

# 可恢复写入边界

## Question

在什么条件下，ZWorkbench 才能从 local-read-only baseline 扩展到可恢复、可审计的本地写
effect？

## Scope

本页是跨 Owner、Worker、Host、Workspace 和 Replay 的共享安全规则。当前写入资格保持
`HOLD`：case-local reversible fake sink 可以继续验证合同，但不能推出真实项目写入、Git
push、部署或 Provider 远端 effect 已获准。

## Boundaries

组合式 approval、配置 preflight 或单次 fixture pass 都不能冒充 OS/host enforcement；
Codex native approval、composition approval 和宿主拒绝必须分别计账。任一关键 identity、
effect 状态、reconcile 结果、schema、artifact 或 host boundary 为 `unknown`，就保持
safe-stop，不自动 retry。

## Shared rule

所有写 effect 遵循：

~~~text
request → policy → decision → claim → execute → complete/reconcile
~~~

approval 必须精确绑定 operation、action、resource 和 idempotency key；重复请求不能产生
第二次物理副作用。写入前、执行后未提交、提交后中断和进程退出等边界都必须由同一个
CompositionOwner 记录并可恢复。放行真实本地项目前，宿主必须证明 workspace、state、
credential 和 process boundary 的实际强制能力。

## Consumers

- **CompositionOwner**：持有 approval、effect、claim、completion、uncertain/reconcile、
  backup 和 rollback receipt。
- **Control Plane / local run**：保持 read-only 默认，拒绝未知边界并控制 case-local workspace。
- **Codex Worker bridge**：把 Worker 请求与 parent/child identity 关联；生成 diff 与应用 diff
  分离。
- **Host / broker**：提供独立于配置声明的路径、进程和网络强制；其结果不能由 adapter 猜测。
- **Replay / evidence**：区分 recorded view、cassette-only simulated replay 和默认拒绝的
  live replay，不以回放执行真实 effect。

## Source map

- `../../src/zworkbench/composition.py`
- `../../src/zworkbench/local_run.py`
- `../../src/zworkbench/worker_bridge.py`
- `../../src/zworkbench/replay.py`
- `../../tests/test_composition.py`
- `../../tests/test_local_run.py`
- `../../tests/test_worker_bridge.py`
- `../../tests/test_replay.py`
- `../../evaluation/fixtures/w8_capability_broker/v1/README.md`
- `../../evaluation/fixtures/w8_host_broker/v1/README.md`
- `../../evaluation/fixtures/w8_external_sandbox_native_approval/v1/README.md`
- `../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md`

## Related authority

- [系统概览](ta-overview.md)
- [CompositionOwner](ta-composition-owner.md)
- [本地只读运行流](ta-local-read-only-flow.md)
- [Codex Worker bridge](ta-codex-worker-bridge.md)
