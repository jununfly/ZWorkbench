---
doc-kind: product-requirements
authority: supporting
status: target
implementation-status: unknown
---

# R3 真实可用路线图

> 本文件是产品规划草稿，不是实现事实。所有未由 owner-backed 证据证实的能力标 `target` 或 `unknown`。
> 评测脚手架（H1–H5 / C1–C7 runner）通过 **不等于** 产品能力已实现；二者必须分开计账。

## Problem Statement

ZWorkbench 的目标组合是 DSH 主 Harness + 进程外 Codex Coding Worker + 唯一 durable CompositionOwner。当前产品入口仍是 **Codex-only 本地只读回退基线**（`local_read_only_run`），目标架构未产品化。

对单人开发者而言，"真实可用"的终态判据是：能在**真实项目**上产生**可追溯写副作用**（改文件 + commit + push，其中 push 为单独门），并接入**真实 Provider**（而非 loopback/fake）——且须同时满足下文三层判据 AND 门。

现状缺口（来自 AGENTS.md / 架构 wiki / evaluation runners）：

- 写边界（`ta-reversible-write-boundary`）显式 `HOLD`：case-local fake sink 能验证合同，但推不出真实项目写入 / Git push / 部署 / live replay 已获准。
- Provider 仅 loopback/fake；真实网络、凭证、远端 effect 全部 deferred。
- DSH 仅实现 H1 bootstrap seam；完整主 Harness 驱动未产品化。
- 验证矩阵 H1–H8 + C1–C7 中，**H6–H8 scope 缺口已于 2026-09-27 收敛**（H6 首版 = 单 Provider 子集；H7/H8 标 `deferred-until-demand`；详见下文切片顺序与"产品定位与架构约束"节）。

核心风险：评测脚手架很多，但 `zworkbench run` 实际只做 case-local 只读任务。进度最易被误判为"快好了"。

## Stage 模型与当前证明状态

验证矩阵分两组：**H-series（DSH–Codex 桥接类）** 与 **C-series（CompositionOwner 类）**。下表区分"验证脚手架"与"产品能力"两列——这是本项目的关键纪律。

| Stage | 内容 | 验证脚手架（evaluation） | 产品能力（product） |
|---|---|---|---|
| H1 | DSH artifact-mode bootstrap seam | implemented — `dsh_runtime.py` + `run_w8_dsh_bootstrap.py` | target（仅 seam，无完整 runtime） |
| H2 | Worker handshake | implemented — `run_w8_worker_handshake.py` | target |
| H3 | Worker 只读 coding | implemented — `run_w8_worker_coding.py` | target |
| H4 | Lifecycle（cancel/timeout/crash） | implemented — `run_w8_worker_lifecycle.py` | target |
| H5 | Replay（recorded/simulated） | implemented — `run_w8_evidence_replay.py` | `live` 模式 default-deny（HOLD） |
| H6 | 真实 Provider 兼容 | scope 已定（2026-09-27）：首版 = **单 Provider（Ark `ark-code-latest`）+ 有界重试 + 失败分类 + unknown→safe-stop**；不做多 Provider failover（标 H6-full / post-MVP）；凭证 env+stdin 注入，禁落盘 / 命令行参数 / owner | target（S1 切片） |
| H7 | DSH 全 runtime / plugin 组合 / 路由 | **`deferred-until-demand`**：不定 scope、不建；触发条件 = 第二用户 / 团队信号；未来若建首形态 = H7-lite（最小本地编排，无 plugin 市场） | deferred |
| H8 | 生产部署 | **`deferred-until-demand`**：不定 scope、不建；分层台阶（L8a 本地命令稳定 → L8b 本机常驻 → L8c 可发布）仅占位 | deferred |
| C1 | Candidate 执行（基本任务） | implemented — `run_deepseek_challenger.py` 等 | target |
| C2 | Provider fail-closed / capability broker | implemented — `run_w8_broker_capability_surface.py` 等 | target |
| C3 | 写副作用 parity / uncertain-reconcile | implemented（fixture）— `run_c3.py` 等 | target（未产品化） |
| C4 | 中断 / 恢复 | implemented（fixture）— `run_c4.py` 等 | target（未产品化） |
| C5 / C6 | capability parity / approval | implemented（fixture）— `run_codex_c5_c6.py` 等 | target（未产品化） |
| C7 | 生命周期 / 升级 / 审计 / 备份恢复 | implemented（case-local fixture）— `run_c7.py` 等 | real-world 部分 unknown（远端账户 / retention / 账单） |

判定规则（沿用 AGENTS.md §6）：任一关键 identity / effect / Provider / replay 状态为 `unknown`，完成状态即 `unknown`/`safe-stop`，不自动 retry。

## 真实可用缺口（缺失 stage）

从回退基线到"真实可用"，必须跨越以下缺口。当前状态：1–3 / 5–6 为 `HOLD` / deferred / 未产品化；4（scope 缺口）已收敛为终态条款。

1. **真实写副作用**（最核心缺口）：隔离 worktree 上 diff apply + local commit（**push 为单独门 S4，默认关**）。对应 C3/C4/C5/C6 的*产品化*，而非 fixture。必须带 host enforcement 证明（路径 / 进程 / 网络边界的实际强制），不能靠配置声明假装。
2. **真实 Provider**：当前 loopback/fake → 真实 Codex/API + 网络 + 凭证。对应 `docs/references/optional-real-provider-staging.md` 与 `optional-real-codex-provider-staging.md`（两份 references 仍为 "optional" deferred）。
3. **完整 DSH 主 Harness 驱动**：当前 Codex-only 回退，仅 H1 bootstrap；H2–H8 的 DSH 全 runtime / plugin 组合 / 路由未产品化。
4. **H6–H8 scope 已定义（2026-09-27 收敛）**：solo 真实可用的依赖闭包只含两条并行 seam——**写副作用 seam + 单真实 Provider seam**；H7/H8 不在闭包内，标 `deferred-until-demand`（不定 scope、不建）。结论同时确立切片顺序 S0–S4（见下）与架构负约束（见"产品定位与架构约束"节）。
5. **live replay 产品化**：H5 的 `live` 模式默认拒绝，回放不执行真实 effect。
6. **C7 真实世界部分**：本地升级 / 备份 fixture 有，但远端账户、retention、账单、本地退出 ≠ Provider 退出未做。

## 缺口图（文本版）

~~~text
[local_read_only_run 回退基线]  Codex-only · 写边界 HOLD · fake Provider
        │
        ▼
[H1–H5 验证脚手架]  只读安全已证明，≠ 产品能力
        │
        ▼  真实可用 = 跨过以下缺口（全 HOLD / deferred / 未定义）
   ┌────────────────────┬─────────────────────────┐
   │ 真实写副作用        │ 真实 Provider            │  ← 最小可用切片（门槛）
   │ diff apply+commit+  │ 真实 Codex/API+网络+凭证 │
   │ push 到真实项目      │                         │
   ├────────────────────┼─────────────────────────┤
   │ 完整 DSH harness     │ live replay + C7 真实退出 │  ← 完整产品（做完非可用）
   │ H7/H8 deferred-until- │ real-world 远端账户/retention│
   │ demand（不定 scope）  │                          │
   └────────────────────┴─────────────────────────┘
~~~

## 最小可用切片（门槛）

对个人 solo 场景，**不必等完整 DSH / H6–H8**。真实可用的最小 MVP = **真实写副作用 + 真实 Provider** 两条并行 seam：

- 生成的 diff 能应用到隔离 worktree / 可丢弃 repo 并 apply + local commit（**push 是单独门，默认关**）；
- 接你的真实 Provider（首版单 Provider：Ark `ark-code-latest`，无 failover）。

完整产品（DSH 全 harness + H7/H8 + live replay + C7 真实世界）是"做完"门槛，不是"可用"门槛；H7/H8 已标 `deferred-until-demand`。

## 已锁定的切片顺序（solo 真实可用路径，2026-09-27 拍板）

`S0 host-enforcement spike → S1 单 Provider 产品化（无 failover）→ S2 写 seam（隔离 worktree + apply + local commit only + receipt）→ S3 dogfood N=10 闸门 → S4 push 单独门`；之后才谈 H6-full（多 Provider failover ledger）/ H7-lite（最小本地编排）/ H8 分层。

- **S0**：证明被沙箱约束的 Worker 子进程无法越界写 / 联网；技术选型（macOS seatbelt / 容器 / VM，Linux bwrap）在 spike 内定，不预判。fail-closed 判据见 ADR 0008。
- **S3 dogfood 闸门 N=10**：连续 10 次默认入口完成"只读分析→审批→apply→local commit"，零越界、零 secret 落盘、receipt 100% 可复核，才开 S4 push 门。**价值基线测量与 S0 并行启动、有效出数挂在 S3 与 N=10 合并测**（量化"比裸 Codex 省时"）——S0 阶段产品默认路径尚不存在，单独测只能测到裸 Codex vs 裸 Codex。
- 残留前提：单 Provider 无 failover 以"Ark 对 zj 足够稳"为前提；若要求"被限流 / 封号不断活"，failover 前移至 S2/S3 之间。

## 产品定位与架构约束（2026-09-27 随 scope 收敛新增）

- **品类定位句**：ZWorkbench = "owner-backed、fail-closed 的 AI 写真实 repo 工作台"。差异化在可复核审计 / replay / safe-stop，而非 coding 能力本身（与 Claude Code / Aider / Cursor 区分）。所有 stage 讨论以此为前提。
- **护城河优先级**：owner-backed 审计 / replay / safe-stop 的 C-series 从 fixture 提升为产品默认路径可复核证据，优先级高于 H6/H8 plumbing。**落点**：S2 的 receipt 即 owner-backed 审计的最小可复核单元（搭车实现，不另开战线）；replay / safe-stop 产品化随后逐级加，各自带独立 acceptance。
- **架构负约束（防 foreclosure，适用于 S1/S2 及所有后续切片）**："H7/H8 不定 scope" ≠ "不做架构预留"：
  1. Provider 接入必须经 **Host Capability Facade**，产品代码不得直连——否则 H6-full 多 Provider 与未来 DSH 均需返工；
  2. 写 seam 的 receipt / approval 数据模型不得引入**第二个 durable owner**（ADR 0001 不变量）。
- **acceptance 双标签纪律**：复用 C-series fixture 框架，但每个 acceptance 证据带布尔位 `exercises_default_product_path`；fixture-only 的即使通过也只能标 scaffold（正面打击"runner 多 ≠ 能力已实现"误判）。
- **写操作爆炸半径分级**：diff apply（可 revert）→ local commit（可 reset）→ push（难撤回）三级，分别配 approval 粒度与 receipt；首切片限定隔离 worktree / 可丢弃 repo，不碰主工作区。

## 产品目标（PG · 以产品可用为准绳，2026-09-27 补强）

> 来源：H6–H8 scope 收敛之后，产品规划权威视角以「产品可用」为第一目标重排目标与动作。scope 结论（S0–S4 工程切片、H7/H8 deferred）不变，本节补"目标怎么排、怎么判真可用"。

排序逻辑（zj 拍板修正）：工程闭环（PG-1）与信任最小单元（PG-3）**并行交付**，价值基线（PG-2）设计与 S0 并行、出数挂 S3；三者同为「可用」AND 门，最后是扩展（PG-4 deferred）。

| # | 产品目标（PG） | 一句话 | 服务哪层判据 | 对应切片 |
|---|---|---|---|---|
| **PG-1** | 可信执行闭环 | 默认入口在真实 repo 完成"分析→审批→apply→commit"，fail-closed | 工程判据 | S0→S3 |
| **PG-2** | 价值可见 | 量化"比裸 Codex 省时/省心"，证明投安全外壳值得 | 价值判据 | 价值基线（与 S0 并行，出数在 S3） |
| **PG-3** | 护城河固化 | owner-backed 审计/replay/safe-stop 成为产品默认路径可复核证据，而非 fixture | 用户判据（信任） | S2 receipt 搭车 + 后续 replay/safe-stop 逐级 |
| **PG-4** | 可扩展/可发布（deferred） | 第二用户/团队信号触发 H7/H8 | — | H7/H8 deferred-until-demand |

> 优先级（zj 拍板修正）：**PG-1 工程闭环 与 PG-3 信任最小单元（receipt，搭 S2 车）并行交付、同为「可用」硬门**；PG-2 价值基线设计与 S0 并行启动、出数挂 S3，同为「可用」硬门（三层皆 AND）；PG-4 是"做完"门槛（deferred）。「不必盯着」本就是 PG-3 交付物，故信任不得滞后于工程闭环——原"PG-1 > PG-2≈PG-3"排位作废。

## 推荐 sequencing（两 lane，2026-09-27 更新）

**Lane A — 最小可用（优先，即上方 S0–S4 切片顺序）**
1. S0 host-enforcement spike（fail-closed 判据见 ADR 0008，判据须可测试断言，防退化成 demo）。
2. S1 单 Provider 产品化：把已验证的 Ark 只读路径从 `scripts/` 收进默认入口 + owner 记录失败分类 / safe-stop；env+stdin 注入凭证、secret 0 落盘；经 Host Capability Facade 接入。**Provider-side 退出记账**：对真实 Ark 发请求即产生远端 retention / 任务，沿用 staging runbook 的 `unknown / delegated` 口径如实记账、不假装已清除（非阻塞，见 `docs/references/optional-provider-exit-inventory.md`）。
3. S2 写 seam 产品化：approval 精确绑定 operation/action/resource/idempotency key；隔离 worktree；diff apply + local commit only；receipt（= owner-backed 审计最小单元）。
4. S3 dogfood N=10 闸门（含价值基线出数）。
5. S4 push 单独门：单独审批 + push，幂等防重复物理副作用。

**Lane B — 完整产品（`deferred-until-demand`）**
6. H7-lite / H8：不定 scope、不建；触发条件 = 第二用户 / 团队信号。live replay 产品化与 C7 真实世界部分同样等 dogfood 拉力再启动。

## 下一步行动（双开工线 · 2026-09-27）

scope 已收敛、R3/ADR 0008 已沉淀、工程切片 S0–S4 已锁定。作为产品规划权威视角的收口，把「产品可用」拆成两条必须并行的开工线，避免工程自嗨推到尽头才问"有人用吗"：

- **开工线 A（信任）**：立即启动 **S0 host-enforcement spike**——它是 PG-1 最长板、最大未知，不解决则一切 acceptance 空中楼阁（fail-closed 三判据见 ADR 0008）。
- **开工线 B（价值）**：同步启动 **价值基线测量设计**（先定"测什么、怎么算省时"，不写代码），待 S3 出数。

二者并行，S1/S2 在 A 出证后跟进。第一目标"产品可用"从第一天起即有"信任 + 价值"双指针牵引。

## 风险

- **验证 ≠ 产品**：runner 多不代表能力已实现；汇报进度必须分开计账（acceptance 双标签纪律见上）。
- **脚手架繁荣的进度错觉**：H1–H5 / C1–C7 runner 全绿，但产品最硬的两道门（host enforcement、失败分类 / safe-stop 承载）此前 0 行实现——必须先启动 S0 spike，而非继续在 fixture 层打磨。
- **写边界 fail-closed 不变量**：真实写副作用必须带 host enforcement 证明（须独立于配置声明真正约束路径 / 进程 / 网络），是架构硬约束不是偷懒，不能绕过；enforcer 失效时 Worker 拒绝启动，绝不降级为无沙箱运行。

## 开放决策（2026-09-27 已收敛）

- ~~A：先钻"真实写副作用"scope gate，还是先补 H6–H8 scope？~~ **已决**：scope 定义与 build 解耦；H7/H8 定义不建（连 scope 也不定，标 `deferred-until-demand`）；build 走 S0–S4，S0（host-enforcement spike）为下一节点。
- ~~真实可用是否接受"仅单人 solo，不要求完整 DSH"？~~ **已决**：接受；solo 真实可用 = 两条并行 seam（写副作用 + 单真实 Provider）。

## 产品可用判定门槛（三层判据 AND 门，2026-09-27 升级）

> 2026-09-27 产品规划权威视角补强：把「真实可用」从纯工程判据升级为**三层判据必须同时满足**。`产品可用 = 工程判据 ∧ 用户信任判据 ∧ 价值判据`。任一不达标 → R3 维持 `target`；**「可用」宣告不因工程闭环（S0–S3）完成而提前，须等价值基线出数**（价值判据是最后一塊拼图，见 PG-2）。

### 工程判据（硬门）
- 真实项目隔离 worktree 上 diff apply + local commit 成功（push 为单独门），且 CompositionOwner 出具可复核 receipt（operation / action / resource / idempotency key 绑定）；
- 真实单 Provider（Ark `ark-code-latest`）接入：失败分类记录率 100%，unknown→safe-stop，无 silent switch；凭证 env+stdin 注入，secret 落盘 0 次（含 owner snapshot / backup 自动扫描）；
- 未知 identity / permission / effect / Provider / replay 状态仍 `safe-stop`，无自动 retry；
- host enforcement 按 ADR 0008 三判据出证（fail-closed 可测试断言，violation 事件入 receipt）；
- S3 dogfood 闸门：连续 10 次默认入口完成全链路，acceptance 证据全部带 `exercises_default_product_path=true`。

### 用户信任判据（硬门）
- zj「愿意每周交给它、不必盯着」：失败可预期、可复核、可回退；错误发生时 **fail-safe 而非 fail-open**；receipt 成为默认路径可复核证据，不必每次人工复查（PG-3 动作 3.1 + 3.2 落地）。

### 价值判据（硬门 · 须等出数）
- 价值基线测量（与 S0 并行启动、有效出数挂在 S3 与 N=10 合并测）给出量化结果：证明"比裸 Codex 省 X% 时间 / 少 Y 次人工复查"，作为继续投安全外壳的前置论证。

满足以上**全部**三层，R3 标 `implemented`（产品可用达成）；任一不满足，R3 维持 `target`。

## 证据来源

- `AGENTS.md` §2 / §5 / §6：scope gate、变更路由、definition of done（C1–C7 / H1–H8 验证矩阵）。
- `docs/architecture/ta-overview.md`：目标架构与回退基线边界。
- `docs/architecture/ta-dsh-runtime-integration.md`：H1 bootstrap seam（已实现范围）。
- `docs/architecture/ta-codex-worker-bridge.md`：H2 handshake / H3 只读 coding（已实现范围）。
- `docs/architecture/ta-reversible-write-boundary.md`：写边界 `HOLD` 规则。
- `docs/README.md`：ontology 与"评测通过 ≠ 产品能力已实现"纪律。
- `evaluation/runner/`：`run_w8_*` / `run_c2..c7` / `run_codex_*` / `run_deepseek_*`：当前验证脚手架事实源。
- `README.md`：当前 `local_read_only_run` 入口与默认边界。
- `docs/zj-adr/0008-host-enforcement-is-fail-closed-and-testable.md`：S0 host enforcement 决策与 fail-closed 三判据。
- `docs/references/optional-real-provider-staging.md` / `optional-real-codex-provider-staging.md`：真实 Provider staging 合同（Ark 5/5 + Codex turn 1/1、`raw_credential_persisted=false` 已验证）。
- `docs/references/optional-provider-exit-inventory.md` / `optional-provider-exit-primary-sources.md`：Provider-side 退出责任记账口径。
- H6–H8 scope 收敛过程（Human+AI 第一遍 + Agent B/C/A 三视角观点 + 拍板）原记录于 `docs/discussions/h6-h8-scope-kickoff.md`（已按 `_POLICY.md` 删除；结论已沉淀至本文件与 ADR 0008）。
