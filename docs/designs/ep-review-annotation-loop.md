---
doc-kind: design
authority: supporting
axis: experience-path
status: implemented
implementation-status: accepted
source: ../prds/r1-ui-reference-registry.md
source-id: prd-r1-ui-reference-registry
authority-id: design.review-annotation-loop
---

# 体验路径：评审标注闭环（Human ↔ AI 指认界面元素）

本页是 R1 评审标注能力的**体验路径实体**，描述从 Human 标注到 AI 解析回代码的端到端闭环。

## Question

Human 与 AI 如何通过同一构建版本的 UI Reference Manifest 准确定位同一个语义元素，且过程零泄露、零业务副作用？

## Scope（闭环步骤）

1. Human 显式启用本地评审模式（默认关闭）。
2. 悬停/聚焦预览 → 面板「锁定目标」按钮显式选择（绝不向业务元素派发点击）。
3. Human 主动复制脱敏 feedback token（`ui-ref/v1`，≤1024 字节，只含稳定引用 + mapping/build identity + 视口/展示状态 + 必要脱敏上下文）。
4. AI 经项目本地工具读取同一 manifest 产物，按精确 `ui_map` / `build` identity 解析 token → 定位代码声明（仓库相对路径 + 符号 + 源码 digest）。
5. 深链接：携带 `ui_ref` + `ui_map` 两个定位参数，纯 UI 导航定位已存在语义，不恢复 Run / 不启动任务 / 不触发预检 / 不 apply。

## 失败语义（显式，无猜测性回退）

- 未开启评审模式跟随链接 → 完成纯定位 + 提示需显式进入，绝不静默开启。
- 动态重复项无 handle → `ambiguous`（不默认取首项）；实例卸载 → `unavailable`；跨会话 → `expired`（不伪称找到原业务记录）。
- 源码内容 digest 不匹配 → `source-mismatch`（保留历史来源提示，不宣称当前精确命中）。
- 缺失指定 manifest → `manifest-missing`；旧版本无显式迁移记录 → `incompatible`（不得用当前 manifest 静默替代旧 manifest）。

## Boundaries

- 高亮层不接收指针事件；普通点击 / Enter / Space 保留业务行为；复制必须由用户发起，失败可见、不回显宿主错误、不自动重试。
- 零远端请求 / 零遥测；annotation 不改变 Owner state 与执行流（非 approval/execution 通道）。
- 禁用/卸载释放 overlay、监听器与后台资源，保留正常焦点与无障碍语义。

## Status

IMPLEMENTED — 真实引擎（CDP）证据：`tests/test_ui_focus_order.py`、`test_ui_pointer_passthrough.py`、`test_ui_clipboard.py`、`test_ui_focus_restore.py`、`test_ui_review_highlight.py`、`test_ui_deep_link_negative.py`、`test_ui_redaction_host.py`、`test_ui_no_side_effects.py` 等。

## Source map

- `../prds/r1-ui-reference-registry.md` §Solution、§Token v1 固定合同、§Manifest 获取与源码定位合同、§Testing Decisions（Token 与深链接 / 选择与焦点 / 脱敏 / 本地与副作用 / 退出）。

## Related authority

- 产品设计：[pd-ui-reference-system](pd-ui-reference-system.md)
- 协同场景：[ps-review-collaboration](ps-review-collaboration.md)
- [ADR 0005 评审模式最小行为层](../zj-adr/0005-review-mode-carries-a-minimal-behaviour-layer.md)
