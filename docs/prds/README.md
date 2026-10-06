---
doc-kind: prd-index
authority: supporting
---

# Product requirements

本目录保存产品规格、验收门槛和实现状态。尚未实现或尚未由 owner-backed 证据证明的目标能力必须标为 `target` 或 `unknown`，不能当作实现事实。

- [Issue #1：Owner-backed Workbench UI and capability integration](issue-1-workbench-ui.md) — 只读三视图 + 交互写 seam 已交付；status: implemented / implementation-status: accepted（live/真实 Provider/主工作区写入按设计默认 deny）
- [R1：界面引用注册表与本地评审标注模式](r1-ui-reference-registry.md) — 代码生成 manifest、脱敏反馈 token、引用迁移与验收合同；implementation accepted：结构合同与四项宿主交互面均已验证，但 R1 主规格仍须独立验收。
- [R2：通用 UI 引用评审能力与协议／运行时双 Skill](r2-ui-reference-skills.md) — 保留 R1 产品规格，抽取协议设计与运行时实现两个可复用 skill；accepted / complete，ZWorkbench-specific profile 联调 deferred/unknown。
- [R3：真实可用路线图](r3-real-usability-roadmap.md) — 从 Codex-only 本地只读回退基线到"真实可用"的 stage 缺口、最小切片（S0–S4）与产品可用判定（三层判据 AND 门）；H6–H8 scope 已收敛（2026-09-27），H7/H8 标 deferred-until-demand；status: in-progress / implementation-status: partial（S2/S4/真实 Ark 读路径已落地，见 roadmap 1-7/1-9/1-10；H6-full/H7/H8 仍 target）。
- [R4：首跑与 onboarding 设计](r4-onboarding-first-run.md) — 主语分轨（验收轨 zj 机械判定 / UX 目标轨非判据）、最小形态 `run --prompt`、`doctor` 只读自检契约、`next_steps` 缝合、端到端回归脚本验收线；status: target / implementation-status: unknown。
