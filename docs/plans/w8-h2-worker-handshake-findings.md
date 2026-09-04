# W8 H2 Worker handshake findings

状态：`product execution / owner-backed + fixture-composed verified`
日期：2026-09-04

本轮完成 `1-9-3` 的最小 DSH → Worker bridge seam。新增的
[WorkerBridge](../../src/zworkbench/worker_bridge.py) 只负责进程边界、严格
`zworkbench.worker.v1` JSONL handshake 和 correlation；它不运行 Agent loop、不调用
Provider、不执行 capability，也不把 Worker session 提升为 durable state。

## 实现边界

- Worker 通过固定 argv、`shell=false`、case-local workspace 和新进程组启动。
- Bridge 发送一条 `handshake.request`，只接受一条严格的 `handshake.response`。
- response 必须具备完整 parent/child/attempt/DSH/Codex identity，并与 request 的
  provider、Worker artifact/schema、replay mode、policy/environment/workspace identity
  精确一致。
- CompositionOwner 持有唯一 durable truth：child handshake Run、request/response、
  error、exit receipt 和 parent event/result 都进入 owner；握手成功只完成 child，parent
  继续保持 `running`，等待后续 H3/H4 显式收口。
- unknown schema/message/field、unknown identity、identity/provenance mismatch、
  malformed JSONL、超时、crash 和 nonzero exit 都双侧 `safe_stopped`，不产生 semantic
  success；结束时不保留 bridge 进程。
- 继承环境仅限非敏感的运行时基础字段，并注入 parent/child/attempt/schema correlation；
  Provider 仅允许 loopback identity。

## Fixture-level result

隔离 fixture 位于 [`evaluation/fixtures/w8_worker_handshake/v1`](../../evaluation/fixtures/w8_worker_handshake/v1)，
测试入口为 [`tests/test_worker_bridge.py`](../../tests/test_worker_bridge.py)，可重复 runner 为
[`run_w8_worker_handshake.py`](../../evaluation/runner/run_w8_worker_handshake.py)。

验证命令：

```text
PYTHONPATH=src python -m unittest tests.test_worker_bridge -v
PYTHONPATH=src python evaluation/runner/run_w8_worker_handshake.py --output <new-empty-dir>
PYTHONPATH=src python -m unittest discover -s tests -p 'test*.py'
```

实际结果：定向测试 `5/5 pass`，runner `11/11 pass`，全量产品测试 `73/73 pass`。

| 场景 | 观察 | 结果 |
|---|---|---|
| success | child completed；parent running；Codex thread/turn 和 DSH session/turn 完整关联；exit 0 | pass |
| unknown identity | identity incomplete；双侧 safe-stop；无 semantic result | pass |
| schema / identity / provenance mismatch | strict reject；记录 error 与 exit receipt | pass |
| unknown message / field | fail-closed；不解释未知 wire | pass |
| malformed / crash | 不产生 response 也不完成；记录退出证据并 safe-stop | pass |
| nonzero / timeout | 退出码或超时可见；进程组被清理；无孤儿 bridge | pass |

## Evidence boundary and remaining gates

本结果是 `owner-backed + fixture-composed` 证据，只证明 ZWorkbench bridge contract、
CompositionOwner correlation 和失败语义。它不证明真实 Codex app-server/CLI artifact
兼容性，不证明 H3 只读 coding、H4 recovery/lifecycle、H5 replay、宿主 sandbox 或真实
Provider 行为；这些仍保持 roadmap 的后续节点或 HOLD。

fixture、runner 和测试不访问网络、不读取真实凭证、不写真实工作区、不执行 capability 或
effect。机器生成的 runner output 应保留在临时目录或 ignored evaluation 目录，不提交历史
运行现场。
