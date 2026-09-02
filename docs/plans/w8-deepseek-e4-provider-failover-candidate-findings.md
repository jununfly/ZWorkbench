# W8 DeepSeek E4 Provider failover 候选扩展验证

日期：2026-09-02
路线节点：`1-8-3-1-1`，`acceptance/evaluation`
验证器：[run_deepseek_e4_provider_failover_candidates.py](../../evaluation/runner/run_deepseek_e4_provider_failover_candidates.py)
正式证据：[summary.json](../../evaluation/evidence/w8-deepseek-e4-provider-failover-candidates-20260902-rerun4/summary.json)
候选 fixture：[manifest.json](../../evaluation/fixtures/w8-deepseek-e4-provider-failover/v1/manifest.json)

## 结论

E4 的候选能力缺口已被收窄，但没有关闭：两个真实候选源码都在
case-local、loopback-only 的 `RATE_LIMIT` 故障下完成了明确的
`primary → secondary` 模型 Provider 切换；`dsh-model-failover` 在所有
候选路由都冷却时不再选择新的 fallback（回到 primary 让失败暴露），
`dsh-llm-failover` 则仍返回已冷却的最终 fallback。这里的 route-only probe
不把“回到 primary”扩大解释为宿主层 safe-stop。两个候选都没有 candidate-owned durable
failure/reason/degradation ledger，所以 E4 仍为 `unknown/stop`。

这修正了“DeepSeek 插件生态完全没有 Provider failover 供给”的过强说法，
但不改变“当前 DeepSeek plugin-composed bundle 尚未达到 E4”的结论。

## 研究状态和证据边界

- 正式 `zj-research` fresh collection 已恢复：sidecar 为
  `fresh-collection`，认证模式为 `authenticated`，GitHub core quota 为
  `5000`，并产生匹配 brief fingerprint 的 sealed ledger；本轮覆盖 4 个
  repository、18 条 evidence，另有 2 个明确的 unknown criteria。
- 解决方式不是把 token 写进仓库，而是在 Human 本机把已登录 `gh` 的 token
  仅注入当前进程：`export GITHUB_TOKEN="$(gh auth token)"`，然后运行
  `zj-research` collection。运行器现在动态读取最新 sidecar，不再硬编码
  `collection-blocked`。
- GitHub 身份、源码版本和研究标准结论只引用 sealed ledger 的 Evidence ID；
  运行时行为仍来自 case-local probe，不能用 GitHub source evidence 替代运行
  验证。
- 运行器从 pinned Git object 读取源码，复制到新 evidence 目录并记录每个
  文件 SHA-256；没有 registry install、真实 Provider、真实凭据、外网或
  生产项目写入。
- 现有火山方舟 Ark `HTTP 200 / 1 request / 0 retry` 仍是单 Provider staging
  基线，不参与本轮 failover 通过判定。

正式 collection 状态见
[collection-status.json](./research/w8-deepseek-e4-provider-failover.collection-status.json)，
sealed ledger 见
[ledger-response.json](./research/w8-deepseek-e4-provider-failover.ledger-response.json)。

## 候选逐项结果

| 候选 | 固定源码 | 正式 ledger Evidence IDs | Provider 切换 | `RATE_LIMIT` 分类与 identity | 全冷却时不再选新 fallback | 无循环 | 原因可观察 | durable reason ledger | 结论 |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| `dsh-llm-failover` | `HB00/dsh-llm-failover@919272faf9f9eb0d379b70f45c5612c1d5aa47a5`，`0.3.0` | identity `8b1b5b96debf89a88c24d1ea`；contract `357f99ac391b5cc690b1b09d`；failure-ledger `unknown` | pass | pass | **fail** | pass | pass（console log） | **fail** | partial/unknown |
| `dsh-model-failover` | `Letter2025/dsh-model-failover@47588d4692a76d64382865e518d2a927eda4891b`，`0.1.4` | identity `62a5f880e4a0e4c19e4a4b57`；contract `c70c560e1a0b9f7606175e9f`；failure-ledger `ab14a944ca50f5d5fcd6b90b` | pass | pass | pass | pass | pass（events/logger/UI notice） | **fail** | partial/unknown |

逐候选完整 checks、事件、日志、路由序列和 source hash 在：

- [`dsh-llm-failover/candidate-result.json`](../../evaluation/evidence/w8-deepseek-e4-provider-failover-candidates-20260902-rerun4/dsh-llm-failover/candidate-result.json)
- [`dsh-model-failover/candidate-result.json`](../../evaluation/evidence/w8-deepseek-e4-provider-failover-candidates-20260902-rerun4/dsh-model-failover/candidate-result.json)

## 可观察行为

### `dsh-llm-failover`

固定配置为 primary `primary/model-a`、fallback `secondary/model-b`，
`fallbackAfterRetries=1`。注入一次 `RATE_LIMIT` 后，路由序列为：

```text
primary/model-a → secondary/model-b → secondary/model-b → secondary/model-b
```

它确实进行了 Provider 切换，也记录了 `RATE_LIMIT` 和切换日志；但候选
没有输出 durable event/ledger，且当 primary 与 fallback 都在 cooldown 时，
`pickEffective()` 仍返回列表最后一项。这个结果不能被描述为 fail-closed。

### `dsh-model-failover`

固定配置为 primary `primary/model-a`、fallback `secondary/model-b`，
`modelCircuitThreshold=1`、关闭真实 probe。注入两次 `RATE_LIMIT` 后，路由
序列为：

```text
primary/model-a → secondary/model-b → primary/model-a → primary/model-a
```

它发出了 `circuit-opened` 和 `failover` 事件，并在 logger/UI notice 中暴露
了 Provider/model 与 `RATE_LIMIT`；所有路由都打开时回到 primary，让真实失败
继续暴露，没有把已知冷却 fallback 当作健康目标。但 `failover` event payload
没有 failure code/reason/degradation，且 circuit state 明确是 process-local；
case-local candidate-owned durable record 数为 `0`。

## 与 E4 门槛的关系

| E4 要求 | 本轮观察 | 是否足以通过 |
|---|---|---:|
| 至少一个真实模型 Provider transition | 两个候选均通过 loopback transition | 否，单项能力不等于完整 E4 |
| failure classification、Provider/model identity | 两个候选均可从日志/事件/路由观察 | 否，仍缺 durable contract |
| 不循环且全冷却时不再选新的 fallback | `dsh-model-failover` 通过；`dsh-llm-failover` 不通过 | 否，候选集合不一致；宿主 dispatch/safe-stop 未由本 probe 证明 |
| fallback reason 记录率 100% | 两个候选的 candidate-owned durable record 均为 0 | **否，hard block** |
| 同语义结果、真实 Provider、真实远端责任 | 本轮没有真实 Provider/远端副作用 | 未验证 |

因此本轮的准确门禁结论是：

```text
provider selection/fallback: partially observed
candidate-owned durable fallback-reason ledger: not observed
E4: unknown/stop
Codex 主 Harness 决策：不变
```

`dsh-search-failover` 和 `dsh-routing-suite` 仍是负对照：前者是搜索后端
fallback，后者是任务/人格/阶段路由；不能用它们满足模型 Provider failover。

## 下一步边界

正式 collection 的配额阻断已解决；若继续解决 E4，下一步只有两个合法方向：

1. formal collection 恢复后，对上述 pinned candidates 完成新的 sealed
   ledger，并在同一版本约束下复核来源、许可证、依赖、安装和维护成本；或
2. 找到/固定一个同时提供 durable failure reason、degradation state、
   Provider/model identity 和全冷却 fail-closed 语义的候选，再做完整 E4
   repeat matrix。

在此之前，不把 `dsh-model-failover` 或 `dsh-llm-failover` 写入
ZWorkbench 产品依赖，也不允许用 evaluator-owned owner ledger 把候选原生
能力补成“通过”。

本文件不构成第三方项目的安全、合规、许可证或商业保证。
