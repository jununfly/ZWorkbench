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
- **层二（待 zj 确认 blast radius 后执行）**：从产品代码剥离 R1 实现层——`src/zworkbench` 的 `ui_ref` / `ui_token` / `ui_manifest` / `ui_build` / `ui_runtime` / `ui_review` / `ui_script` / `ui_matrix` / `ui_view_model` / `ui_declare` 及 `ui_home` / `ui_host` / `ui_task_detail` / `ui_record_view` 中的 R1 专用接缝，以及 `cli.py` 的 `ui-ref` / `ui-host` / `ui-build` 子命令与 `__init__.py` 的 `ui_*` 重导出。

> ⚠️ 关键事实：R1 实现层**就是** ZWorkbench 本地三视图 UI 子系统本身（首页/任务详情/记录视图 + 评审模式 + token/深链 + 构建/manifest + 矩阵），其测试套件即 `tests/test_ui_*.py` 整体。层二等于端掉整个本地 UI 表面，blast radius 远大于"删两个目录"，须 zj 单独确认后再做，且必须按 TDD 切片 + 验证推进，不得一次性盲删。

## Consequences

- 设计实体与设计文档不再声称 R1「implemented / accepted」，改标 `retired` 并指向本 ADR。
- conformance 测试套件不再断言 `skills/` 包存在，避免测试红。
- 层一为纯减法，提交即稳定；层二为产品重构，未执行前 R1 运行代码保持原状——此时文档已 `retired` 但代码暂留，属**已知中间态**，待层二闭合后消除。
- 不触碰 `evaluation/evidence/` 历史证据树（仅删除专门的 portability fixture 目录）。
- 不删除 ZAgentic 侧新 skill；本 ADR 仅影响 ZWorkbench 仓库。

## Status

ACCEPTED 2026-10-24（zj，grilling Q5/Q6/Q8=B1）。层一已落地，层二待 blast-radius 确认。
