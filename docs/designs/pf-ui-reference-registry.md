---
doc-kind: design
authority: supporting
axis: product-feature
status: implemented
implementation-status: accepted
source: ../prds/r1-ui-reference-registry.md
source-id: prd-r1-ui-reference-registry
authority-id: design.ui-reference-registry-feature
---

# 产品功能：界面引用注册表功能本体

本页是 R1 的**产品功能实体**，沉淀 UI 引用注册表这一功能的功能面（而非需求叙述或体验路径）。

## Question

界面引用注册表作为产品功能，对外暴露哪些稳定能力单元？

## Scope（功能面）

- **语义 ref 声明**：统一代码 helper `ui_ref` 声明语义元素（工作记录列表、列表项、当前工作、运行事实、证据、预检操作及结果等）；装饰容器/分隔线/图标内部节点不注册。
- **Manifest 生成与校验**：构建从声明生成确定性 manifest 与 build receipt（SHA-256），随本地 UI artifact 保存；只读本地查询接口按精确 `ui_map`/`build` identity 返回 manifest 或 `manifest-missing`，不联网下载历史版本。
- **源码定位合同**：manifest 含 schema 版本、build receipt identity、视图归属、引用声明及迁移信息；声明来源含仓库相对路径 + 符号 + 源码 digest；解析前验证源码内容 digest，不匹配返回 `source-mismatch`。
- **Token v1**：版本化 `ui-ref/v1`，≤1024 字节，固定白名单（protocol / ref / ui_map / build / viewport / state / instance），拒绝重复键/未知键/类型错误/超限/未知版本。
- **深链接**：本地工作台入口 + `ui_ref` / `ui_map` 两个定位参数，纯 UI 导航，不携业务路由/状态恢复/执行参数。
- **引用生命周期**：视觉重排不改 ref；语义变化建新 ref + alias / replaced-by / retired；当前映射版本须保留对紧邻上一发布版本的显式迁移声明。
- **评审模式 UI**：高亮层（不接收指针事件）、停靠式侧栏面板、锁定目标、复制 token、键盘可达、焦点恢复、禁用/卸载释放资源。

## 验收矩阵（功能覆盖）

固定语义覆盖矩阵（首页 / 任务详情 / 记录视图 × 必测语义单元 × 390px/1280px × 正常/评审两模式）作为产品验收范围；`conditional` 单元可豁免，`visible`/`expandable` 缺席一律计 gap；隐藏单元定位返回 `unavailable`，与 `unknown-reference` 区分。

## Status

IMPLEMENTED（accepted 2026-09-13）；模块见 `src/zworkbench/ui_*.py`，验证入口见 Repository README。

## Source map

- `../prds/r1-ui-reference-registry.md` §User Stories、§Implementation Decisions、§Token v1 固定合同、§Manifest 获取与源码定位合同、§固定语义覆盖矩阵与完成门槛。

## Related authority

- 产品设计：[pd-ui-reference-system](pd-ui-reference-system.md)
- 体验路径：[ep-review-annotation-loop](ep-review-annotation-loop.md)
- 功能：[pf-ui-reference-skills](pf-ui-reference-skills.md)
