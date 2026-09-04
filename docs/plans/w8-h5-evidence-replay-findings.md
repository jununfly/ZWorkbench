# W8 H5 Evidence/replay findings

状态：`product execution / owner-backed + fixture-composed verified`
日期：2026-09-04

本轮完成路线图 `1-9-6` 的最小 Evidence/Replay seam。新增的
[OwnerBackedReplayService](../../src/zworkbench/replay.py) 不执行模型、Provider、工具或
进程；它把三种模式拆成三个显式入口，并将可解释的 provenance、执行计数和安全结论返回给
Control Plane。CompositionOwner 仍是唯一 durable owner，service 只读取 owner canonical
state；已有 owner evidence writer 也会拒绝明显的原始 credential 字段。

## 实现边界

| 模式 | 产品入口 | 允许读取 | 结论 |
|---|---|---|---|
| `recorded_view` | `recorded_view()` | CompositionOwner 已保存的 run、result、event | 只读 projection，不改变 owner state |
| `simulated_replay` | `simulated_replay()` | 本地、sealed、digest 匹配的 JSON cassette 和 owner 源事件 | 返回 cassette 的 expected result；不访问 Provider/tool/network |
| `live_replay` | `live_replay()` | 同一 provenance/cassette 校验 | 默认 `deny`，`safe_denial=true`，不启动任何外部执行 |

Replay identity 固定绑定以下字段：Harness、plugin set、Worker、非敏感 Provider identity、
tool schema、policy、workspace、environment、owner schema、源事件 digest，以及模拟/ live
模式所需的 cassette identity。字段为 `unknown`、缺失或 digest 不匹配时，结果是
`unknown` + `safe_stop=true`，不会用最终文本补齐身份。

## 验证结果

测试与 runner：

- [`tests/test_replay.py`](../../tests/test_replay.py)：7/7 pass
- [`tests/test_w8_evidence_replay.py`](../../tests/test_w8_evidence_replay.py)：1/1 pass
- [`evaluation/runner/run_w8_evidence_replay.py`](../../evaluation/runner/run_w8_evidence_replay.py)：7/7 case pass
- fixture：[`evaluation/fixtures/w8_evidence_replay/v1`](../../evaluation/fixtures/w8_evidence_replay/v1)

实际 runner 汇总：

```text
status=pass
passed_cases=7/7
recorded_view_read_only=true
simulated_replay_cassette_only=true
live_replay_default_deny=true
unknown_inputs_safe_stop=true
external_execution_zero=true
```

场景覆盖：

- `recorded-view`：读取 owner facts，state digest 前后一致，未执行外部动作；
- `simulated-replay`：sealed cassette、cassette digest、源事件 digest、environment 和
  Provider identity 全部匹配，返回预期语义结果；
- `live-replay`：显式策略结论为 deny，未获得 approval，不执行任何动作；
- `missing-identity`、`missing-cassette`、`tampered-cassette`、`source-digest-mismatch`：
  全部保持 unknown/safe-stop；
- 所有场景的 network、Provider、tool 和 external effect 计数均为 0。

## Evidence level 与 non-claims

本轮等级是 `owner-backed + fixture-composed`：产品 service 真实读取本地
CompositionOwner，cassette 是固定的 case-local fixture。它不升级为：

- DSH 原生 Evidence/Replay 能力通过；
- 真实 Codex runtime replay 通过；
- 真实远程 Provider compatibility、自然故障 failover 或 Provider-side exit 通过；
- OS/host sandbox、真实主工作区写入、Git push、部署或任何不可逆 effect 通过。

本轮没有读取、打印、生成或重新配置任何 API key，也没有保存真实 Provider 响应或生产数据。
实际运行产物使用临时目录，未批量加入 `evaluation/runs` 或 `evaluation/evidence`。
