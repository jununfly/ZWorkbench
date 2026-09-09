---
doc-kind: architecture-flow
authority: primary
authority-id: architecture.flow.local-read-only-run
---

# 本地只读运行流

## Question

一个 case-local、read-only 的运行如何从用户入口进入 Control Plane，经过 adapter/owner，
最终形成可解释的 result 或 safe-stop？

## Scope

本页描述当前 `local_read_only_run` 回退入口和目标混合切片共同遵守的可观察边界；它不证明
DSH native scheduler、Codex native approval、真实 Provider 或真实项目写入已经实现。

## Boundaries

运行只能使用显式 workspace、固定 executable、case-local state、read-only policy 和
fake/loopback Provider。任何越界 workspace、未知请求、凭证/网络要求、无法关联 identity
或不可观察的退出都必须停止。

## Trigger

用户或受控 CLI 提交一个 prompt、case root、workspace 和固定 Codex/runtime executable。
Control Plane 先做 preflight，确认路径、policy、Provider、replay mode 和 executable identity
满足当前入口的合同。

## Sequence

1. 创建 parent run 和 case-local workspace/state。
2. 记录 preflight、policy、environment、workspace 和 Provider identity。
3. 启动受监督 adapter；需要时创建 child run 并关联 Worker/DSH/Codex identity。
4. 接收并验证事件、请求、结果和退出；未知 wire message 不继续解释。
5. 将 semantic result、artifact metadata、event digest 和 exit receipt 写入 Owner。
6. 只有不存在未决 effect 且所有关键 identity 可解释时才完成 parent run。

## State and effects

read-only 运行不应产生业务写 effect；生成的文件只限于 case-local evidence/export/backup。
Owner 仍记录 run、attempt、event、result 和 replay metadata。任何未来 reversible write 都
必须单独经过 approval、claim、execute、complete/reconcile，不能借用本流的 read-only 结论。

## Failure or exit behavior

preflight、adapter、Provider、Worker、tool、timeout、cancel 或 process crash 失败时，Owner
记录明确 failure class 并 fail 或 safe-stop。effect 状态未知时先 reconcile；父任务停止时
终止和核对完整子进程树。Worker 完成、模型文本完成或没有观察到错误都不能单独完成 parent。

## Observable evidence

每次运行至少应能从 `run_id` 查询 parent/child run、attempt、event、result、artifact、
policy/provider/environment/workspace digest、adapter/Worker identity 和退出状态；脱敏导出
与 backup 必须可重新校验。`recorded_view` 只读 Owner facts，`simulated_replay` 只读封存
cassette，`live_replay` 默认拒绝。

## Source map

- `src/zworkbench/local_run.py`
- `src/zworkbench/composition.py`
- `src/zworkbench/codex_adapter.py`
- `src/zworkbench/worker_bridge.py`
- `src/zworkbench/replay.py`
- `tests/test_local_run.py`
- `tests/test_local_run_orchestration.py`
- `tests/test_codex_adapter.py`
- `tests/test_replay.py`
- `evaluation/fixtures/w8_local_read_only/v1/README.md`

## Related authority

- [系统概览](README.md)
- [CompositionOwner](ta-composition-owner.md)
- [Codex Worker bridge](ta-codex-worker-bridge.md)
- [可恢复写入边界](ta-reversible-write-boundary.md)
