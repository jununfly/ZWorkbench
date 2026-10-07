---
doc-kind: architecture-subsystem
authority: primary
authority-id: architecture.subsystem.codex-worker-bridge
---

# Codex Worker bridge

## Question

ZWorkbench 如何监督一个进程外 Codex Coding Worker，并保证 wire message、版本、Provider、
workspace、policy 与 parent/child identity 可验证、可停止、可审计？

## Scope

本页覆盖 H2 handshake、H3 bounded read-only coding 和 Worker 进程生命周期 seam。Codex
内部 Agent loop、Codex session 文件和 Provider 日志不是 ZWorkbench canonical state；生成 diff
与应用 diff 也不是同一个 effect。

## Boundaries

- bridge 是 transport/correlation seam，不是第二个 Agent loop、Provider router 或 permission owner。
- Worker 通过 `zworkbench.worker.v1` envelope 与 bridge 通信；未知 schema、message 或字段
  fail-closed。
- Worker 默认只读或在隔离 worktree 生成可审查 artifact；真实写入、Git push、部署和 live
  replay 需要独立 gate。
- parent stop、cancel、timeout 或 crash 必须终止并核对完整 Worker 进程树。

## Responsibility

bridge 启动固定 executable，发送带有 artifact/schema/provider/policy/environment/workspace
identity 的 handshake，验证 response 与 coding result 的关联，转发 owner-visible event/result，
并为取消、超时、异常退出和 safe-stop 保留 receipt。

## Owned state

bridge 不持有跨 Run canonical state。`WorkerHandshakeResult`、`WorkerCodingResult`、进程退出
信息和 identity-bound artifact descriptors 是 adapter 输出，由 CompositionOwner 记录；Worker
自身 session/rollout 只能作为输入或 evidence。

## Interface

`IdentityChain` 显式携带 `parent_run_id`、`child_run_id`、`attempt_id`、DSH session/turn、
Worker run、Codex thread/turn、event 和 artifact identity。消息类型包括 handshake、capability、
event、result、cancel 和 error；Provider identity、Worker artifact/schema identity、replay mode、
policy/environment/workspace digest 必须与请求一致。

## Failure behavior

identity 不完整或不匹配、Provider/Worker/schema identity 漂移、payload 未知、secret 泄漏、
stdout/stderr/line 超限、启动失败、超时或无法清理进程树时，bridge 记录错误并 safe-stop
关联的 child/parent run。Worker 完成不等于 parent run 完成，也不等于 diff 已应用。

## Source map

- `../../src/zworkbench/worker_contract.py`
- `../../src/zworkbench/worker_bridge.py`
- `../../src/zworkbench/composition.py`
- `../../tests/test_worker_bridge.py`
- `../../tests/test_composition.py`
- `../../evaluation/runner/run_w8_worker_coding.py`
- `../../AGENTS.md`
- `../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md`

## Related authority

- [系统概览](ta-overview.md)
- [分层与依赖](ta-layers.md)
- [DSH runtime 集成](ta-dsh-runtime-integration.md)
- [CompositionOwner](ta-composition-owner.md)

## 执行层基本功能讨论结论（2026-10-07）

> 以下为 zj-discuss「执行层应实现哪些基本功能」讨论的耐久沉淀（sub-02 Worker 调度与监督）。过程讨论稿已删除，本段为唯一权威结论。

### sub-02：Worker 调度与监督

- **IMPLEMENTED（baseline 内落地）：** 传输契约 + identity 绑定 + 未知 wire fail-closed；H2 handshake 验收；Provider 维度 loopback-only 边界；进程树清理 + exit receipt。
- **UNKNOWN / BLOCKED（须显式标注，不得据「代码存在」标 DONE）：**
  - H1 Bootstrap 负向测试、H3 read-only coding fixture、H4 lifecycle（cancel/stop_parent/recover）fixture **全部零覆盖** → H1/H3/H4 标 BLOCKED/unknown。
  - 单发监督无心跳；长连接心跳属 TARGET/unknown。
  - cleanup 断言 + 孤儿零残留证明 UNKNOWN；exit receipt 无子进程树快照字段。
- **IdentityChain 完成性分层（P1，须 ADR）：** parent/child/attempt/dsh/event/artifact 为 required；codex_thread/turn 仅在确认 Codex Worker 时 required，否则允许 UNKNOWN；停止 fake fixture 编造 codex 身份。
- **Q4 双重钳制（P0）：** `worker_bridge` 请求构造处加 `assert replay_mode=="normal"`；`WorkerBridge` 加显式 `real_worker_mode: bool = False`，开真实模式须 ADR + owner gated reason。
- **真实架构前硬前置（backlog）：** host sandbox（seatbelt/namespace/unshare）作为真实 Workspace 写入前置；`_reject_secrets` 值级扫描；`semantic_result` 出站脱敏；`codex_adapter.close()` stderr 脱敏；bridge 进程异常退出注册 reaper 兜底 killpg；worker 可执行体 digest 实测校验。

### 交叉引用

- [终止与资源生命周期](ta-termination-resource-lifecycle.md)
- [Provider 适配与降级](ta-provider-adaptation.md)
- [执行层 effect 授权](ta-execution-effect-authorization.md)
