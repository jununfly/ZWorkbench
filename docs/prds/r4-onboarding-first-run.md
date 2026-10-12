---
doc-kind: product-requirements
authority: supporting
status: target
implementation-status: implemented
---

# R4：首跑与 onboarding 设计

> 来源：2026-09-30「如何把 ZWorkbench 做到用户能真实可用」讨论 sub-03（分发/安装/首次运行 UX）结论沉淀。
> 本文件是产品规格，不是实现事实；未由 owner-backed 证据证实的能力标 `target` / `unknown`。
> 设计层（首跑最小形态、只读自检 `doctor`、价值演示缝合、端到端旅程）已沉淀为 [pd-first-run-onboarding](../designs/pd-first-run-onboarding.md) 与 [ep-first-run-journey](../designs/ep-first-run-journey.md)，本 PRD 不再重复。

## Problem Statement

当前无面向非作者用户的安装 / quickstart / onboarding；真实 Provider 配置在产品中未文档化（仅 references 与 ZJ-CONTEXT 提及「真实 Provider 安全 wizard」）。成功判据「非作者陌生人 <5 分钟跑起来」在 solo 场景下无可测对象（仓库仅 zj 单一贡献者），且违反「不得把 UX 目标误写成验收判据」的不变式（C4）。

## 主语分轨（承接 C1 约束4）

| 轨 | 主语 | 性质 | 验收口径 |
|---|---|---|---|
| **验收轨** | zj 本人 | 机械判定（可作 MASTER / R3 状态依据） | 干净 venv + 空 `case_root` 下，从 `pip install .` 到「在 loopback UI 看到自己首跑 `recorded_view_present=true`」的端到端脚本退出码 0 且可重放 |
| **UX 目标轨** | 非作者陌生人 | **非判据**、不进 MASTER 状态 | 仅登记代理指标「是否需要作者在场 / 卡点数」与恢复触发条件（出现第 2 位真实使用者 → 重开 sub-01 Q1） |

> 「非作者陌生人 <5 分钟」降为 deferred-until-demand + 本文件的 UX 目标，不得写回验收判据。

## 首跑最小形态（设计见 pd-first-run-onboarding）

- 新增 `zworkbench run --prompt "..."`（或 `zworkbench demo`）：自动在默认位置脚手架 `case-root + workspace + state` 子目录；`--codex` 缺省按 PATH 探测并打印实际解析路径；原完整参数形态保留为高级用法。
- Provider 默认 `fake-loopback`（零配置、恒真可达），不要求任何外部凭证。

**验收**：不读 README 的用户用单条命令完成首跑。

> 完整设计与边界见 [pd-first-run-onboarding](../designs/pd-first-run-onboarding.md)（首跑最小形态 / onboarding 自检 / 价值演示缝合）。

## onboarding = 只读自检 `doctor`（设计见 pd-first-run-onboarding）

- 只探测（Codex 可执行性、case 目录约定、loopback provider 可达性），输出 readiness 报告 + 每项失败对应 fix hint，**不采集、不存储任何凭证**。
- 真实 Provider 在首跑路径中改写为「显式旁路」：doctor 报告末行指向 staging runbook 引导（声明 owner 自持 Key 的按需动作）。
- **C3 强约束**：wizard 今天仅是路线外 owner 工具（`scripts/` 下 4 个 `/zj-wizard` 生成物），不产品化为首跑步骤；禁止 onboarding 收集/持久化任何凭证（`no_credentials_in_config` deny 语义）。
- issue #39 关闭前，doctor 报告不得输出「配置真实 Provider 步骤已完成」类表述（与 C5 一致）。

**验收**：doctor 在零凭证环境下全绿可跑，`git status` 无副作用文件。

## 价值演示缝合（next_steps，设计见 ep-first-run-journey）

- `run` 完成且写了 `--db`（或默认 `case_root/state/composition.sqlite3`）后，在 stdout 末尾追加 `next_steps` 数组（可复制的 `zworkbench ui-host --review` 或 `zworkbench ui --db <实际 db 路径>`）。
- 进一步 `zworkbench run ... --open`：子进程自动拉起 `ui-host`（仍 loopback、仍只读）。

**验收**：首跑脚本跑通后无需读 README 即可在浏览器打开看到自己 run 的 recorded view。

> 端到端旅程（pip → run → loopback UI 见 recorded view）见 [ep-first-run-journey](../designs/ep-first-run-journey.md)。

## fail-closed UX 成本回收

- `PreflightViolation` 增加 `hint` 字段（人类可读修复动作，如「mkdir -p <case-root>/workspace 或运行 zworkbench init」），保持现有 JSON schema 兼容、机器可解析部分不变。
- 首跑场景把 `--timeout` 默认提高（如 120s）或在状态输出显式区分 `timeout` 与 `failed` 并给重试提示。

**验收**：人为制造「目录缺失」「超时」两种失败，输出须包含可执行修复动作。

## 端到端回归脚本验收线

- 给定干净环境（仅装 python3.9+），从 `pip install .` 到「在 loopback UI 看到自己首跑的 recorded view」的端到端脚本必须可重放（用 `fake-loopback`、零外部凭证），脚本本身入库（tests/ 或 scripts/）作 onboarding 回归测试。
- 验收线机械判定：脚本退出码 0 且 `recorded_view_present == true`；对照三项指标（C1-6）已于 2026-10-01 落盘 `evaluation/evidence/competitive-baseline/`（ZWorkbench owner-backed replay 一项明确更优），价值证明条件已满足，首跑价值演示可据实测陈述。

**做到什么程度算完**：脚本绿 + 至少 2 份真实走查记录（计时起点 = 第一条命令；走查者须为未参与本仓开发者或隔周作者本人；记录总耗时 / 卡点数 / 最终是否看到 recorded view；卡点数 ≤ 2）。

### 验收进度（如实分栏，2026-10-13 复核）

复现环境：干净 venv（Python 3.13.12，`python -m venv`）→ `pip install .`（wheel `zworkbench-0.1.0`）；源码副本装在 `/tmp` 的工作副本上，未污染本仓工作树；全程 `ARK_API_KEY` / `OPENAI_API_KEY` 已 unset，走 `fake-loopback`、零外部凭证。

| 判据 | 状态 | 证据 |
|---|---|---|
| 端到端脚本可重放（exit 0 且 `recorded_view_present == true`） | ✅ | `scripts/first_run_e2e_regression.py` 在干净 venv 下 `EXIT=0`，输出 `PASS: first run completed and recorded_view_present == true`；另以安装产物 console script `zworkbench run` 交叉跑通（`status=completed`，owner `recorded_view_present=true`，replay `zw-r4-console:recorded-view`，turn 文本 `CONSOLE-SCRIPT-OK`） |
| `doctor` 零凭证全绿 | ✅ | `zworkbench doctor` 三项 `pass`（codex_executable / case_layout / loopback_provider），`status=ready`，`EXIT=0` |
| `doctor` / 首跑零副作用 | ✅ | doctor 前后 case_root 目录树不变（无 `state/` `codex-home/` `events/`），本仓 `git status --short` 前后 diff 为空 |
| 「目录缺失」失败含可执行修复动作 | ✅ | `doctor --case-root <不存在路径>` → `not_ready`，`EXIT=1`，hint = 「create the missing directory, or pass --case-root (and --workspace) pointing at existing directories」 |
| 「超时」失败含可执行修复动作 | ✅ | 挂起式 fake codex + `--timeout 2` → `status=failed`，`error={"type":"TimeoutError","category":"timeout"}`，`retry_hint` = 「连接/传输超时：检查 provider endpoint 可达性（zworkbench doctor），或增大 --timeout」 |
| 至少 2 份真实走查记录（走查者须为未参与本仓开发者或隔周作者本人；记录总耗时 / 卡点数 / 最终是否看到 recorded view；卡点数 ≤ 2） | ⏭️ **owner 豁免**（0 / 2） | 2026-10-13 zj 显式决定：不做外部/隔周走查，视为通过。**这是判据豁免，不是判据满足** |

### 豁免留痕（waiver）

- 时间：2026-10-13；决策人：zj（本 PRD 作者 / owner）。
- 内容：§端到端回归脚本验收线 中「至少 2 份真实走查记录」一条**整体豁免**，不再作为 R4 收口前置。
- 已满足的部分：上表机械判据 5 项全部 owner-backed（干净 venv `pip install .` 复跑，逐条证据见上）。
- 随豁免一并接受、但未消解的风险：
  - **无真实新手视角**：本仓作者之外的首次走查从未发生，安装/首跑路径上「新人卡在哪」零数据；
  - **卡点数 ≤ 2 无观测**：这是设计目标里唯一直接衡量 onboarding 摩擦的指标，现为零观测；
  - 上述两项是**已知盲区**（不是未知风险），一旦对外分发须优先补外部走查。
- 重开条件：产品进入「给非作者使用」阶段时本豁免自动失效，须补齐 2 份走查记录。

因此 `implementation-status` 记为 `implemented`：机械判据全部 owner-backed，人证判据经 owner 显式豁免。**须区分**：这不等于「走查已做过」。

## 约束与依赖

- 必须与 sub-02（ADR 0009）共用「显式授权」语义：onboarding 仅只读自检 + 定位回填，不代持/不代填凭证；真实 Provider = 一次显式、可记账、进 receipt 的授权动作。
- 首跑价值演示依赖的 C1-6 竞品对照已于 2026-10-01 完成（与 sub-01 同源，sub-01 升 `DONE_WITH_CONCERNS`）；价值证明不再阻塞，但仍须以实测数据陈述、不得夸大。
