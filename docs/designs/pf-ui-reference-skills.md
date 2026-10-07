---
doc-kind: design
authority: supporting
axis: product-feature
status: implemented
implementation-status: implemented
source: ../prds/r2-ui-reference-skills.md
source-id: prd-r2-ui-reference-skills
authority-id: design.ui-reference-skills
---

# 产品功能：通用 UI 引用评审双 Skill

本页是 R2 的**产品功能实体**，沉淀「通用 UI 引用评审能力与协议／运行时双 Skill」这一可复用功能的能力面。

## Question

UI 引用评审能力如何从 ZWorkbench 产品抽取为可服务更多项目与 Coding Agent 的通用 skill，而不成为新运行时或第二 owner？

## Scope（功能面）

- **双 skill 职责分离**：
  - `ui-reference-protocol`（协议设计 skill）：识别问题边界、定义稳定语义身份、规定 manifest/token/深链接/迁移/脱敏/副作用合同，输出可被运行时 skill 消费的 **UI Reference Protocol Profile**；只定义协议与验证要求，不直接实现浏览器 overlay/面板/剪贴板/业务视图。
  - `ui-reference-runtime`（运行时实现 skill）：读取已确认 profile，在具体项目落地声明/manifest/DOM 标记/评审交互/解析/行为验证，完成「代码声明 → manifest → DOM → review session → token/link → manifest/源码定位」纵向闭环；通过项目已有 UI/Host/Control Plane/facade 接缝工作。
- **显式交接物**：协议 profile 是两 skill 的显式交接物，含协议身份/语义字段/生命周期/错误结果/信任边界/宿主能力假设/验收条件，不含项目动态业务数据。缺失或无法验证 profile → `unknown` / `HOLD`，不自行发明协议。
- **通用身份模型**：稳定机器引用 / 语义名称 / accessible name / 视觉样式 / 源码 provenance / mapping identity / build identity 分开建模。
- **可安装性**：两 skill 可独立安装、不依赖 ZWorkbench 源码/模块/目录；运行时 skill 消费项目 profile，不通过未声明相对路径 import 另一 skill 内部文件。
- **报告格式**：结构化结论至少区分 `implemented` / `target` / `unknown` / `HOLD` / `blocked` / `migrated` / `retired` / `incompatible` / `source-mismatch`，含 profile/artifact/environment identity、证据、未覆盖项、下一证据、owner、回滚路径。

## 关键边界

- 两个 skill 都不得创建新的 Agent loop / durable owner / scheduler / Provider 调用 / 业务执行入口；运行时只能通过项目已有 facade 读展示数据，不直接写 durable owner 或改 Run/effect/approval/replay 状态。
- 不复制 ZWorkbench 三视图验收矩阵；通用 skill 只要求每项目提供独立于 manifest 的语义覆盖矩阵，验证缺失声明不缩小分母。
- 跨项目可移植性不能只由 ZWorkbench 自身通过证明；须至少第二个结构不同的 fixture（否则标 `unknown`）。

## Status

IMPLEMENTED — 双 skill + `ui-reference-profile/v1` 校验器 + 严格运行时 evidence checker + 双 validator conformance corpus + 不依赖 ZWorkbench 的 `catalog-html` portability runtime 已落地；`ZWorkbench-specific profile` 联调标 `deferred/unknown`（不阻塞本阶段完成）。

## Source map

- `../prds/r2-ui-reference-skills.md` §Solution、§Implementation Decisions、§Testing Decisions（Protocol/Runtime skill、Cross-project portability）、§Implementation status、§Out of Scope。

## Related authority

- 产品设计：[pd-ui-reference-system](pd-ui-reference-system.md)
- 场景：[ps-review-collaboration](ps-review-collaboration.md)
- 功能：[pf-ui-reference-registry](pf-ui-reference-registry.md)
