---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.v1.codex-only-fallback-and-write-boundary-sequencing
---

# ADR 0009：v1 是 Codex-only 回退基线的合法延伸；写入边界按 R3 序列逐步放松

> 状态为 `accepted`：2026-09-30「如何把 ZWorkbench 做到用户能真实可用」讨论（discussions/make-it-usable）四子文档收敛后沉淀；sub-04 gate 决策（绕开 DSH 出货）+ sub-02 写入断层结论合并。

## Context

目标架构 = DSH 主 Harness + 进程外 Codex Coding Worker + CompositionOwner。但事实核查（sub-04 A 视角）表明：产品路径从未经过 DSH。今日 session/插件组合/任务路由由 Codex CLI 内部承担（仅算 evidence），`dsh_runtime.py` / `worker_bridge.py` 仅为 H1/H2/H3 seam 真实实现，只被 tests/evaluation 调用，产品栈（cli → local_run → codex_adapter → CompositionOwner）对 `dsh` 零引用。DSH Harness 本体（Agent loop / 插件组合 / 任务路由）= target/unknown。

同时，真实写入能力（sub-02）与 DSH 无关：写边界（S0→S2）是 ADR 0008 / ownership 不变量，受 S0 host enforcement 约束。sub-04 的「绕开 DSH」二元框架对写边界是盲的——必须显式区分两个维度的门（C1-补）。

sub-01 的 Q3 验收线（v1「真能用」= (i) 只读 owner-backed 证据 vs (ii) S0→S2 真写链路入 v1）仍 `NEEDS_CONTEXT`，待 C1-6 竞品对照取证；本 ADR 不预写该选边。

## Decision

1. **v1 = Codex-only 回退基线的合法延伸（非重新设计）**：v1 在 {Codex-worker + CompositionOwner + loopback UI} 出货，不建 DSH Harness。DSH 接入点 = H1/H2 seam（implemented，可作 frozen 接入点）；DSH Harness 本体 = target/unknown（三态措辞，防误写为 implemented）。H7 trigger 到来时第一步不是建 DSH，而是跑 seam 契约测试 + 对齐 IdentityChain / provider_identity（含 transport）字段；若存在 drift 先做契约对齐切片。

2. **C1 六条挂接约束 + C1-补 作为可接受闸门**（约束 sub-01/02/03）：
   - C1-1：v1 执行器 = 复用 `codex_adapter`，禁止在入口/CLI 新建 agent loop（防第二个 harness）。
   - C1-2：关键路径 = `S0 → S1 → S2 → S3(N=10) → S4`；DSH 不在路径上。
   - C1-3：S0 host enforcement 是唯一无上界硬门，排期由 S0 决定；S0 出口 = 三断言 + 一否定测试（enforcer 失败 → Worker 拒绝启动，绝不降级）。
   - C1-4：判据主语 = zj 本人（R3 三层 AND 门 + N=10）；MASTER「非作者陌生人 <5 分钟」降 deferred-until-demand + sub-03 UX 目标。
   - C1-5：默认入口 = README 首屏可见且真实 repo 产可感知产出；`zworkbench ui` 要么进 README，要么宣布非产品入口。（注：C1-5 的「≥1 diff/commit」以 sub-01 Q3 选 (ii) 为条件；sub-01 当前 NEEDS_CONTEXT，未选边前 README 不得预先宣称写能力。）
   - C1-6：价值假设前移到可证伪：S0 前做一次零代码竞品对照（Claude Code 同任务，记录净时间差 / 人工复查次数 / 事后能否回看），落盘 `evaluation/evidence/competitive-baseline/`。
   - **C1-补**：「绕开 DSH」≠「绕开写边界」；真实写边界（S0→S2）是 ADR 0008 / ownership 不变量，与 DSH 无关。

3. **写入边界放松 = R3 序列（不重编号）+ 每档 DoD 四字段**：(放行副作用类别) × (本档依赖强制层 L1/L2/L3) × (一条可机械判定验收命令) × (验收人：zj + 承接 Agent)。任一档若 L3 缺席，`exercises_default_product_path` 只能标 false。策略预授权 = **(a) 两档制**（自动 / 单次确认，增量≈0，复用现有 token 链）；**正面禁止** CLI/config/UI 侧出现 owner 不知的预授权第三态（否则授权判定分裂为第二源，违反 ADR 0001 / ADR 0008 L31）。

4. **C5 提升为已决**：`zworkbench run` 的 provider identity 与真实传输不一致且静默（`--provider` 对传输零效力、`--endpoint` 不被消费、`provider_identity` 缺 transport、有 `setdefault` 反向回填）→ 登记为 **S1 第 0 步前置闸门**（identity↔transport 单一来源绑定 + 删 `setdefault` + 补 4 条 fail-closed 测试）；跟踪 issue #39。sub-03 wizard 在 #39 关闭前不得宣称 `--provider/--endpoint` 生效。

5. **不引 sub-04 B 视角观点1 作独立锚点**：其「run→执行器空洞」发现在 sub-04 conclusion 的「解法」节已转述吸收，引用以 conclusion 为准（ontology 合成层核实）。

## Consequences

- v1 出货时间由 S0 决定，不由 DSH 决定；H7/H8 维持 deferred-until-demand，不占 v1 依赖闭包。
- 唯一 owner 不变式守住（sub-04 A 观点5）：v1 新增编排能力只准落在 CompositionOwner 或显式命名 seam 模块；cli.py / local_run.py 不得新增 session/retry/routing 状态字段（grep 断言 + 测试护栏）。
- 安全洞（sub-02 S 视角）登记为 S1/S2 前置 DoD（非阻塞但须实施）：loopback 写面加 Host/Origin 校验 + nonce；approval decision 绑定 `decided_by`；脱敏下沉存储层；token 通道绑定 + TTL 下调；`external_receipt` 定义成独立证据源、缺失即 `mark_effect_uncertain`；执行级幂等测试。
- 前置 DoD（阻塞 S1 开工）：preflight 三条 deny 分支各一条负路径断言；唯一词表映射表落 owner 侧作 SSOT + 一致性测试。
- sub-01 Q3 验收线选边仍 `NEEDS_CONTEXT`，待 C1-6 竞品对照取证；本 ADR 不预写该选边。
- 关联：R3「真实可用路线图」承接本 ADR 每档 DoD 四字段（见其「S0–S4 切片 DoD」节）；onboarding 首跑设计见 `docs/prds/r4-onboarding-first-run.md`。
