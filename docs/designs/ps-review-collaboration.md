---
doc-kind: design
authority: supporting
axis: product-scenario
status: implemented
implementation-status: implemented
source: ../prds/r1-ui-reference-registry.md
source-id: prd-r1-ui-reference-registry
authority-id: design.review-collaboration
---

# 产品场景：评审协作（Human ↔ AI）与隐私边界

本页是 R1 + R2 的**产品场景实体**，描述 Human 与 AI 如何在不泄露产品数据、不形成执行通道的前提下协作评审，以及该能力如何被抽取为可复用 skill。

## Question

Human 与 Coding Agent 如何协作定位/评审界面元素，同时不把页面正文、Run 数据或凭证带入外部平台，且不把 UI 反馈变成 approval/execution 通道？

## Scope（协作边界）

- **零远端副作用**：评审模式默认关闭、显式启用；开启/悬停/选择/复制/链接定位/关闭全程零远端请求、零遥测；annotation 不改变 Owner state 与执行流。
- **脱敏边界**：token、URL、overlay、日志、浏览器持久存储与 clipboard 中，prompt / 运行标题 / 完整 Run ID / 原始事件 / Owner snapshot / 凭证 / cookie / approval bearer token / 输入框内容 / 本地绝对路径泄露阈值 = 0（用合成 canary 验证，真实凭证永不作测试输入）。
- **所有权**：UI 反馈模块只拥有界面引用元数据及短暂展示状态，不持有 Run/attempt/event/effect/approval/replay 状态；沿用 Workbench Control Plane façade 读取展示数据。
- **可复用抽取（R2）**：保留 R1 PRD 作为产品事实源，新增双 skill——`ui-reference-protocol`（设计/ratify 协议 profile）+ `ui-reference-runtime`（真实浏览器验收），二者以显式 **UI Reference Protocol Profile** 交接；skill 不成为新 UI 运行时 / 第二 owner。

## 关键设计约束

- 协议 profile 与运行时实现版本分离记录；缺失/冲突 profile → `unknown` / `HOLD`，不自行发明协议。
- 通用能力只抽取稳定设计/工作流原则；ZWorkbench 的 `ui-ref/v1` 字段白名单、三视图、CompositionOwner 约束等继续作为项目 profile，不升级为所有项目强制事实。
- 两个 skill 可独立安装、不依赖 ZWorkbench 源码；跨项目能力须经至少第二个结构不同的 fixture 验证，否则标 `unknown`（不能把 ZWorkbench 单项目通过标为通用已验证）。

## Status

IMPLEMENTED — R1 评审闭环 2026-09-13 Human 验收通过；R2 双 skill + 不依赖 ZWorkbench 模块的 `catalog-html` portability runtime 已落地，独立 fixture 取得协议/静态闭环/动态 session/真实浏览器交互/覆盖矩阵/unload teardown 证据；`ZWorkbench-specific profile` 联调标 `deferred/unknown`。

## Source map

- `../prds/r1-ui-reference-registry.md` §Solution、§Implementation Decisions（所有权 / 禁止数据 / 本地与副作用）。
- `../prds/r2-ui-reference-skills.md` §Solution、§Implementation Decisions、§Testing Decisions（Cross-project portability）、§Implementation status。

## Related authority

- 产品设计：[pd-ui-reference-system](pd-ui-reference-system.md)
- 体验路径：[ep-review-annotation-loop](ep-review-annotation-loop.md)
- 功能：[pf-ui-reference-skills](pf-ui-reference-skills.md)
