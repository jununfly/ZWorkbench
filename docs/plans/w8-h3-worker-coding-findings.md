# W8 H3 Worker coding findings

状态：`product execution / fixture-composed + real-Codex-runtime/loopback-Provider verified`
日期：2026-09-04

本轮完成 `1-9-4` 的最小 owner-backed `read_only_coding` seam。它复用 H2 的
[WorkerBridge](../../src/zworkbench/worker_bridge.py)，在严格的
`handshake.response → result` wire 序列上运行一个只读 coding turn，并把可审查
artifact 的 digest、Provider/Worker/schema identity 和 parent/child correlation
写入 [CompositionOwner](../../src/zworkbench/composition.py)。Worker 不直接写 owner，
也不应用 workspace 修改。

## 实现边界

- `WorkerBridge.read_only_coding()` 要求 parent Run 已是 `running`，创建一个 child
  Run，并只接受一条完整 `handshake.response` 和一条完整 `result`；未知 wire、字段、
  identity、provenance、状态或非零退出均 fail-closed。
- artifact root 必须是 case-local、已存在、独立于 `workspace` 且运行前为空。结果必须
  精确声明 `diff`、`tests`、`semantic`、`runtime_events` 四个 artifact，每个路径、
  byte count 和 SHA-256 都由 bridge 重新读取校验；额外文件也会拒绝。
- Worker 运行前后对 case-local workspace 做 snapshot；workspace 变化、effect 或
  未声明 artifact 会使 parent 和 child `safe_stopped`。成功时 child `completed`、
  parent 保持 `running`，并且 bridge/Worker 进程退出。
- coding prompt 中检测到 credential-like `sk-...` 或 `AKIA...` 值时，在创建 child
  Run 和启动 Worker 前拒绝；这是一条早期边界检查，不是对任意文本的完整 secret-DLP
  证明。

真实 runtime adapter 位于
[`evaluation/fixtures/w8_worker_coding/v1/codex_worker_adapter.py`](../../evaluation/fixtures/w8_worker_coding/v1/codex_worker_adapter.py)。
它只负责 transport 和一个 case-local Codex app-server 生命周期，不写
CompositionOwner。真实路径固定使用 `/opt/homebrew/bin/codex`、case-local `CODEX_HOME`、
app-server stdio、`sandbox=read-only`、`approvalPolicy=never`，禁用 Codex plugins/apps，
并通过显式的 `h3-loopback` Responses provider 配置连接 fake loopback service。

## 回归修复

初次回归曾出现间歇性 `worker_timeout`：Codex 日志已显示
`turn/completed`，但 Worker 未收到结果。根因是 `selectors` 监视操作系统 fd，
而 `TextIOWrapper.readline()` 可能一次预读多条 JSONL；第一条通知消费后，后续
消息留在 Python 缓冲区，fd 不再报告可读，导致 `wait_turn()` 永久错过已完成 turn。

真实 runtime adapter 和产品 `CodexAppServerAdapter` 现在都使用二进制 pipe 与显式
有序 JSONL 缓冲；`wait_turn()` 也会先检查已缓冲通知。新增的确定性回归会让
`turn/completed` 早于 `turn/start` response 到达，验证该事件顺序不会被误判为超时。

## 验证结果

fixture 和 runner 位于
[`evaluation/fixtures/w8_worker_coding/v1`](../../evaluation/fixtures/w8_worker_coding/v1)、
[`evaluation/runner/run_w8_worker_coding.py`](../../evaluation/runner/run_w8_worker_coding.py)，
测试位于 [`tests/test_worker_coding.py`](../../tests/test_worker_coding.py)。

实际命令和结果：

```text
PYTHONPATH=src python -m unittest tests.test_worker_coding tests.test_worker_bridge -v
8/8 pass

PYTHONPATH=src python -m unittest discover -s tests -p 'test*.py'
76/76 pass

PYTHONPATH=src python evaluation/runner/run_w8_worker_coding.py \
  --output /tmp/zworkbench-h3-final-20260904 \
  --codex /opt/homebrew/bin/codex
status=pass; cases_passed=2; cases_total=2
```

修复后的稳定性回归：同一 runner 连续 5 次执行，5/5 pass；每次
`real-codex-loopback` 都观察到 4 条 Provider 日志记录、semantic text
`fixture-ok`、workspace unchanged、effect=0 和 Worker 退出。全量产品/评测测试为
`85/85 pass`。

| 场景 | 证据等级 | 观察 | 结果 |
|---|---|---|---|
| `fixture` | `fixture-composed` | child completed、parent running、semantic text `fixture-ok`、四类 artifact digest 校验通过、Provider 请求 0、effect 0 | pass |
| `real-codex-loopback` | `real-Codex-runtime + loopback-Provider` | 实际 Codex `0.139.0` app-server 完成 thread/turn；fake loopback Provider 收到 4 次请求；semantic text `fixture-ok`；workspace 未变化；effect 0；Worker 退出 | pass |

两条路径都验证了：

- parent/child/attempt/DSH/Codex identity 能进入 owner-backed result；
- workspace 前后 snapshot 一致，未执行 apply 或其他 effect；
- `diff.patch`、`tests.txt`、`semantic-result.json` 和 `runtime-events.jsonl` 均由 bridge
  重新计算 digest；
- child result kinds 包含 request、handshake、semantic、coding 和 exit；
- `bridge.process is None`，没有遗留 bridge Worker。

验证输出只写入新的 `/tmp` case-local 目录，没有将运行现场、Provider 原始响应或凭证加入仓库。
`git diff --check` 通过。

## Evidence boundary and non-claims

本轮的 real-runtime 证据证明的是：在固定的本机 Codex CLI `0.139.0`、case-local
app-server 配置和 fake loopback Provider 组合下，H3 Worker wire、owner correlation、
只读 workspace 和 artifact receipt 可以完成一个 turn。它不是 DSH 原生能力通过，也不是
生产部署安全证明。

以下事项仍保持 `HOLD` / `unknown`，没有因本轮通过而升级：

- 没有执行真实远程 Provider、真实 API key 或生产数据，因此不声称真实 Provider 兼容性；
- 没有证明 H4 的 cancel、timeout、crash、parent stop、restart、恢复和完整进程树矩阵；
- 没有证明 H5 的 owner evidence 完整回放、`recorded_view`、cassette-only
  `simulated_replay` 或默认拒绝 `live_replay`；
- 没有证明 OS/host sandbox、Codex native approval、主工作区写入、apply、Git push 或
  任何不可逆 effect。

下一验证节点分别是 `1-9-5` H4 生命周期/恢复和 `1-9-6` H5 evidence/replay；真实
Provider staging 仍需账户 owner 单独授权，并遵守
[`optional-real-provider-staging.md`](../references/optional-real-provider-staging.md) 的
凭证、远端资源和退出责任边界。
