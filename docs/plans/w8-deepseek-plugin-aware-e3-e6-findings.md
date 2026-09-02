# W8 DeepSeek plugin-aware adapter：E3–E6 独立重开结果

日期：2026-09-02
路线：`1-8-3-1-1`，acceptance/evaluation
最终证据：[rerun3 summary](../../evaluation/evidence/w8-deepseek-plugin-aware-e3-e6-20260902-rerun3/summary.json)
真实 Provider 子证据：[Ark staging summary](../../evaluation/evidence/w8-deepseek-plugin-aware-e4-real-ark-20260902/20260902T025444Z-9108/summary.json)
执行器：[run_deepseek_plugin_aware_e3_e6.py](../../evaluation/runner/run_deepseek_plugin_aware_e3_e6.py)
固定 bundle：[manifest](../../evaluation/fixtures/w8-deepseek-plugin-bundle/v1/manifest.json)

## 结论

本轮完成了独立 E3–E6 执行，但没有形成“通过全部门槛”的 DeepSeek
候选。E3 通过；E4 和 E5 按 fail-closed 规则保持 `unknown/stop`；E6
因此被前置条件阻断。当前不批准 DeepSeek 替换或并列 Codex 主 Harness。

这不是对 DeepSeek 插件生态的全盘否定：它证明了部分可组合能力，但当前
组合尚未证明完整的 Provider 故障切换、真实单人运维成本和远端退出责任。

E4 候选扩展验证已单独完成：两个 pinned 模型 Provider failover 候选均观察到
真实的 loopback `primary → secondary` 切换，但 durable fallback-reason ledger
仍缺失，且其中一个候选在全路由冷却时不 fail-closed；因此本报告原有 E4
`unknown/stop` 结论保持不变。详见
[E4 候选扩展 findings](./w8-deepseek-e4-provider-failover-candidate-findings.md)。

## 独立性与边界

- 使用全新的 `rerun2` evidence 目录；不继承 Codex、前三插件首轮或旧
  owner fixture 的通过结论。
- 组合为固定的 DeepSeek Alpha.4 core，加上 pinned
  `dsh-context`、`dsh-routing-suite`、`dsh-memoir`，以及通过 dynamic-plugin
  adapter 接入的 `dsh-config-migrate`。
- `dsh-config-migrate` 固定 commit：
  `24aa64188386181bdaf21f4b46fea02bddf77e71`；E3 runtime seam 使用其真实
  pinned `host.js`/`client.js`，写入仍由 adapter policy gate 拒绝。
- 运行期间不接触真实 Provider、API key、外网、真实 DSH_HOME、生产项目、
  远端任务、Webhook 或远端备份；所有目标均在 case-local evidence 下。

## Gate 结果

| Gate | 状态 | 证据与解释 |
|---|---|---|
| E3 安全与副作用 | **pass** | runtime seam 的写入、路径逃逸、未知 RPC、未授权 subprocess 和未知 effect 均 fail-closed；dispose 后 `rpc/tools/ui/styles=0/0/0/0`，owner effect 为 0。 |
| E4 幂等、路由、记忆、Provider、回放 | **unknown/stop** | 插件路由 deterministic，阶段序列为 `[1,2,3]`；memoir 选出 2 条、估算 62 tokens、硬上限 120、排除 `note`；owner 幂等为 1 次物理写入，模拟回放 5/5，未批准 live replay effect=0；Ark staging 真实请求 HTTP 200、1 请求/0 重试、合成 fixture 命中。但 Provider failover 合同缺失。 |
| E5 小团队生命周期与退出 | **unknown/stop** | fresh install、upgrade/rollback、backup/restore、fault diagnosis 的机器 fixture 均通过；人工单人计时未提供，真实远端任务/Webhook/备份清理责任未验证。 |
| E6 组合增量收益 | **blocked-by-E3-E5-prerequisites** | E4/E5 未通过，且尚无同任务集、同 Provider 下相对 Codex 的可测量非重复优势。 |

## 真实火山方舟 staging 子门

本轮按 Human 要求复用前次火山方舟 API key，但 key 只在本机隐藏输入中使用；
runner 只读取脱敏 summary，不接收 key 原文。验证结果：

- Provider：`volcengine-ark`；endpoint：
  `https://ark.cn-beijing.volces.com/api/coding/v3/responses`。
- 配置 model：`ark-code-latest`；响应字段 `model=auto`，按已确认的 Ark
  映射记为同一配置路由。
- HTTP `200`；`request_count=1`；`retry_count=0`；`staging-fixture-001`
  命中；未持久化 raw request/response。
- key 只以 SHA-256 fingerprint 关联：
  `9c9020b16cb136d1f0cb71989fe3b81e0fc756742f6b7d2eb335ba2a84683451`。

这证明了“一次真实 Ark 请求可达且语义 fixture 返回正确”，没有证明：第二个
Provider、自动 fallback、降级 reason ledger、真实远端任务/Webhook/备份清单，
或 DeepSeek 插件已经拥有这些能力。真实请求是 E4 的外部 staging 子证据，不是
ZWorkbench 产品运行时请求。

## E3：安全边界已成立的范围

独立 runtime seam 证明了以下行为：

- `dsh-config-migrate` 的注册、调用、结果与 CompositionOwner correlation
  可记录；run 可完成。
- export/import、路径逃逸和 tool write 均被拒绝；插件声明的
  `danger-full-access` 没有扩大 effective adapter policy。
- 未知 effect 使 run 进入 `safe_stopped`；重复请求不会自动执行；物理
  effect 数为 0。
- pinned Node subprocess allow 与非 allowlisted Python/shell deny 均被记录。

这些结果只证明 evaluation-only seam 的行为，不证明宿主 OS sandbox、真实
DSH_HOME 迁移成功或产品集成可发布。

## E4：已验证能力与关键缺口

已验证的候选插件行为：

- `dsh-routing-suite` 的任务/人格/阶段路由在相同输入下 deterministic，
  阶段能够从 1 推进到 3。
- `dsh-memoir` 的本地 store 与 hot-memory selector deterministic；
  估算 token 数不超过 hard max，`note` section 不进入 hot memory。
- 外层 CompositionOwner 对本地 effect 做到重复抑制（1 次物理写入）并
  记录模拟 replay 的 source/environment/provider identity。

不能将上述路由能力称为 Provider failover。固定的
`router-core-v34.mjs` 没有候选拥有的 Provider selection、fallback、
degradation 或 fallback-reason ledger 合同；因此没有用 evaluator 自己写
的 fake router 填补这个缺口，E4 保持 `unknown/stop`。

## E5：机器 fixture 不等于真人运维结论

当前机器 fixture 只证明 case-local 操作逻辑可运行：

- `backup/restore` 的 backup manifest、数据库和 state JSON 存在，完整性
  检查通过，损坏目标被替换，恢复前后 state digest 一致。
- upgrade/rollback 恢复 adapter manifest identity。
- fault diagnosis 能通过 run/request/fault id 关联故障，并给出不自动重试
  的有界动作。
- uninstall 只删除 case-local marker；fixture 中没有远端资源，不能据此
  宣称真实远端清理完成。

E5 仍缺：真实产品安装/升级 runbook 的人工单人计时，以及真实 Provider/远端
 任务/Webhook/备份的退出责任审计。不能把 Codex 的人工耗时移植给 DeepSeek。

## E6 决策边界

E6 当前不比较“谁更好”，只保留三项待证实的候选收益：

1. task/persona routing；
2. bounded local project memory；
3. configuration migration。

它们还不是相对 Codex 的优势，因为尚未在同任务集、同 Provider、同 owner
contract 下完成匹配测量。下一次只有在 E4 的 Provider failover 合同和 E5
的人工作业/真实退出证据补齐后，才允许重开 E6；否则停止这条组合分支，
继续 Codex + 单一 CompositionOwner 主线。

本报告不构成第三方安全、合规、许可证或商业保证。
