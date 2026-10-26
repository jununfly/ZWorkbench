---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.ui-reference.retirement
retires:
  - design.ui-reference-system
  - design.ui-reference-registry-feature
  - design.ui-reference-skills
  - package skills/ui-reference-protocol
  - package skills/ui-reference-runtime
---

# ADR 0018：退役 R1 UI Reference System 与两个 skill 包

## Context

R1「界面引用注册表与本地评审标注系统」于 2026-09-13 由 Human 在真实宿主验收（A–F 六项人工验收全过，四项缺陷已修复带回归），原 PRD（`prd-r1-ui-reference-registry`）已于 2026-10-13 退役，内容沉淀为设计实体 `pd-ui-reference-system.md` / `pf-ui-reference-registry.md`。R2「通用 UI 引用评审双 Skill」将两个 skill 包（`ui-reference-protocol`、`ui-reference-runtime`）作为可安装复用资产沉淀于仓库根 `skills/`，由 conformance 测试 `tests/test_ui_reference_*` + `tests/ui_reference_support.py` 与 `evaluation/runner/run_ui_reference_skill_lifecycle.py` 守护。

2026-10-24 经 grilling 决策（Q5/Q6/Q8 = B1 全退役）：zj 确认 R1 功能已无用处；UI 编写已转到 ZAgentic 新建的写 UI skills，ZWorkbench 本地的 UI 引用评审体系不再需要。据此决定项目级退役 R1 及其双 skill 包。

## Decision

退役以下资产：

- 设计实体：`pd-ui-reference-system.md`、`pf-ui-reference-registry.md`、`pf-ui-reference-skills.md`（含 `ps-review-collaboration.md` 中对应的 R2 抽取条款）。
- 仓库根 `skills/ui-reference-protocol` 与 `skills/ui-reference-runtime` 两个 skill 包（`git rm`）。
- 配套 conformance 测试与 eval 资产：`tests/test_ui_reference_skill_installation.py`、`tests/test_ui_reference_skill_lifecycle.py`、`tests/test_ui_reference_portability.py`、`tests/test_ui_reference_runtime_skill.py`、`tests/test_ui_reference_profile.py`、`tests/ui_reference_support.py`、`evaluation/runner/run_ui_reference_skill_lifecycle.py`、`evaluation/fixtures/ui_reference_portability/`。
- 未跟踪本地草稿 `skills-outputs/`（物理删除，从未进 git）。

执行分两层，明确隔离 blast radius：

- **层一（已执行，纯减法、可提交即稳定）**：上述 `skills/`、`skills-outputs/`、conformance 测试、eval 资产删除，设计文档与设计实体改标 `retired`。**不改动产品运行代码**——`src/zworkbench/ui_*.py` 维持原状。
- **层二（已执行 2026-10-26，zj 拍板「全删 + 5 切片提交」）**：从产品代码剥离 R1 实现层——`src/zworkbench` 的 `ui_ref` / `ui_token` / `ui_manifest` / `ui_build` / `ui_runtime` / `ui_review` / `ui_script` / `ui_matrix` / `ui_view_model` / `ui_declare` 及 `ui_home` / `ui_host` / `ui_task_detail` / `ui_record_view` 中的 R1 专用接缝，以及 `cli.py` 的 `ui-ref` / `ui-host` / `ui-build` 子命令与 `__init__.py` 的 `ui_*` 重导出。

### 层二实测 blast radius（2026-10-26，非估算）

| 面 | 规模 | 耦合结论 |
|---|---|---|
| 生产模块 | 20 个 `ui_*.py` / 8206 行 | 封闭簇，仅互相依赖 |
| 非 ui 消费者 | **仅 2 个文件**：`cli.py`（9 模块 + 4 子命令 + `run --open` 钩子 + 5 handler）、`__init__.py`（8 组 / 38 条重导出） | 耦合面极小 |
| 测试 | 43 / 91 个 `test_ui_*.py`（占 Python 套件 47%）+ `test_cli_zero_config_run.py` 2 个 `--open` 用例 + 1 个 `next_steps` 断言（5 项 → 4 项） | 全属 R1 实现层 |
| Go app / Electron / CI | **零命中** | 剥离不动产品运行面 |
| 证据 / owner / receipt 层 | `ui_map` / `review_token` **零命中** | ADR 0002 的摘要语义完全封闭在被删的 manifest 体系内，删除不动摇证据核心 |
| `tests/browser.py`（ADR 0004 CDP 通道） | 剥离后零消费者 | **初判保留 → 2026-10-26 改判删除**（见下） |

执行切片（每片独立提交、独立验证，全绿推进）：

| 切片 | 内容 | 提交 |
|---|---|---|
| S1 | CLI 命令面下线：4 子命令 + `run --open` + 死代码（`threading` / `LOOPBACK*` / `_announce`） | `80a94fc` |
| S2 | 退役 43 个 `test_ui_*.py` | `d444601` |
| S3 | 撤掉 `__init__.py` 的 R1 重导出（266→167 行，`__all__` 110→72） | `a7bf1a5` |
| S4 | 删除 20 个 `ui_*.py` + 新增退役守卫 `tests/test_r1_layer2_retirement.py` | `528fa9f` |
| S5 | 文档收尾（README / AGENTS.md / tests/README.md / desktop/README.md）与本 ADR 闭合 | 见 S5 提交 |

TDD 口径：S1 与 S4 均先写「必须不存在」的断言跑红、再删码转绿；S4 的守卫测试是层二唯一的自动化证据——任何 `ui_*.py` 回流、顶层重导出恢复或 CLI 宿主命令加回来都会立刻变红。

验证：非 ui 套件剥离前后基线不变（46 文件 / 484 用例全绿）；最终官方规范命令 `python -m unittest discover -s tests -p "test_*.py"` 得 **502 tests / ~45s / skipped=1 / OK**（相对上一基线 1261 tests 减少的正是 43 个 `test_ui_*.py`，skipped 从 110→1 同源）。

> ⚠️ 关键事实：R1 实现层**就是** ZWorkbench 本地三视图 UI 子系统本身（首页/任务详情/记录视图 + 评审模式 + token/深链 + 构建/manifest + 矩阵），其测试套件即 `tests/test_ui_*.py` 整体。层二等于端掉整个本地 UI 表面，blast radius 远大于"删两个目录"，须 zj 单独确认后再做，且必须按 TDD 切片 + 验证推进，不得一次性盲删。

## Follow-up：`tests/browser.py` 改判为退役（2026-10-26）

层二收口时把该模块判为「方法论资产，保留」。两日后复核推翻该判断，理由不是"没人用"，而是
**它服务的宿主本体已不存在**：该模块是为 Python 侧服务端渲染 HTML 宿主（ADR 0003）写的 CDP
取证通道，而该宿主已被 Go 全 pivot（ADR 0015）+ React 前端取代，Python 侧只剩 7 个 CLI 子命令；
将来要做真引擎 e2e，承载面是 Go/Electron 侧，不会跨语言复用 Python 客户端。

保留成本不是"占用空间"——它不进产品构建、运行成本为零——而是**未被任何测试执行的代码会静默
腐烂**（升级 Chrome 后它看起来还在，实际可能已坏，这比缺失更危险），以及每次读
`tests/README.md` 都要重新判断一次"这玩意儿还有用吗"的认知税。按「有消费者的能力才配留在产品
树里」删除 336 行，同时把 4 条 CDP 顺序规则沉淀进 ADR 0004 的「实现附注」——**方法论由 ADR
承载，不靠代码承载**。

判据自检（可复核，非估算）：`git grep`（含隐藏目录）零代码命中，仅文档提及；`.github/` 只有
`web-build.yml`，零 CI 命中；官方规范命令全量仍 502 tests / OK（删的是支撑模块不是用例）。
验证口径：`tests/browser.py` 与 `ZW_UI_ENGINE` 门控一并删除后，Python 套件基线**不变**。

## Consequences

- 设计实体与设计文档不再声称 R1「implemented / accepted」，改标 `retired` 并指向本 ADR。
- conformance 测试套件不再断言 `skills/` 包存在，避免测试红。
- 层一为纯减法，提交即稳定；层二为产品重构，已按 TDD 切片执行完毕（见上表）——**「文档已 `retired` 但代码暂留」的已知中间态已于 2026-10-26 消除**。
- 不触碰 `evaluation/evidence/` 历史证据树（仅删除专门的 portability fixture 目录）。
- 不删除 ZAgentic 侧新 skill；本 ADR 仅影响 ZWorkbench 仓库。
- **真引擎证据通道当前处于「方法论在、实现在缺」的显式状态**：口径与 4 条顺序规则由 ADR 0004
  承接，重建面在 Go/Electron 侧（未立项）。此后任何涉及布局/焦点/剪贴板/指针穿透的验收面，
  在重建之前一律报 `unknown`——不得以「结构覆盖满格」替代引擎证据（ADR 0004 原始动机）。

## Status

ACCEPTED 2026-10-24（zj，grilling Q5/Q6/Q8=B1）。**层一 + 层二均已落地，退役闭环。**

- 层一：2026-10-24 执行（`skills/` 两包、`skills-outputs/`、conformance 测试、eval 资产删除，设计实体改标 `retired`）。
- 层二：2026-10-26 执行（zj 拍板「全删 + 5 切片提交」）。8206 行 `ui_*.py`、4 个 CLI 子命令、`run --open`、43 个 `test_ui_*.py` 全部下线；新增 `tests/test_r1_layer2_retirement.py` 守卫不回流。官方规范命令全量 502 tests / OK。
- 层二附：2026-10-26 同日复核 `tests/browser.py`，由「保留」**改判删除**（zj 拍板 A 方案，理由见上节）；ADR 0004 增「实现附注」承接 4 条 CDP 顺序规则与重建口径，方法论不随代码消失。
