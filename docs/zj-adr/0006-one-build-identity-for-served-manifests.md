---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.ui-host.one-build-identity
---

# ADR 0006：宿主服务的 manifest 只有一个 build 身份——全树 receipt

> 状态为 `accepted`：2026-09-13 经 Human 在决策前沿确认（Q1：receipt 为唯一事实源；
> Q2：宿主启动时现算 receipt）。

## Context

PRD 的 token 合同写明 `build` 是"源码及构建输入 receipt 的 SHA-256"，`build_ui_artifacts`
也按此把 5 个 ROOT_SOURCES 的全树摘要作为唯一 build 身份——共享 helper 的改动必须使所有
受影响视图的旧 token 失效。但宿主服务的各视图 manifest 用默认值：`build` 等于本模块文件
的内容摘要。结果是同一个工作树产出两套 build 身份：评审者复制的 token 携带模块摘要，本地
store 按 receipt 摘要寻址，`ui-ref resolve` 对服务出的 token 返回 `manifest-missing`
（验收中实测复现）。"同一构建版本"这个承诺存在两套算法时，它不再是承诺。

## Decision

- build 身份的唯一事实源是全树 receipt。模块内容摘要降级为 `source.content_digest`，
  只用于代码定位校验（`source-mismatch`），不再充当 build 身份。
- 宿主启动时用同一个 `build_receipt()` 对工作树现算一次 receipt，服务全程以该 digest
  生成各视图 manifest。工作树一致时，服务出的 token 与 `build_ui_artifacts` 产出的
  store 精确对齐，`resolve` 可达。
- 宿主不消费 store、不新增启动参数；store 仍是 CLI 查询侧的入口。

## Consequences

- 宿主启动开始读取声明源文件；源不可读在启动点 fail loud，而不是服务出无法对齐的身份。
- 任何 ROOT_SOURCES 改动（含 `ui_ref.py` 共享 helper）使所有已复制 token 的 build 过期
  ——这是设计而非事故：它强制"同一构建版本"按整棵树理解。
- per-module 摘要仍出现在 manifest 的 `source.content_digest` 中，职责单一：定位校验。
- 连贯性有测试：服务出的 token 身份必须能被 receipt 构建的 store resolve。
