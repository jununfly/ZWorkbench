---
doc-kind: architecture-subsystem
authority: primary
authority-id: architecture.subsystem.dsh-runtime-integration
---

# DSH runtime 集成

## Question

ZWorkbench 如何以可追溯、可回滚的外部 artifact 方式接入 DSH，而不 vendoring DSH
源码、不复制 Agent loop，也不把 runtime session 升级为 durable owner？

## Scope

当前实现覆盖 artifact-mode H1 bootstrap seam：读取严格 manifest、校验 artifact/lock/receipt/profile
digest，在 case-local 环境中以无 shell 子进程启动 DSH，并把 bootstrap 事件关联到 owner。
Worker handshake、完整 DSH runtime、真实 Provider 和生产部署不由本页宣称已实现。

## Boundaries

- runtime 必须绑定 source commit、artifact、dependency lock、build receipt、profile、schema、
  policy、Provider、environment 和 workspace identity。
- H1 只接受 artifact mode、case-local workspace、read-only policy 和 loopback/fake Provider。
- adapter 只负责 manifest、进程和事件边界，不执行 DSH Agent loop、不调用 Provider、不执行工具。
- 未知 manifest 字段、digest 不匹配、路径越界、未声明环境变量、未知 bootstrap message 或
  无法关联 identity 时，owner 必须 safe-stop。

## Responsibility

runtime adapter 负责解析并验证 pinned manifest，创建受限环境，启动外部 DSH，转发有限的
bootstrap 事件，记录退出 receipt，并在失败时停止进程树。artifact cache、DSH session 和插件
状态只能作为输入、缓存或 evidence。

## Owned state

runtime adapter 不拥有跨 Run durable state。它只产生本次 runtime 的 artifact/profile/provider/
policy/environment/workspace identity、事件 digest、session identity 和 exit result；这些事实由
CompositionOwner 持久化和关联。

## Interface

H1 的稳定 seam 是 `zworkbench-dsh-runtime-manifest/v1`、`zworkbench-dsh-runtime-adapter/v1`
和 `zworkbench.dsh.bootstrap/v1`。当前允许的 bootstrap message 是
`bootstrap.started` 与 `bootstrap.ready`，并要求 `parent_run_id`、`dsh_session_id`、status
和 profile identity。启动使用显式 argv、受限环境和无 shell 子进程。

## Failure behavior

manifest、provenance、Provider、environment、workspace、protocol、启动或退出任一校验失败，
都不是成功的 runtime。adapter 记录错误 code，安全停止 owner run，并尽力终止和核对完整子进程树；
无法确认外部结果时保持 `unknown`，不自动 retry。

## Source map

- `src/zworkbench/dsh_runtime.py`
- `src/zworkbench/composition.py`
- `tests/test_dsh_runtime.py`
- `tests/test_composition.py`
- `AGENTS.md`
- `docs/references/optional-real-provider-staging.md`

## Related authority

- [系统概览](README.md)
- [分层与依赖](ta-layers.md)
- [Codex Worker bridge](ta-codex-worker-bridge.md)
- [CompositionOwner](ta-composition-owner.md)
