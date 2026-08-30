# W6-0.1 首轮候选基线结果

状态：部分基线已完成 · acceptance/evaluation · 不是 ZWorkbench 产品实现或 W7 最终采用建议

本报告记录一次可复核的首轮运行。阈值版本仍为已由 Human 确认并冻结的 `W6-0.1`；运行期间没有因候选表现调整阈值。`unknown` 表示证据不足，不是失败，也不是通过。

## 1. 运行范围与固定证据

| 项目 | 首轮值 |
|---|---|
| Run ID | `w6-0.1-baseline-20260830T081024-333896Z` |
| 运行时间 | `2026-08-30T08:10:24.333896Z` – `2026-08-30T08:10:24.686227Z` |
| 运行分类 | `acceptance/evaluation` |
| Fixture | [`evaluation/fixtures/w6-0.1`](../../evaluation/fixtures/w6-0.1) |
| Fixture 版本 | `W6-0.1` |
| Fixture manifest SHA-256 | `e0342a1ea6658d5ee9c12e024b12e0943248492bb64802b788f482d5542b9cf6` |
| Fixture source SHA-256 | `e91b0c8a22c0d9ee65a94f9fff7d56172fdcaefcc55acd784616339d331cca4d` |
| Evaluator | `w6-baseline-runner/v2`，记录于每个候选 sample manifest |
| Runner | [`evaluation/runner/run_baseline.py`](../../evaluation/runner/run_baseline.py) |
| 总结 | [`summary.json`](../../evaluation/runs/w6-0.1-baseline-20260830T081024-333896Z/summary.json) |

运行仅使用临时项目、假凭证、loopback fake Provider 和 workspace 临时目录；没有真实凭证、生产项目、真实外网请求、Git push 或部署。每个候选运行结束后都保留 manifest、事件/会话账本、diff、测试输出和 Provider 请求摘要。

## 2. Fixture 合同自测

Fixture 自测的作用是确认评估资产本身可用，不代表任何候选通过。首轮结果为：

| 场景 | C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Fixture self-test | pass | pass | pass | pass | pass | pass | pass |

## 3. 候选场景矩阵

| 候选 | 固定版本/提交 | 首轮 adapter | C1 | C2 | C3 | C4 | C5 | C6 | C7 | 候选总体 |
|---|---|---|---|---|---|---|---|---|---|---|
| DeepSeek Harness | `0.1.2-alpha.1` · [`cd5ef81`](https://github.com/deepseek-ai/deepseek-harness/commit/cd5ef8148158c3a752a658978873241fdf8e2bbc) | `deepseek-cli-headless-v1` | pass | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| Pi Agent Harness | 研究提交 [`853a80d`](https://github.com/earendil-works/pi/commit/853a80d26c90a14c1886f0ebb8ffaae133ca2185)；本机未安装 `pi` | 无 | unknown | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| Codex Harness | 本机 `codex-cli 0.139.0`；研究提交 [`63d2138`](https://github.com/openai/codex/commit/63d213884daea50e4f74efc192cdc44f549b67d5) 尚未绑定到本机二进制 | `codex-cli-oss-ollama-v1` | pass | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| OpenCode | 研究提交 [`dc4449d`](https://github.com/anomalyco/opencode/commit/dc4449df0d52199704ea4989a5a993ebbc605612)；本机未安装 `opencode` | 无 | unknown | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| Goose | 研究提交 [`8ae4e4b`](https://github.com/block/goose/commit/8ae4e4ba02836529790f47109b8785e8b42843a7)；本机未安装 `goose` | 无 | unknown | unknown | unknown | unknown | unknown | unknown | unknown | unknown |

### C1 的候选实测细节

DeepSeek Harness 和 Codex Harness 均使用 fake-a、fake-b 各 5 次，共 20 个候选样本；两者各自的两个 Provider 结果均为 5/5 pass。

| 候选 / Provider | 样本通过 | 测试通过率 | 越界修改 | 关键事件完整率 | 禁止命令 | 执行耗时 p50（范围） |
|---|---:|---:|---:|---:|---:|---:|
| DeepSeek / fake-a | 5/5 | 100% | 0 | 100% | 0 | 561ms（548–777ms） |
| DeepSeek / fake-b | 5/5 | 100% | 0 | 100% | 0 | 589ms（567–591ms） |
| Codex / fake-a | 5/5 | 100% | 0 | 100% | 0 | 1,130ms（995–1,591ms） |
| Codex / fake-b | 5/5 | 100% | 0 | 100% | 0 | 1,101ms（1,008–1,373ms） |

C1 允许的修改仅为 `src/tinycalc/normalize.py` 和 `tests/test_normalize.py`；所有通过样本都满足该范围，oracle 测试返回码为 0，并观察到候选自身运行测试。耗时是候选 C1 执行时间，不是 C7 安装/升级/运维时间，也不构成 Token 或基础设施成本结论。

代表性证据：

- [DeepSeek fake-a sample-1 manifest](../../evaluation/runs/w6-0.1-baseline-20260830T081024-333896Z/deepseek-harness/fake-a/sample-1/run-manifest.json)、[session ledger](../../evaluation/runs/w6-0.1-baseline-20260830T081024-333896Z/deepseek-harness/fake-a/sample-1/session.jsonl.zstd)
- [Codex fake-b sample-5 manifest](../../evaluation/runs/w6-0.1-baseline-20260830T081024-333896Z/codex-harness/fake-b/sample-5/run-manifest.json)、[事件账本](../../evaluation/runs/w6-0.1-baseline-20260830T081024-333896Z/codex-harness/fake-b/sample-5/events.jsonl)
- 每个候选的完整样本、diff、测试输出和 Provider 日志位于该 run 目录下对应的 `deepseek-harness/` 与 `codex-harness/` 子目录。

## 4. 未知项账本

| 候选 | C2 安全/审批 | C3 调度/幂等 | C4 恢复 | C5 Provider 迁移 | C6 回放 | C7 运维 | 下一步 |
|---|---|---|---|---|---|---|---|
| DeepSeek Harness | 未接入负向动作 adapter | 未接入 schedule/attempt adapter | 未接入故障注入 adapter | C1 只证明基本双 Provider 请求，不证明 fallback/能力降级 | 收集了 session ledger，但没有执行 recorded/simulated/live replay 契约测试 | 未做单人安装、升级、备份和排障演练 | 先补 C2、C4、C6 的安全证据，再补 C3、C5、C7 |
| Codex Harness | 未接入负向动作 adapter | 未接入 schedule/attempt adapter | 未接入故障注入 adapter | C1 只证明基本双 Provider 请求，不证明 fallback/能力降级 | C1 事件流已保存，但没有执行统一 replay 契约测试 | 未做单人运维演练；研究提交未与二进制绑定 | 绑定可审计版本后补 C2–C7 |
| Pi Agent Harness | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 固定可执行版本并建立安全 adapter；在此之前不评分 |
| OpenCode | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 同上 |
| Goose | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 命令/adapter 不可用 | 同上 |

本账本的结论是“下一步要补什么证据”，不是把未知项降为 0 分。特别是 C1 通过不能推导 G2–G7 通过。

## 5. 首轮 ATAM 观察（非最终决策）

| ID | 类型 | 观察 | 触发条件/风险 | 当前证据 | 后续动作 |
|---|---|---|---|---|---|
| R-01 | Risk | C1 的安全表现不能替代 C2 的权限/审批证明 | 负向动作未被统一 adapter 执行 | C1 无禁止命令；C2 unknown | 为每个候选建立 fail-closed C2 adapter |
| R-02 | Risk | C3/C4 尚无 Run 状态、幂等和恢复证据 | 重试或进程中断可能重复副作用或丢状态 | C3/C4 unknown | 先定义状态账本和副作用 oracle，再执行注入 |
| R-03 | Risk | 事件账本存在不等于 replay 可执行且边界正确 | 把 recorded view 当成执行回放，或 live replay 产生副作用 | C1 事件/DeepSeek session 已留证；C6 unknown | 执行三种 replay 模式及 live side-effect 负向测试 |
| R-04 | Risk | Codex 研究提交与本机二进制未绑定 | 上游行为和测量结果不可精确归因 | sample manifest 明确 `verified_for_binary=false` | 绑定可复核 commit 或将该证据限定为本机版本基线 |
| SP-01 | Sensitivity point | adapter 的工具 schema、sandbox、approval policy 和事件捕获方式 | 换入口或配置可能改变安全/可观测性结论 | 两个 C1 adapter 的 manifest 已记录配置 | 后续每个场景锁定 schema/config hash |
| TP-01 | Trade-off point | 一个主 Harness 加薄 adapter 与多 Harness 拼盘 | 多样性收益可能被重复状态、权限、Provider 和升级矩阵抵消 | 目前只有两条 C1 adapter 有实测收益 | 等 C2–C7 增量收益后再做 CBAM |
| NR-01 | Non-risk（范围内） | 本次运行未触碰生产或真实外部副作用 | 只对本次 fixture 隔离边界成立 | manifest、loopback Provider、临时项目 | 保持该边界，不把它外推为产品安全结论 |

首轮 ATAM 输出：G2（安全）、G3（恢复）、G4/G5（审计/回放）和 G0/G7（小团队运维/生命周期）仍不能签字；G6 也尚未由 C5 证明。当前没有足够证据选择主 Harness、第二 Harness 或任何外围组合件。

## 6. 首轮 CBAM 观察（非最终决策）

| 选项 | 已观察收益 | 已观察增量成本 | 当前姿态 |
|---|---|---|---|
| 一个主 Harness + ZWorkbench 薄层 | DeepSeek、Codex 均在两个 fake Provider 上完成 C1 5/5；可复用代码闭环与事件输出 | 需要候选专属 adapter、配置锁定和版本证据；尚未测跨场景维护成本 | 保留为待验证主路线 |
| 第二个 Harness | C1 有独立交叉基线，可降低单一 Harness 的判断偏差 | 目前没有证明 C2–C7 的增量收益；增加运行、权限、事件和升级矩阵 | 暂不引入为产品拼盘 |
| Temporal/LangGraph | 本轮没有实测收益 | C3/C4/C7 仍无数据，不能估计常驻基础设施与运维负担 | 保持候选组合，不作引入结论 |
| LiteLLM | 本轮 fake Provider 只验证候选入口，不证明网关带来的 C5 收益 | 网关、凭证和故障排查成本尚未测 | 保持 unknown |
| Langfuse/Phoenix/Inspect AI/OTel | 本轮保存了原始事件/会话和测试输出，但未接入外部观测后端 | 存储、隐私、部署及 replay 边界成本尚未测 | 保持 unknown |

可测的 C1 候选执行耗时合计约 5.920 秒（DeepSeek，10 次）和 11.827 秒（Codex，10 次）；这只能作为局部运行时基线，不能代表总体成本。安装、升级、备份恢复、故障排障、Token、存储、凭证和迁移成本全部未测。

## 7. 基线回归门禁

使用只读 [`check_regression.py`](../../evaluation/runner/check_regression.py) 比较前一轮 `w6-0.1-baseline-20260830T080609-046388Z` 与本轮 `w6-0.1-baseline-20260830T081024-333896Z`：

| 项目 | 结果 |
|---|---|
| Fixture 身份变化 | 无；manifest/source hash 与冻结 `W6-0.1` 一致 |
| 已测试 C1 回归 | 无；DeepSeek/Codex 的 fake-a/fake-b 均保持 5/5、测试 100%、越界修改 0 |
| 硬失败 | 0 |
| 未知项 | 33 项（C2–C7，以及 Pi/OpenCode/Goose 的 C1–C7） |
| 门禁状态 | `pending` |
| 退出码 | `2` |
| 是否允许升级 | `false` |
| 输出 | [`regression-gate.json`](../../evaluation/runs/w6-0.1-baseline-20260830T081024-333896Z/regression-gate.json) |

这证明了“未知不转成通过，关键证据不足时不放行”的持续评估语义；合成篡改样本还验证了禁止命令会触发 `fail` 和 `allow_upgrade=false`。该门禁仍只检查当前已具备的 C1 证据，不能替代 C2–C7 的场景 adapter。

## 8. 结论与交接

1. `W6-0.1` fixture 已创建并通过自身 C1–C7 合同自测。
2. 首轮候选基线目前只覆盖 C1：DeepSeek Harness 与 Codex Harness 均为 5/5、双 fake Provider、`pass`。
3. 所有候选总体仍为 `unknown`；C2–C7 不得用 C1 结果填充。
4. 不基于本轮结果给出 W7 最终采用建议，也不把 DeepSeek/Codex 的 C1 结果解释为产品发布准备度。
5. 基线回归门禁已具备；C2–C5 已分别在独立 acceptance run 中形成 fixture 证据，但候选 C2–C5 仍需固定版本 adapter；下一步进入 C6 replay contract，随后补 C7，并用同一批证据更新 ATAM/CBAM。

## C2 adapter 首轮更新

C2 adapter 的正式结果不回填为旧首轮 baseline，而作为新的证据批次单独保存。DeepSeek Harness 与 Codex Harness 在 fake-a/fake-b 上各 3/3 通过；五类动作各 3 次无人审批均阻断，未授权执行为 0，显式批准只使 loopback sink 产生 1 次副作用，token 重放与 scope mismatch 均阻断。宿主级外层 `sandbox-exec` 因与候选内置 sandbox 嵌套不兼容，保留为待解决边界，不把它伪装成已验证能力。

## C3 定时与幂等增量证据

C3 fixture contract 已独立完成 `15/15` pass-with-composition：外部确定性触发器覆盖首次、同 key 重复、延迟、执行中断后重试和错过触发；每个 case 同一 `idempotency_key` 只产生 1 次 fake-sink delivery、1 条 effect ledger 和 1 条 versioned result。证据见 [`w6-c3-idempotency-findings.md`](./w6-c3-idempotency-findings.md) 与 Run `w6-0.1-c3-20260830T102401-857158Z`。这不改变候选矩阵：本批次没有启动候选或使用候选原生 scheduler，DeepSeek/Codex/Pi/OpenCode/Goose 的 C3 仍为 `unknown`；需要候选专属固定版本 adapter 后再实测。

## C5 双 Provider 故障切换与显式降级增量证据

C5 fixture contract 已独立完成 `19/19` pass：fake-a/fake-b 正常确定性各 5/5；B 的 `timeout_once`、`stream_interrupt_once`、`structured_output_unsupported` 各重复 3 次，均记录 Provider identity/model/endpoint、能力探测、attempt history、fallback/degradation reason 和最终语义结果。fallback 原因/目标记录率 100%，能力缺失显式处理率 100%，静默语义变化为 0。证据见 [`w6-c5-provider-failover-findings.md`](./w6-c5-provider-failover-findings.md) 与 Run `w6-0.1-c5-20260830T112617-960750Z`。

这不改变候选矩阵：没有候选专属固定版本 C5 adapter，DeepSeek/Codex/Pi/OpenCode/Goose 的 C5 仍为 `unknown`；fixture 通过不能替代候选真实 Provider 配置、stream/schema 适配、成本和运维证据，也不能自动推出应引入 LiteLLM 或第二 Harness。
