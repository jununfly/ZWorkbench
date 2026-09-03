# W8 E4：durable fallback/reason/degradation ledger 与全冷却 fail-closed

日期：2026-09-02<br>
路线节点：`1-8-3-1-1`，`acceptance/evaluation`<br>
collection metadata：[`w8-deepseek-e4-provider-failover.v2.collection-status.json`](./research/w8-deepseek-e4-provider-failover.v2.collection-status.json)<br>
collection：17 个固定 commit、128 条 canonical evidence、8 个 unknown criteria。

原始 brief 和 sealed ledger 是研究编译器生成的本地证据，按仓库规则不作为默认提交
物；本轮 ledger 的 SHA-256 为
`d8aa9f4d8d5e035e67da6445e76e85c847c45885ac628c22934c141641a370ed`，321,735 bytes
（brief 与 ledger 合计）。需要复核时使用同一 collection metadata、brief fingerprint
和固定 GitHub commit 重新生成；本文件保存可提交的结论摘要，不把本地生成物伪装成
版本库中的完整 ledger。

## 结论

1. **Codex 原生没有被证明拥有这套 Provider failover ledger。** 当前通过的是
   `Codex + ZWorkbench CompositionOwner + C5 adapter/router`。CompositionOwner
   负责通用 run/effect/attempt/result/replay、幂等、未知副作用安全停止和 SQLite
   backup/restore；Provider 的 route、cooldown、fallback reason、degradation
   目前由外层 adapter/fixture 负责，不是 Codex 原生 schema。
2. **GitHub 上确实有多个适配 DSH 的开源 Provider/fallback 插件。** 因此不能再说
   “DeepSeek 生态没有供给”；但本轮没有找到一个已经证明同时满足以下完整合同的插件：
   Provider/model 切换、失败分类、durable decision/reason/degradation ledger、
   跨进程恢复，以及所有 route 冷却时拒绝 dispatch 的 fail-closed。
3. **DSH 生态能降低自研成本，但不能消除 ZWorkbench 的 owner 责任。** 插件的
   route state、session event、quota snapshot 不能自动成为 ZWorkbench 的 canonical
   run/effect/replay truth；否则会产生两个恢复和回放事实源。

## 目标合同

完整 E4 至少要求候选自己持久记录：

```text
decision_id, run/thread/turn, request/attempt,
provider/model 与非敏感 endpoint identity,
failure class + HTTP status/retry-after,
primary/fallback + fallback reason,
degradation state,
cooldown before/after,
action=fallback|degraded|safe-stop,
sequence, candidate commit, ledger schema/version
```

安全顺序是：记录失败 → 更新 cooldown → 持久化 decision → 再 dispatch fallback。
持久化失败、状态不确定或所有 route 冷却时，必须不再 dispatch 已知不可用 route，
而是返回明确的 unavailable/safe-stop。评估器事后生成的 `fallback-ledger.jsonl`
或 ZWorkbench owner ledger 只能证明 composition adapter，不能补成候选原生能力。

## Codex 当前实现边界

| 层 | 已有能力 | 对 E4 的含义 |
|---|---|---|
| `src/zworkbench/composition.py` | SQLite `runs/effects/effect_attempts/results/replays/events`；幂等、bounded retry、uncertain/reconcile、safe-stop、backup/restore | 是通用 durable owner；没有 Provider route/cooldown/fallback decision 字段 |
| `evaluation/fixtures/w7-codex-c5-c6/provider-router.py` | primary→fallback、timeout/stream failure、Provider identity、`attempt-history.jsonl`、fallback/degradation ledger、无同 Provider retry | 是验收 adapter/fixture；不是 Codex native Provider failover |
| C5 判定 | `pass-with-composition` | Codex 主线可用，但不能声称 Codex 原生完成 E4 Provider ledger |

## DSH 候选核查

状态词含义：`部分` 代表源码/文档或局部运行语义存在，但至少一个 E4 hard gate
仍未证明；`unknown/stop` 不是说源码一定没有，而是当前证据不足以放行。

| 候选（固定 commit） | 已观察到的增量 | 关键缺口/风险 | 当前判断 |
|---|---|---|---|
| [`Liyuk/dsh-quota-router`](https://github.com/Liyuk/dsh-quota-router/tree/683dc8755b309bdbfbeb807ad79db882e8e44d7f) | Provider/model 候选链、失败分类、cooldown、route receipt 与 bounded ledger；集成测试中有 forward-only 和候选耗尽语义。Evidence `2bb74f2bbf84c5bfdfedd6df`、`28a40353ba0bc1cb3c5828ca` | `Ledger` 是进程内数组/Map；UI 明确说明不是永久账单，不能证明跨进程恢复。其 npm 安装还出现 Cordis peer 冲突；67 个非 DSH 集成测试通过，2 个 DSH 集成套件因缺少 `@deepseek-ai/dsh-scope` 未能运行 | **路由语义较完整，durable E4 不通过** |
| [`baochaofan0404/dsh-provider-fallback`](https://github.com/baochaofan0404/dsh-provider-fallback/tree/e19fe0267932d6db395062c7c801fbbf4af3fc7e) | Provider-level failover；`ProviderRuntimeState` 保存 cooldown、quota、failure kind；JSON snapshot atomic write/read，并有 restart round-trip 测试。Evidence `457b7d86a414b0e45470c485` | snapshot 是 Provider 健康状态，不是 fallback decision/reason/degradation ledger；全冷却时 selector 返回原请求 route 并让错误暴露，属于 route-level no-new-fallback，尚未证明 host dispatch safe-stop。包标为 `private`，构建要求 DSH checkout | **最接近持久 cooldown；仍需 adapter 和 E4 重验** |
| [`force-push/dsh-llm-fallback`](https://github.com/force-push/dsh-llm-fallback/tree/69762df64784adbfc85671cc783b088564537bb2) | 跨 Provider/model fallback；失败后写入 durable `llm/fallback` session event，事件含 from/to/failure/attempt。Evidence `e45f7a2aa94c8a7c5be58bff` | 没有 candidate-owned cooldown/health/degradation 状态；chain exhausted 只是交给下游 terminal policy；session event 不是完整可查询的 decision ledger | **最接近 reason event；仍不完整** |
| [`lokic7123-star/dsh-route-resilience`](https://github.com/lokic7123-star/dsh-route-resilience/tree/738d6c23c442eda2c574612642567b8b7c6ffd9a) | 多 route、故障分类、quarantine、指数退避、durable session events 和状态 API | 所有 route down 时会 force-revive 最早到期的 quarantine；这让已知不健康 route 重新进入候选，不满足严格全冷却 fail-closed | **可观测/路由部分通过，安全门禁不通过** |
| [`HB00/dsh-llm-failover`](https://github.com/HB00/dsh-llm-failover/tree/919272faf9f9eb0d379b70f45c5612c1d5aa47a5) | RATE_LIMIT/QUOTA 切 Provider、per-provider model、cooldown、最终兜底 | 没有 durable decision/reason/degradation ledger；本轮 loopback probe 观察到全冷却时仍可能选择最终已冷却 fallback | **部分** |
| [`YFY-AI/dsh-llm-fallback`](https://github.com/YFY-AI/dsh-llm-fallback/tree/c765e1d8397e892dde92718b4b1c94e790880b89) | 多渠道 fallback、分级 cooldown、usage/status API、配置/chain 持久化 | 持久化主要是 chain/usage/config projection；未证明 durable fallback decision ledger、全冷却拒绝 dispatch 和单一 owner | **部分，外部数据/配置面较大** |
| [`HeWhenJay/dsh-provider-hub`](https://github.com/HeWhenJay/dsh-provider-hub/tree/94a45b8ebd3b9efdaca60d3b2517d351f6f758fa) | Provider hub、API key/OAuth channel、model allowlist、failover、redacted logs、loopback sidecar | 引入 sidecar、账户、凭证、下载和远端/进程生命周期；许可证为 CC-BY-NC-SA-4.0；当前证据未证明 durable E4 ledger 或全冷却 safe-stop | **能力广但责任面超出首个个人切片** |
| [`guangxiangwu6-cmd/dsh-llm-failover`](https://github.com/guangxiangwu6-cmd/dsh-llm-failover/tree/e9d9b0f3ee2986b57916d4005476c0769931142e) | 模型 failover、cooldown、session event 方向 | 其文档本身记录自定义 session event 会触发 DSH persistence compatibility 问题；不能直接视为稳定 durable owner | **暂缓** |

其余本轮候选（`omdsh-dev`、`Visol-456`、`eye33`、`KongFUN2018`、`morphlinglan`、
`qfzlm`、`young-tim`、`green-dalii`）有不同程度的 fallback/route/approval 代码或
文档，但没有在 sealed evidence 中同时建立完整 durable ledger + all-cooldown
fail-closed 合同；其中部分项目的 security/maintenance criteria 仍是 unknown。

## 是否可以靠插件组合解决

可以形成一条“可实现”的组合路线，但它不是现成 bundle 直接通过：

```text
DSH plugin（Provider route / cooldown / fallback event）
        ↓ adapter translation
ZWorkbench CompositionOwner（唯一 run/effect/replay/policy owner）
        ↓ host dispatch gate
all-cooldown / uncertain / persistence failure → safe-stop
```

可行的最小组合是从一个 Provider-level 候选开始，补一个薄 adapter；不要直接把
多个同时监听 `agent/request` 与 `agent/request-error` 的 fallback 插件叠加，否则
会出现重复 retry、不同 cooldown、不同 fallback index 和两个 reason source。

必须新增的 adapter 责任：

- 将候选的 route/failure/cooldown 状态投影为统一 decision ledger；
- 以 `run_id/thread_id/turn_id/request_id` 关联 DSH session event 与 owner state；
- 在候选选择之前检查持久化成功和 all-cool 状态；
- 把候选“不知道”转换为 `safe-stop`，而不是猜测可用；
- 对 streaming、reasoning effort、tool call、settings reload、进程重启做重复语义测试；
- 提供 pinned source/package、升级/回滚、backup/restore、卸载和 provenance 证据。

## 自研成本区间

这是工程估算，不是已发生工时；区间按单人、已有 ZWorkbench CompositionOwner、
只支持两个 Provider 起步计算。

| 范围 | 估算 | 交付边界 |
|---|---:|---|
| 仅候选/适配 POC | **20–40 小时（3–5 个工作日）** | 固定 DSH commit；两个 loopback Provider；失败分类；SQLite/append-only decision ledger；all-cool safe-stop；fake Provider 测试。不能称生产可用 |
| 受控个人试点 | **80–160 小时（2–4 周）** | Provider/model identity、streaming/tool-call/reasoning 兼容；并发与 cooldown 恢复；owner correlation；脱敏；DSH ABI/version skew；E3/E4/E5/C7 回归；真实 Ark staging；安装/退出 runbook |
| 较完整长期维护 | **160–320 小时（4–8 周）** | 多 Provider/模型、升级回滚、迁移、备份恢复、供应链/许可证、故障诊断、跨版本兼容、完整 C1–C7 和退出责任 |

可拆开的主要工作包（受控试点）大致为：Provider seam 8–16h、失败分类与
cooldown 8–16h、durable ledger/atomic recovery 12–24h、DSH ABI/stream/tool
兼容 16–32h、E4/E5/C7 验收 12–24h、安装/回滚/许可证/排障 12–24h。组合两个
互相重叠的 fallback 插件时，还要增加 pairwise 语义冲突和升级矩阵时间。

持续维护另计：通常每周 2–5 小时；DSH alpha、Provider API 或插件发布变化时，
可能集中消耗数天。引入第二 Harness 或独立 sidecar 后，安装、凭证、升级、备份、
排障和退出面会乘法增加，而不是只增加一个功能开关。

## 对个人/小团队的判断边界

- **≤40h**：可以接受，适合做一次可丢弃 POC，判断是否有 DSH 特有收益。
- **40–120h**：只有在 Provider quota/cooldown、DSH plugin ABI 或跨 Harness 互操作
  带来 Codex 当前路线没有的可重复价值时才值得继续。
- **>120h**：默认暂缓；除非该能力是产品核心差异化并且有人承担长期升级/退出责任。
- 以当前证据，若目标只是获得 durable ledger 和全冷却安全停止，沿用 Codex
  + 一个 ZWorkbench owner 的成本更可预测；引入 DSH 的合理理由应是它的插件生态
  能提供额外的 Provider/quota/互操作价值，而不是重复实现同一安全合同。

## 当前决策状态

```text
DSH plugin ecosystem: 有真实供给
完整 E4 plugin-native contract: 未证明
最接近候选: dsh-provider-fallback（持久 Provider state）+
             force-push/dsh-llm-fallback（durable fallback event）
Codex native Provider ledger: 未证明
Codex + ZWorkbench composition: 当前主线可用，但 C5 是 pass-with-composition
E4: unknown/stop
```

本轮没有修改 ZWorkbench 产品运行时，也没有接入真实 Provider、真实凭据或生产数据。
本文件不构成第三方项目的安全、许可证或商业保证。
