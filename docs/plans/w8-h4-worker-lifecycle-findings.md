# W8 H4 Worker lifecycle findings

状态：`product execution / owner-backed + fixture-composed verified`
日期：2026-09-04

本轮完成 `1-9-5` 的最小 Worker 生命周期与恢复 seam。新增的生命周期控制仍位于
[WorkerBridge](../../src/zworkbench/worker_bridge.py)，CompositionOwner 继续是 parent/child
Run、attempt、event、result 和状态的唯一 durable owner。Worker 进程只在单次 Run 内存在，
以独立 process group 启动，退出时保留脱敏的 argv digest、stderr digest/bytes、退出码、信号、
终止原因、进程组清理和 orphan count receipt。

## 实现边界

- `WorkerBridge.cancel(parent_run_id)` 和 `stop_parent(parent_run_id)` 是可从另一个控制线程
  调用的显式生命周期 API；它们写入 owner 的 stop event/result，分别产生
  `worker_cancelled` / `worker_parent_stopped`，并安全停止 parent 与 child。
- timeout、cancel、parent stop 和 bridge failure 都先阻止 semantic completion，再清理
  Worker process group。停止顺序是全组 `SIGTERM`，超时后全组 `SIGKILL`，随后轮询确认 group
  不再存在；确认失败不会被当作成功。
- child non-zero exit 记录为 `child_crash`；没有完整 response/result 时不会写入 semantic
  success。未知 wire、identity、provenance 和不完整结果仍沿用 H2/H3 的双侧 safe-stop。
- `recovery_mode=True` 是显式 owner-backed 配置。对已确认清理且无 unresolved effect 的
  timeout/exit failure，parent 进入 `recovering`；`recover_handshake()` 或
  `recover_read_only_coding()` 只能从 recovering 启动，并创建新的 child/attempt。旧 child
  及其 exit/error receipt 保留不覆盖；恢复来源必须是同一 parent 的 terminal child。
- `CompositionOwner.begin_recovery()` 拒绝仍有 `claimed`、`uncertain` 或 `unknown` effect
  的 Run，避免把未知副作用误当成可重试生命周期错误。普通 H2/H3 bridge 默认仍是双侧
  safe-stop，历史 H2 失败语义不被静默改写。

## 验证结果

生命周期 fixture、runner 和测试位于：

- [`evaluation/fixtures/w8_worker_lifecycle/v1/worker_fixture.py`](../../evaluation/fixtures/w8_worker_lifecycle/v1/worker_fixture.py)
- [`evaluation/runner/run_w8_worker_lifecycle.py`](../../evaluation/runner/run_w8_worker_lifecycle.py)
- [`tests/test_worker_lifecycle.py`](../../tests/test_worker_lifecycle.py)
- [`tests/test_w8_worker_lifecycle.py`](../../tests/test_w8_worker_lifecycle.py)

实际命令和结果：

```text
PYTHONPATH=src python -m unittest tests.test_worker_lifecycle tests.test_w8_worker_lifecycle -v
7/7 pass

PYTHONPATH=src python evaluation/runner/run_w8_worker_lifecycle.py --output <new-empty-dir>
status=pass; passed_scenarios=6; scenario_count=6
```

| 场景 | 关键观察 | 结果 |
|---|---|---|
| `cancel` | 控制 API 可观测；parent/child safe-stopped；退出原因 `cancelled`；group clean | pass |
| `timeout` | 超时不产生 semantic success；退出原因 `timeout`；group clean | pass |
| `crash` | exit code `23`；退出原因 `child_crash`；无 semantic result | pass |
| `parent-stop` | parent stop 与 cancel 使用不同 error/reason；双侧 safe-stop | pass |
| `descendant` | fixture 创建 descendant；全组清理触发 forced kill；orphan count `0` | pass |
| `recovery` | 首个 child/attempt 保留；parent 进入 recovering；新 child/attempt 完成并带 recovery source identity | pass |

H4 runner 的 machine checks：

- `orphan_processes_zero=true`；6/6 场景 process group clean；
- `status_loss_zero=true`：每个控制线程都结束，owner 可重开并读取 parent/child 状态；
- `unauthorized_effects_zero=true`：所有场景 parent/child effect ledger 均为空；
- recovery 不覆盖旧 attempt，且新的 attempt 退出 receipt 可读。

## Evidence boundary and non-claims

结果等级是 `owner-backed + fixture-composed`：同时验证了真实本机 process-group 边界和
CompositionOwner durable 状态，但不是 DSH 原生能力、OS/host sandbox 或生产 supervisor 的
证明。H4 通过不升级以下状态：

- 不证明 H5 recorded/simulated/live replay 和 evidence completeness；
- 不证明真实 Codex runtime、真实远程 Provider compatibility、Provider failover 或
  Provider-side exit；
- 不证明真实主工作区写入、apply、Git push、部署或其他不可逆 effect；
- 不处理此前已暴露的凭证/证据问题，也不读取或重新配置任何 API key。

运行现场应写入新的临时或 ignored evidence 目录；不提交大体量历史 runs、raw response 或
凭证。下一节点为 `1-9-6` H5 Evidence/replay。
