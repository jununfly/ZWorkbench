---
doc-kind: design
authority: supporting
axis: product-design
status: implemented
implementation-status: accepted
source: ../prds/r1-ui-reference-registry.md
source-id: prd-r1-ui-reference-registry
authority-id: design.ui-reference-system
---

# 产品设计：界面引用注册表与本地评审标注系统

本页是 R1「界面引用注册表与本地评审标注模式」的**产品设计实体**（durable 设计结论），从 PRD 抽取协议、运行时边界与验收合同，不重复需求级叙述。

## Question

Human 与 AI 在评审工作台时，如何在不维护易漂移的 docs 元素映射表的前提下，准确定位同一个界面元素？

## Scope

覆盖本地评审标注模式的**产品设计**：

- 代码统一 helper 声明 `ui_ref` → 构建生成并校验 UI Reference Manifest（派生产物，非第二份手工注册表）。
- 评审模式默认关闭、显式启用；悬停/选择显示边框、中文语义名、稳定引用；主动复制脱敏 token。
- Token v1 固定白名单（`ui-ref/v1`，≤1024 字节，字段外信息零进入）。
- 深链接仅携带引用 + mapping identity，定位已存在界面语义，不恢复/执行业务状态。
- 引用生命周期：视觉重排不改 ref；语义变化建新 ref 并声明 alias / replaced-by / retired；迁移必须显结果。
- 评审模式状态机、三视图语义单元声明、安全负向断言。

## Boundaries（不覆盖）

- 不创建第二份 durable owner、不修改 Owner schema、不引入浏览器 scheduler / Worker/Provider 写操作。
- token 不得作为认证、approval、业务状态恢复、recorded/simulated/live replay 或任务执行入口。
- 远端反馈平台、截图/录屏、遥测、自动发布 Issue 不在范围内。

## Design decisions（durable）

- **单一来源**：统一代码 helper 声明；manifest 是声明派生产物，docs 只说明协议/命名/安全/迁移规则，不列元素清单。
- **字段分离**：稳定机器引用、中文语义名、无障碍名称分别维护；文案/布局变化不改变语义未变的引用。
- **动态实例**：Run ID/标题/载荷不拼入结构引用；实例用当前评审会话内随机分配的 instance handle（内存保存、非 durable entity）；卸载 `unavailable`、跨会话 `expired`、无 handle 重复结构 `ambiguous`。
- **真实 DOM**：运行时渲染 `data-ui-ref`，标注模式从真实元素读取并核对 manifest；未登记节点不生成看似有效的反馈引用。
- **禁止数据**：prompt、Run 标题、完整 Run ID、原始事件、Owner snapshot、凭证、cookie、approval bearer token、输入框内容、本地绝对路径不得进入 token/overlay/链接。
- **所有权**：本模块只拥有界面引用元数据及短暂展示状态，不持有 Run/attempt/event/effect/approval/replay 状态；沿用 Workbench Control Plane façade。

## Status

IMPLEMENTED — 2026-09-13 Human 在真实宿主验收通过（A–F 六项人工验收全过，四项缺陷已修复带回归）。实现证据见 `src/zworkbench/ui_*.py`、`tests/test_ui_*.py`；ADR 0003/0005/0006 落地宿主边界与构建身份。

## Source map

- `../prds/r1-ui-reference-registry.md` §Solution、§Implementation Decisions、§Token v1 固定合同、§Manifest 获取与源码定位合同、§Testing Decisions、§Out of Scope、§Implementation status。

## Related authority

- [工作台用户界面架构](../architecture/ta-workbench-user-surface.md)
- [唯一 durable owner ADR](../zj-adr/0001-composition-owner-is-the-unique-durable-owner.md)
- [宿主只读边界 ADR](../zj-adr/0003-workbench-host-is-server-rendered-html-over-loopback.md)
- [评审模式最小行为层 ADR](../zj-adr/0005-review-mode-carries-a-minimal-behaviour-layer.md)
- [单构建身份 ADR](../zj-adr/0006-one-build-identity-for-served-manifests.md)
- 协同能力见 [pf-ui-reference-skills](pf-ui-reference-skills.md)、[ps-review-collaboration](ps-review-collaboration.md)
