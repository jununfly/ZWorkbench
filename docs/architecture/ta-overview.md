---
doc-kind: architecture-overview
authority: primary
authority-id: architecture.overview
---

# ZWorkbench 架构概览

## Question

ZWorkbench 如何把可替换的 Agent runtime、进程外 Coding Worker 与稳定的
CompositionOwner 组合起来，同时不产生第二个 durable state owner？

## Scope

本页表达目标架构和当前可运行回退基线之间的边界。目标组合是 DSH 主 Harness、
进程外 Codex Coding Worker、ZWorkbench Control Plane 与 CompositionOwner；当前产品入口
仍可能是 Codex-only 的 `local_read_only_run`。代码、测试和运行产物负责证明当前实现，
不能把目标架构自动解释为已实现。

## Boundaries

- DSH 持有顶层 Agent loop、session、上下文、插件组合和任务路由，但不持有跨 Run canonical state。
- Codex Worker 负责代码理解、测试、构建和可审查 diff，但不拥有 parent run、approval、
  scheduler 或 CompositionOwner。
- Control Plane 负责 preflight、Worker supervision、workspace/artifact、Provider、
  evidence/replay 和退出编排。
- CompositionOwner 是唯一 durable owner；未知 identity、permission、effect、Provider
  或 replay 状态都必须进入 `unknown` / safe-stop。

## System boundary

~~~text
User / CLI
  → ZWorkbench Control Plane
    → DSH Main Harness
      → Codex Coding Worker
    → CompositionOwner
    → Provider Adapter / Workspace / Evidence-Replay
~~~

第一混合切片只允许 case-local workspace、固定 artifact、只读或隔离 worktree 与
fake/loopback Provider。真实 Provider、真实主工作区写入、Git push、部署、Webhook 和
live replay 都是显式的后续验证边界。

## Major parts

| Part | Responsibility | Durable ownership |
|---|---|---|
| DSH Main Harness | 顶层 Agent loop、session、插件组合、上下文和路由 | 仅持有 runtime/session 输入 |
| Codex Coding Worker | 代码任务、测试、构建和可审查 diff | 仅持有本次 Worker 运行状态 |
| Control Plane | 入口、preflight、监督、workspace、Provider、evidence/replay、退出 | 通过 Owner API 记录事实 |
| CompositionOwner | run、attempt、event、effect、result、approval、replay metadata、backup/restore | 唯一 durable source of truth |
| Host / Provider boundaries | 执行强制、Provider 请求和外部资源边界 | 不得生成第二份跨 Run canonical state |

## Source map

- `../../AGENTS.md`：目标架构、ownership、不变量和安全边界。
- `../../ZJ-CONTEXT.md`：Workbench、Run、Provider、effect、unknown 和 replay 词汇。
- `../../src/zworkbench/composition.py`：CompositionOwner 的当前 durable 实现。
- `../../src/zworkbench/dsh_runtime.py`：DSH artifact-mode H1 runtime seam。
- `../../src/zworkbench/worker_bridge.py`：Worker transport、identity 和进程监督 seam。
- `../../src/zworkbench/local_run.py`：当前 local-read-only orchestration。
- `../../src/zworkbench/replay.py`：recorded/simulated/live replay 边界。
- `ta-workbench-user-surface.md`：工作台的稳定信息结构、读模型与安全展示边界。
- `../../tests/test_composition.py`、`../../tests/test_dsh_runtime.py`、`../../tests/test_worker_bridge.py`、
  `../../tests/test_local_run.py`、`../../tests/test_replay.py`：产品行为验证。
- `../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md`：已接受的 owner 决定。

## Related authority

- [分层与依赖](ta-layers.md)
- [DSH runtime 集成](ta-dsh-runtime-integration.md)
- [Codex Worker bridge](ta-codex-worker-bridge.md)
- [CompositionOwner](ta-composition-owner.md)
- [本地只读运行流](ta-local-read-only-flow.md)
- [可恢复写入边界](ta-reversible-write-boundary.md)
- [工作台用户界面](ta-workbench-user-surface.md)
