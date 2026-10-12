---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.worker.heartbeat.liveness
---

# ADR 0012：Worker 长连接心跳监督（1-7-5）—— 间隔 / 超时 / owner 计账 / 失败语义 / 与 reaper 的关系

> 状态 `accepted`：经 Human 于 2026-10-12 确认。据此实现产品代码（roadmap 1-7-5 转 in_progress）。

## Context

`worker_bridge` 当前对真实 Worker 子进程只记录**离散事件**：handshake、coding
请求/响应、error、exit（`worker_bridge.py` 的 `record_result`/`record_event` 调用）。
它已有**请求级**超时——`worker_timeout` / `worker_exit_timeout`（`worker_bridge.py:798`）
管"单次 coding 请求等不到响应"。但它**没有"长连接存活"监督**：一个真实 Worker 在
handshake 之后、下一次 coding 请求之前的长时间空闲里，若静默卡死或连接掉线，ZWorkbench
侧毫无感知，直到下一次 coding 请求触发 `worker_timeout`——而那要等有人去发请求。

后果是一个覆盖盲区：
- 进程还活着、stdout 管道静默、但已不再产出有效工作（挂死 / 内部死锁 / 网络半开）；
- 或连接已半开失效、子进程实际已不可达，却仍被当成"running"。

`1-7-2` 把孤儿计账诚实化（zero/nonzero/unknown），但那只覆盖"进程退出后"的残留，不覆盖
"存活但失联"的窗口。本能力属**产品代码**（非 fixture），由 `1-7-2` 切出为 `1-7-5`，
须先定死口径再实现。

同时，owner 侧目前 `worker.*` 事件 kind 与 worker error code（`real_mode_replay_conflict`、
`replay_mode_not_normal`、`codex_identity_fabricated`、`worker_timeout`、`worker_exit_timeout`、
`worker_parent_stopped`、`worker_cancelled`、`worker_exit_nonzero`、`worker_start_failed`、
`worker_stream_missing`、`worker_request_failed`）都是 `worker_bridge.py` 内联字面量，
**无集中词汇表**。ADR 0009（L44）要求 owner 侧单一词汇表 + 一致性测试，本 ADR 一并收编。

## Decision

### 1. 心跳间隔（interval）—— 单向 supervisor 观测，不要求 Worker 主动 ping

新增常量 `WORKER_HEARTBEAT_INTERVAL_SEC = 30.0`。

心跳由 **ZWorkbench supervisor 侧**的一个轻量后台线程驱动，每 `interval` 检查一次
`now - last_activity_ts`。**不要求 Worker 协议新增 ping/pong 方法**——v1 Worker 子进程协议
无 heartbeat 动词，加双向 ping 要改 `worker_contract.py` + 所有 fixture，收益低且破坏
fail-closed。单向观测是最小且诚实的活体监督：

- supervisor 每 `interval` 观测两条 ZWorkbench 侧可知的活体信号：
  1. 子进程仍在（`process.poll() is None`）；
  2. 距上次 `last_activity_ts` 未超过心跳超时（见决策 2）。
- `last_activity_ts` 在以下两处更新（共享、加锁）：
  - 每次从 Worker stdout 管道读到合法字节（ `_run_process` 的 `on_line` ）；
  - 每次 handshake / coding 响应落账（`record_result("worker.handshake" / "worker.coding")`）。

### 2. 超时判定（timeout）—— 纯函数，可测，与请求级超时正交

新增常量 `WORKER_HEARTBEAT_TIMEOUT_SEC = 90.0`（= 3×interval，留 2 个 interval 抖动余量）。

判定规则抽成纯函数（便于单测、不依赖线程）：

```
heartbeat_lost(now, last_activity_ts, timeout) -> bool:
    return (now - last_activity_ts) > timeout
```

与 `worker_timeout` 的关系：**正交，不重叠**。
- `worker_timeout` = 单次 coding 请求的请求级等待超时（bounded wait for one response）；
- `heartbeat_lost` = 两次请求之间长连接空闲期的 liveness 超时（no traffic, connection should still be alive）。

### 3. owner 计账字段（event kind & evidence_source）—— 接入既有账本，贯彻 ADR 0009 单一词汇表

3.1 **新增 worker 事件 kind 词汇**，注册进**新建的 `WORKER_EVENT_KINDS` 常量集**
（`worker_bridge.py` 或独立 `worker_vocabulary.py`，与 `provider_vocabulary.py` 同范式）：
- `worker.heartbeat.tick` —— 周期活体观测（用 `record_event`）；
- `worker.heartbeat.lost` —— 丢失判定（用 `record_event`）；
- `worker.heartbeat.recovered` —— 恢复（用 `record_event`）。

3.2 **evidence_source = `EVIDENCE_SOURCE_NATIVE`**（来自 `composition.py:58`，
与 `dsh_runtime` 同口径）。心跳 tick/lost/recovered 由 ZWorkbench supervisor **自身产出**，
**不是** `EVIDENCE_SOURCE_OUTER_COMPOSED`（后者是"Worker 响应被 ZWorkbench 组装"的场景，
心跳并非 Worker 响应）。

3.3 **新增 error code `heartbeat_lost`**，注册进**新建的 `WORKER_ERROR_CODES` 常量集**，
一并收编决策 1 / Context 中列出的所有 worker error 内联字面量，消灭散落。一致性测试保证
运行代码不 emit 未注册的 kind / code（沿用 `provider_vocabulary.KNOWN_DENY_CODES` 的同款范式）。

3.4 **计账 payload 字段**（写进 `worker.heartbeat.*` 事件的 `value`）：
`last_activity_ts`、`interval_sec`、`timeout_sec`、`observed_process_alive`(bool)、
`now_ts`、`reason`。

### 4. 心跳丢失的失败语义（failure semantics）—— fail-closed 偏 safe-stop

心跳丢失即认为该 `child_run` 当前 coding 结果**不可信** → `safe_stop_run`，不谎称结果。
**不采用 `uncertain`**：长连接失联的 Worker 产出的任何中间状态都不可验证，safe-stop 比
uncertain 更不易掩盖数据损坏。`uncertain` 留给"进程还在但只是慢"的边界——但那属请求级
`worker_timeout`（已有 `begin_recovery` 路径），与 heartbeat 不重叠。

丢失触发链（复用既有机制，不另造）：
1. `record_event(child_run_id, "worker.heartbeat.lost", payload, ..., evidence_source=NATIVE)`；
2. `record_result(child_run_id, "worker.error", {code:"heartbeat_lost", ...}, ..., evidence_source=NATIVE)`
   （沿用现有 `worker.error` 落账路径 `worker_bridge.py:1142/1155`）；
3. `owner.safe_stop_run(child_run_id, "worker:heartbeat_lost")`；
4. 触发进程终止（见决策 5）。
5. `_termination_reason_for_error` 增加分支：`heartbeat_lost -> "heartbeat"`。

与 `1-7-2` 孤儿计账的关系：safe-stop 后若子进程未真正退出，`1-7-2` 的孤儿计账
（zero/nonzero/unknown）在 run 收尾时诚实记录残留——心跳模块只判定 lost + 触发终止，
不做二次孤儿判定，避免职责重叠。

### 5. 与 1-8-4 reaper / killpg 兜底的关系—— 心跳是触发条件，reaper 是执行手段

`1-8-4` 的终止机制已在 Worker 路径实现：`worker_bridge._signal_process`（`worker_bridge.py:774`）
用 `os.killpg(pid, sig)`（进程以 `start_new_session=True` 起，自成 pgid）。这是"进程退出 /
终止"的单一执行手段。

心跳丢失时的终止动作**直接复用** `_signal_process(SIGTERM)`，**不在心跳模块另写 kill 逻辑**：
- 心跳监督 = 触发条件（判定 `heartbeat_lost`）；
- reaper / killpg = 执行手段（SIGTERM → killpg；沿用既有 setsid 逃逸处理 + 超时升级 SIGKILL）。
- 心跳模块只负责"lost 即触发 `_signal_process`"，不重新发明超时升级。
- 单一 killpg 路径，零重复实现。

## Consequences

- 新增模块（建议 `src/zworkbench/worker_heartbeat.py`）：
  - 常量 `WORKER_HEARTBEAT_INTERVAL_SEC` / `WORKER_HEARTBEAT_TIMEOUT_SEC`；
  - 纯函数 `heartbeat_lost(now, last_activity_ts, timeout) -> bool`；
  - `HeartbeatMonitor` 线程类（start/stop、共享 `last_activity_ts`、tick/lost 回调）；
  - `WORKER_EVENT_KINDS` / `WORKER_ERROR_CODES` 词汇集 + 一致性测试。
- `worker_bridge.py` 改动（本 ADR accepted 后执行）：
  1. `_run_process` 生命周期里启动/停止 `HeartbeatMonitor`，在 `on_line` 与每次
     handshake/coding 响应落账处更新共享 `last_activity_ts`；
  2. `_termination_reason_for_error` 增加 `heartbeat_lost -> "heartbeat"`；
  3. 心跳丢失回调接 `safe_stop_run` + `_signal_process(SIGTERM)`；
  4. 收编现有 worker error code 字面量为 `WORKER_ERROR_CODES`。
- 测试：用可注入 clock（fake time）+ 可控子进程 harness。`fake-loopback` fixture 不起真
  子进程，故心跳测试走 `real_worker_mode=True` 的受控 harness——强制"进程 `poll()` 仍 alive
  但 `last_activity` 不前进"→ 断言 tick 记录 + lost 触发 + `safe_stop_run` + SIGTERM 经
  killpg。（参考 `1-7-4` 审计：worker 真实子进程测试在 sandbox 内隔离跑 14/14 通过，说明
  该 harness 在 sandbox 可行。）
- 不回归：现有 `worker_timeout` 语义不动；heartbeat 是新增的并行监督维度。
- roadmap 影响：本 ADR accepted 后，`1-7-5` 由 `pending` 转 `in_progress`；`1-7-4`（等 `1-8`
  的验收闸门）不受影响——心跳复用的是 Worker 路径**已实现**的 killpg，非 `1-8` 阻塞项。

## 未解决（不在本 ADR 范围）

- 双向 ping/pong（Worker 主动心跳）—— 若未来 v1 协议要支持，另立 ADR 改 `worker_contract`。
- 心跳语义与 `1-8` 共享硬前置（host sandbox / 出站脱敏等）无耦合，本 ADR 不触及。
