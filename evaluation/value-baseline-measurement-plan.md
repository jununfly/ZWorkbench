# 价值基线测量设计（Value-Baseline Measurement Plan）

> 路线节点：roadmap 1-10-6（solo 真实可用 · 价值基线实证）
> 归属：R3「真实可用路线图」三层 AND 门的**第三道（价值判据）**
> 性质：**Acceptance/evaluation 文档**（非 Product execution）。本文件只定义"测什么、怎么算、证据怎么标"，不动产品代码 `src/`。
> 来源权威：`docs/prds/r3-real-usability-roadmap.md` §价值判据 / §价值基线实证；`docs/designs/ps-solo-real-provider.md` §Scope（三层 AND 门）。

## 1. 目的与定位

「产品可用 = 工程判据 ∧ 用户信任判据 ∧ **价值判据**」。任一不达标 → R3 维持 `target`；「可用」宣告不因工程闭环（S0–S4）完成而提前，**须等价值基线出数**。

价值判据的硬指标（见 R3 §价值判据）：

> 价值基线测量给出量化结果（**比裸 Codex 省 X% 时间 / 少 Y 次人工复查**），作为继续投安全外壳的前置论证。

本文件固化该测量的**指标定义、计算口径、证据双标签纪律、与 S3 N=10 合并测方案**，并明确哪些证据算"产品路径"、哪些只是"脚手架"。

## 2. 三指标定义（取自 C1-6 seam 基线，2026-10-01）

对照实验固定变量：**同任务 / 同模型（ark-code-latest）/ 同 custom provider**，只改"执行外壳"：

| 指标 | 裸 Codex（`codex exec`） | ZWorkbench（`codex app-server` + owner） | 类型 |
|---|---|---|---|
| **净时间** | 墙钟耗时（rc=0 且结果正确） | 墙钟耗时（completed 且结果正确） | 连续量（越小越好） |
| **人工复查** | 为确认结果正确而人工复核的次数 | 同上 | 离散计数（越少越好） |
| **事后回看** | NO（仅 transcript，无 durable ledger） | YES（owner run 持久化 + recorded_view receipt + event/环境 digest） | 结构布尔（可复现差异） |

- **净时间** 受 ARK 抖动影响，单点 n=1 仅作趋势前证；正式出数须 N≥10 取中位数/均值。
- **事后回看** 是**结构性、可复现**差异（裸 Codex 完全没有 owner-backed durable ledger），直接对应 **PG-3 护城河**，非单次耗时偶然——这是价值基线里"省心"的硬证据，不依赖省时。

## 3. 计算口径（省 X% / 少 Y 次）

- **省时 X%**：对第 i 个同构任务，`X_i = (t_bare_i − t_zw_i) / t_bare_i`。报告取 `median(X_i)` 与 `mean(X_i)`，并附 `t_bare`/`t_zw` 分布（P25/P50/P75），不报单点。
- **少复查 Y 次**：`Y = Σ_i (recheck_bare_i − recheck_zw_i)`；逐项记录 `recheck_bare_i ∈ {0,1,2,…}` 与 `recheck_zw_i`，汇总为总减少次数与 per-task 明细。
- **事后回看增益**：报告 `replay_recorded=true` 的任务占比（目标 100%）。这是"省心"的非时间维度证据。
- **门槛（临时，非承诺）**：N=10 默认路径实测中，`median(X) > 0`（ZW 不慢于裸 Codex 的中位）且 `Y > 0` 或 `replay=100%` 任一成立，即视为价值判据的可复核支撑；最终"可用"仍须三层 AND 全过。

## 4. 证据双标签纪律（acceptance 双标签 · R3 §acceptance 双标签纪律）

每个 acceptance 证据带布尔位 **`exercises_default_product_path`**：

- **`true`** = 走**默认产品入口**（`run` / `ui`，带 `--real-provider-gate` + `--provider-profile`/`--provider-config`，真实 ARK）+ 真实 Provider，且 receipt 100% 可复核。此类证据才计入"产品可用"价值判据。
- **`false`** = fixture / loopback / 绕过 CLI 的 seam 级测量 / 确定性状态机。即使通过也**只能标 scaffold**，正面打击"runner 多 ≠ 能力已实现"误判。

> 已有 C1-6 seam 基线（2026-10-01，n=1，绕过 CLI）：`exercises_default_product_path=false`，仅作趋势前证，**不**提前宣告 R3 `implemented`。

## 5. 测量协议（两档，明确分账）

### 5.1 Seam 级（已完成 · scaffold）
- 形态：绕过产品 CLI，直连 `codex app-server` + ARK `custom` provider，在 seam 层测对称三指标。
- 证据：`evaluation/evidence/competitive-baseline/README.md`（local-only，不入库）。
- 计账：`exercises_default_product_path=false`；n=1；仅趋势前证。
- 结论（2026-10-01）：ZW 净时间约 1/3.7（seam 级）、事后回看 YES vs 裸 Codex NO 为结构性差异、写链路落盘 md5 与裸 codex 一致。

### 5.2 产品路径级（S3 dogfood N=10 · 价值判据正式出数 · **deferred**）
- 主语：**zj 本人**（R3 验收判据主语 = zj；非作者陌生人 <5 分钟 已降为 deferred）。
- 入口：`run` / `ui` **默认入口** 带 `--real-provider-gate`（#40 已解，闸门式可达）。
- 条件：连续 10 次"只读分析 → 审批 → apply → local commit"全链路、**零越界、零 secret 落盘、receipt 100% 可复核**，同时采三指标。
- 计账：`exercises_default_product_path=true`；N=10；可并入"默认入口价值基线"与 S3 闸门合并测。
- **harness 已就绪（2026-10-10）**：`evaluation/runner/run_n10_value_baseline.py` + 任务清单模板 `evaluation/fixtures/n10-value-baseline/tasks.json`，已完成 `--self-test`（对比数学断言通过）与 `--dry-run`（不需 ARK 验证清单加载+聚合）。见 §9。
- **数据收集未执行**：需 zj 在场做真实任务 + 真实 ARK 凭证，属 Human-in-the-loop，显式 defer。

## 6. H1–H8 / C1–C7 runner 分类与离线可复核现状（2026-10-10 实测）

分类口径：是否需真实 Provider（ark/codex/deepseek/网络/凭证）。`evaluation/runner/` 下现有 runner 实测结果：

| Runner | 类别 | 离线可跑（2026-10-10） | 证据级 | 备注 |
|---|---|---|---|---|
| run_c4.py | C4 中断/恢复 | ✅ RAN（fixture 状态机） | scaffold（fixture_contract） | `exercises_default_product_path=false` |
| run_c5.py | C5 capability parity | ✅ RAN（loopback fake） | scaffold | 同上 |
| run_c7.py | C7 生命周期/审计 | ✅ RAN（deterministic fixture） | scaffold | 同上 |
| run_w8_worker_handshake.py | H2 handshake | ✅ RAN（fake loopback） | scaffold | 隔离 fixture |
| run_w8_dsh_bootstrap.py | H1 bootstrap | ✅ RAN（isolated fixture） | scaffold | 同上 |
| run_w8_evidence_replay.py | H5 replay | ✅ RAN（fixture-composed） | scaffold | owner-backed+fixture |
| run_w8_remote_provider_failover.py | failover | ✅ RAN（dual-loopback） | scaffold | 双 loopback 语义 fixture |
| run_w8_local_read_only.py | W8 本地只读 | ⚠️→✅ **已修复**（2026-10-10 corrective） | scaffold（fixture_contract） | 原 STALE：`LocalReadOnlyRunOrchestrator.run()` 新增 `run_claim` kwarg，fixture adapter 未接受→`TypeError` 在 `_start_run` 前炸；已给两个 fixture adapter 的 `execute` 加 `run_claim` 形参，`exercises_default_product_path=false` |
| run_w8_host_boundary_min_permissions.py | host 边界 | ⚠️ **ENV-GATED**（status `unknown/stop`） | scaffold | 设计内：需 macOS `sandbox-exec` 探针 + 真实 Codex 0.139.0 app-server；沙箱/CI 不可满足→`unknown/stop`，**非代码缺陷**，不假修 |
| run_c3.py | C3 写 parity | ⚠️ 需核（subprocess） | scaffold | 未在本节点深跑 |
| run_w8_worker_coding.py / lifecycle.py | H3/H4 | ⚠️ 混合（loopback/real-codex 探针） | scaffold+探针 | 未在本节点深跑 |
| run_w8_broker_capability_surface.py | C2 broker | ⚠️ loopback + subprocess | scaffold | 未在本节点深跑 |
| run_baseline / run_c2 / run_c6 / run_codex_* / run_deepseek_* / run_continuous_evaluation / run_w8_external_sandbox_native_approval / run_w8_host_broker_boundary / run_w8_local_read_only_security / run_w8_native_approval_matrix | 各 H/C | ⛔ **需真实 Provider**（ark/codex/deepseek/网络/凭证） | — | 本节点不跑；属真实评测，不在离线范围 |

**关键审计发现（严守 R3 纪律）**：
1. 离线 fixture runner **曾部分 stale**——初测 `local_read_only` 与 `host_boundary_min_permissions` 在当前产品代码（S0–S4 合并后）下 fail-closed。后续 corrective 已修复 `local_read_only`（API 漂移：`run_claim` kwarg 未接受）；`host_boundary_min_permissions` 经确认是**设计内 env-gated**（需 macOS `sandbox-exec` + 真实 Codex 0.139.0），非代码缺陷，不改。结论：这套评测脚手架相对产品 API 确有陈旧面，但本节点只修真 drift，不假修 env 依赖，也不谎报 green。
2. 能跑的 offline runner 全部自标 `fixture-contract / not production or candidate evidence`——**scaffold 绿 ≠ 产品已实现**。本节点不把它们计入"产品可用"价值判据。
3. 需真实 Provider 的 runner（含所有 `run_codex_*` / `run_deepseek_*`）本节点一律不跑，避免浪费真实额度；其通过与否与"价值基线出数"无直接等价关系。

## 7. 本节点（1-10-6）交付与 defer

**本次交付（2026-10-10）**：
- 本测量设计文档（指标 / 口径 / 双标签 / 两档协议 / runner 分类 / N=10 harness runbook）。
- 离线 fixture runner 实测分类 + staleness 审计发现（§6）。
- **corrective：修复 `local_read_only` fixture adapter**（`run_claim` kwarg 漂移）→ 离线 runner 复绿（§6）。`host_boundary_min_permissions` 确认为 env-gated，非缺陷。
- **N=10 价值基线 harness 就绪**：`run_n10_value_baseline.py` + 任务模板，self-test/dry-run 已验证（§8）。

**显式 defer（未完）**：
- 产品路径级 N=10 价值基线**数据收集**（§5.2/§8.4）：需 zj 作被试 + 真实 ARK 凭证，Human-in-the-loop，harness 已备好但本节点不代跑。
- 需真实 Provider 的 runner 全套：属真实评测，不在离线范围。

## 8. N=10 价值基线 harness（就绪 · 待 zj 主测）

> 本 harness 是**指标采集器 + 对比计算器**，不是产品代码、也不决定产品是否"完成"。它只量化：在固定任务集上，ZW 产品路径（真实 Provider + 默认闸门开）相对裸 Codex 控制臂是否省时间 / 少人工复查。

### 8.1 文件
- `evaluation/runner/run_n10_value_baseline.py`：harness 本体（仅 stdlib）。
- `evaluation/fixtures/n10-value-baseline/tasks.json`：N=10 固定任务集模板（live 跑前须锁定此集合）。
- `evaluation/fixtures/w8_local_read_only/v1/fixture_adapters.py`：被 corrective 修复的 fixture adapter（local_read_only runner 用）。

### 8.2 三指标 / 两臂（与 §2/§3 一致）
- 每 (任务, 臂)：`net_time_s`（墙钟 start→accepted completion）、`manual_review_count`（任务中人工重查/重跑）、`posthoc_review_count`（跑完后人工回看）。
- 两臂：`zw`（ZW 产品路径，真实 Provider）/ `control`（裸 Codex，同 Provider，无编排层）。
- 聚合：`time_saved_pct = (Σcontrol_time − Σzw_time)/Σcontrol_time×100`；`review_reduction = Σcontrol_review − Σzw_review`（带符号计数）。

### 8.3 三种模式
- `--self-test`：内嵌合成任务，断言聚合数学（含长度不匹配报错），**无 Provider**，CI 可跑。
- `--dry-run --tasks <file>`：加载任务集 + 确定性合成指标，验证清单加载与聚合，**无 Provider**，CI 可跑。
- `--live --tasks <file> [--zw-command CMD] [--control-command CMD] [--output DIR]`：交互式，**需 zj 在场 + 真实 Provider 凭证**（环境变量注入，harness 不读不打印）。每任务每臂：可选命令包住产品/裸 Codex 调用，或交互计时；人工录入两个复查计数。输出证据 JSON（`exercises_default_product_path=true`，**local-only，不入库**）。

### 8.4 zj live runbook（数据收集时执行）
1. **锁定任务集**：编辑 `evaluation/fixtures/n10-value-baseline/tasks.json`，定稿 10 个真实会做的开发任务（zw 臂与 control 臂必须用同一批）。
2. **准备真实 Provider**：把 ARK `custom` provider 凭证放入环境（`CODEX_*` / config.toml inline token，绝不落 argv）；确认产品默认入口可达（`run`/`ui` 带 `--real-provider-gate` + `--provider-profile`/`--provider-config`）。
3. **跑 zw 臂**：对每任务走 ZW 产品路径完成"只读分析 → 审批 → apply → commit"，记墙钟 + 两个复查计数。可用 `--zw-command` 包住产品调用以自动计时；否则交互计时。
4. **跑 control 臂**：对同一批任务走裸 Codex（同 Provider、无编排层），记同样三指标。可用 `--control-command` 包住 `codex` CLI；否则交互计时。
5. **生成证据**：`python evaluation/runner/run_n10_value_baseline.py --live --tasks evaluation/fixtures/n10-value-baseline/tasks.json --output evaluation/evidence/value-baseline-1-10-6/live`，得到 `n10-value-baseline.json`（含 `time_saved_pct` / `review_reduction` / per-task）。
6. **回填**：把 `time_saved_pct` / `review_reduction` / `replay_recorded%` 填回本文件 §5.2，并把证据 JSON 留在 `evaluation/evidence/`（local-only）。**仅此时 1-10-6 的价值判据才算正式出数。**

> ⚠️ `--live` 在 CI/沙箱**不可跑**：既需人在键盘，又需真实凭证。本 harness 的 CI 可跑部分仅 `--self-test` / `--dry-run`。

## 9. 完成判据（节点 1-10-6）

- [x] value-baseline 测量设计固化（指标/口径/双标签/协议/harness runbook）——本文件。
- [x] 离线 runner 分类 + staleness 审计（§6）。
- [x] local_read_only corrective 修复（API 漂移）→ 离线 runner 复绿。
- [x] N=10 价值基线 harness 就绪 + self-test/dry-run 验证（§8）。
- [ ] **产品路径 N=10 价值基线数据收集出数**（`exercises_default_product_path=true`，zj 主测）—— **deferred，未完**。

> 结论：**1-10-6 测量设计 + 离线审计 + local_read_only 修复 + N=10 harness 就绪 已完成；价值判据正式出数（N=10 产品路径数据收集）仍 deferred**，故 R3 仍 `target`，不提前宣告 `implemented`。runner 绿（含 scaffold 绿）一律不冒充产品交付证据。
