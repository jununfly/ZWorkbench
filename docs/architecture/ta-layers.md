---
doc-kind: architecture-layers
authority: primary
authority-id: architecture.layers.core
---

# ZWorkbench 分层与依赖

## Question

哪些层可以依赖彼此，哪些状态和副作用边界必须由 CompositionOwner 或宿主强制控制？

## Scope

本页只定义目标组合的责任层和允许依赖；具体 wire schema、Provider 合同和 OS sandbox
行为以代码、测试和受控 fixture 为准。

## Boundaries

层之间通过显式 contract、Host Capability Facade 或 Owner API 连接。插件、Worker、Provider
和观测投影不能直接写 CompositionOwner SQLite，也不能复制另一套 Agent loop。

## Layers

1. **User / CLI**：提交 prompt、选择 case-local workspace 和查看脱敏结果。
2. **Control Plane**：执行 preflight、创建/监督 run、编排 workspace、Provider、evidence/replay
   和退出。
3. **DSH Main Harness**：持有顶层 Agent loop、session、插件组合、上下文和任务路由。
4. **Worker / Adapter**：通过固定版本、固定 schema 的外部 bridge 启动并关联 Codex Worker。
5. **CompositionOwner**：持有唯一 durable state，并裁决 policy、approval、effect、reconcile
   和结果完成。
6. **Host / Provider / Workspace**：分别提供执行强制、模型请求和隔离文件边界，不持有
   跨 Run canonical truth。

## Allowed dependencies

| Caller | May depend on | Must not become |
|---|---|---|
| CLI / Control Plane | DSH runtime、Worker bridge、Owner、Provider/Workspace facade | 第二个 scheduler 或 state owner |
| DSH plugin | Host Capability Facade、声明的 Provider/Owner/子进程能力 | 直接数据库 writer 或隐式后台服务 |
| Worker bridge | 固定 Worker executable、wire contract、Owner 事件/结果接口 | Agent loop、Provider router 或 approval owner |
| CompositionOwner | 本地 durable storage 和可验证 receipt | 外部 runtime session 的别名 |
| Provider / host boundary | 显式 request、policy、claim、execute、reconcile 流程 | 静默 fallback 或未经授权 effect |

## Source map

- `../../src/zworkbench/composition.py`
- `../../src/zworkbench/dsh_runtime.py`
- `../../src/zworkbench/worker_bridge.py`
- `../../src/zworkbench/worker_contract.py`
- `../../src/zworkbench/local_run.py`
- `../../tests/test_composition.py`
- `../../tests/test_dsh_runtime.py`
- `../../tests/test_worker_bridge.py`
- `../../AGENTS.md`
- `../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md`

## Related authority

- [系统概览](ta-overview.md)
- [DSH runtime 集成](ta-dsh-runtime-integration.md)
- [Codex Worker bridge](ta-codex-worker-bridge.md)
- [CompositionOwner](ta-composition-owner.md)
