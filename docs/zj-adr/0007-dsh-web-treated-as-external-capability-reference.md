---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.dsh-web.external-capability-reference
---

# ADR 0007：dsh-web 作为外部能力参考而非可安装依赖

> 状态为 `accepted`：2026-09-19 经 `research/dsh-web-capability-fit`（结论报告 + PoC 设计 +
> sealed-ledger，证据锚点 commit `2629c3f` / tag v0.3.22）收敛确认；原始研究包与证据归档于
> `docs/plans/research/dsh-web-capability-fit/`。

## Context

在评估把外部 UI 能力源 `zhu1090093659/dsh-web`（Apache-2.0，TypeScript）吸纳进 ZWorkbench 时，
需要回答两个被长期架构约束框定的问题：

1. **吸纳单元的形态边界**——什么样的单元可以独立复用、独立禁用 / 移除，且不破坏
   CompositionOwner 的唯一 durable owner 地位。
2. **复用到底指什么**——复用的是运行时 / 聚合包，还是其契约、组合模式与测试方法。

固定 commit `2629c3f` 的源码事实显示：`dsh-session-id` 有独立 package、版本、Apache-2.0 许可、
host/client 两半区与包级测试（独立发布形态已证实）；但其 `apply()` 仍要求 `slots`/`locale`/
`sessions` 并依赖 DSH client SDK，脱离 DSH Web runtime 的嵌入能力**未证实且当前不成立**——它只是
host half，不是 runtime 无关组件。同时 ZWorkbench 当前仅证明 artifact-mode H1 bootstrap，无完整
DSH Web client runtime / browser slot / settings / remote API seam。

## Decision

- **dsh-web 是 ZWorkbench 的外部能力源与插件设计参考，不是可直接安装的产品依赖。**
- 最现实的收益来自**选择性抽取**其插件契约、slot/settings 组合思想、生命周期与测试方法，
  而非复用其运行时或聚合包（选项 C）。
- 与 C 并行：**继续自建 ZWorkbench UI**，把成熟模式转译为本项目的 SSR host + 现有 UI facade，
  而非引入 React / Cordis runtime（并行 D，风险最低）。
- 整包 `dsh-web-all` / 桌面客户端 / 创意工坊 / 远程访问平台**不吸纳**（选项 A 拒绝）。
- 薄 adapter/sidecar 接入真实 DSH plugin（选项 B1）**当前不成立**，留作未来重评——前提是已存在
  稳定的 DSH Web profile、client loader、slot/settings contract 与退出验证。

## Consequences

- CompositionOwner 仍是 run/attempt/event/effect/result/approval/replay/backup-restore 的唯一
  durable owner；任何外部 UI 单元只能通过显式 Host Capability Facade 读写允许的脱敏投影。
- 首个 PoC 只选 `session-id` 同等级的**只读 UI surface**，用 ZWorkbench 的 DTO + SSR / 现有
  `ui_view_model` facade 重写宿主接缝，**不把原包直接装进 ZWorkbench**。
- PoC 进入前必须另开 **product-execution scope gate**（按 AGENTS.md Step 1 拆分），本 ADR 不授权
  任何产品代码改动。
- **止损线**：若 PoC 需要引入 DSH Web client runtime、动态 loader、profile patch、远端 API、独立
  store/scheduler，或 adapter 开始拥有业务状态，则立即升级为 D 或停止投入，不再称为"薄 adapter"。
- **未闭合的 unknown**（诚实保留，不静默）：ZWorkbench-specific profile 联调、`clean dependency
  install` 下 dsh-web package 的 build/test、Cordis `dispose` 后资源归零、实际选用依赖树的完整
  许可证 / NOTICE / 版本 pin / 回滚。这些 unknown 不改变方向性判断，但阻止把 DSH 内测试通过写成
  ZWorkbench 已组合通过。
