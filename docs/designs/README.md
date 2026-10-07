---
doc-kind: design
authority: supporting
---

# 设计文档

本目录保存长期维护的产品设计与实现规格。产品目标和范围仍以 `docs/prds/` 为准；
稳定的信息架构和 ownership 仍以 `docs/architecture/` 为准；本目录不保存单次开发进度、
截图 diff 或机器生成的历史 evidence。

## 产品设计 product-design（`pd-`）

- [界面引用注册表与本地评审标注系统](pd-ui-reference-system.md) — R1 评审标注协议、manifest/token/深链接/生命周期/所有权边界
- [可交互完整工作台 Web-UI](pd-interactive-workbench.md) — IA 方向、交互深度、宿主边界、D1–D4 决策
- [首跑与 onboarding](pd-first-run-onboarding.md) — 零配置首跑、只读 doctor 自检、价值演示缝合

## 体验路径 experience-path（`ep-`）

- [评审标注闭环](ep-review-annotation-loop.md) — Human 标注 → 脱敏 token → AI 解析定位代码 的端到端闭环
- [首跑旅程](ep-first-run-journey.md) — `pip install` → `run --prompt` → loopback UI 见 recorded view 默认路径
- [交互写 seam 旅程](ep-write-seam-journey.md) — UI 经宿主注入 facade 触发真实写入/审批/reconcile，只读宿主 404

## 产品场景 product-scenario（`ps-`）

- [solo 真实可用](ps-solo-real-provider.md) — 三层 AND 门、最小切片 S0–S4、H7/H8 deferred
- [评审协作与隐私边界](ps-review-collaboration.md) — Human↔AI 协作零泄露、双 skill 抽取
- [unknown → safe-stop 失败关闭语义](ps-safe-stop-unknown.md) — 未知即安全停止、写边界 fail-closed、Provider-side 退出记账

## 产品功能 product-feature（`pf-`）

- [界面引用注册表功能本体](pf-ui-reference-registry.md) — ref/manifest/token/生命周期/评审模式 UI 功能面
- [完整工作台功能目录 F1–F19](pf-workbench-features.md) — 原子功能清单与交付状态
- [通用 UI 引用评审双 Skill](pf-ui-reference-skills.md) — protocol + runtime 双 skill 能力面

## 既有实现规格

- [Issue #1：Workbench UI 实现规格](issue-1-workbench-ui-implementation.md)

参考原型和其他大型设计资产放在对应文档的 `assets/` 子目录中，并通过文档链接访问。
