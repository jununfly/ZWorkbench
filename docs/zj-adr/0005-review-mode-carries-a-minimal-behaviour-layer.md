---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.ui-host.review-mode-behaviour-layer
---

# ADR 0005：评审模式携带一层最小行为脚本

> 状态为 `accepted`：实现与证据齐备（键盘计划声明的 ArrowUp/ArrowDown 已在页面层接通，
> 见 `tests/test_ui_arrow_keys.py`；全部评审/宿主相关套件回归通过），并经 Human 在决策前沿
> 确认接受。本决定现为长期约束：新增评审行为必须先落在状态机上，页面层只镜像决策。

## Context

ADR 0003 把宿主定为服务端渲染 HTML，并排除前端框架、桌面外壳与打包链路。该决定覆盖了视口、
样式、overlay 语义与指针穿透四类可由静态文档加真实引擎判定的面。

但 PRD 要求的两个面发生在页面内部，服务端无从表达：向剪贴板写入并在被拒绝时让失败**可见**，
以及面板关闭后焦点**可见地**落回。没有页面内行为，这两项不是"暂未验证"，而是构造上不可判定
——`HOST_UNKNOWNS` 将永久保留两项，而结构覆盖满格会被误读为验收通过。

## Decision

评审模式加载一层最小行为脚本，仅此一层。它镜像 `ReviewMode` 已经做出的决策，不新增决策。

脚本的硬边界：

- 只在评审模式下作为独立资源提供；普通模式既不链接它，宿主也不提供该路由。
- 不发起任何网络请求、不做持久化、不上报遥测、不触发任何业务动作。
- 不铸造 token。服务端按视口档各渲染一份由 `ui_token` 生成的 token，脚本只按计算出的
  `--viewport-class` 取用。
- 不保存跨会话状态；面板 identity、条目与键盘计划仍由服务端从状态机渲染。

## Consequences

- 行为契约有两处表达：`ui_review.py` 的状态机与 `ui_script.py` 的页面层。状态机是事实源；
  脚本若自造判断，两者会分叉而各自的测试都保持绿色。新增评审行为必须先落在状态机上。
- `clipboard-failure-visible` 与 `focus-restore-on-close` 因此可判定，证据分别为
  `tests/test_ui_clipboard.py` 与 `tests/test_ui_focus_restore.py`。
- 文档不再是纯声明式：两模式对照测试必须逐项减去评审模式新增的每个子树（overlay、评审入口、
  面板、脚本标签），新增一处未登记即转红。
- 评审面板的 token 不再携带 instance handle。handle 属于铸造它的 `ReviewMode` 会话，而该会话
  随响应结束，服务出去的 handle 对任何评审者都会解析为 expired。
- 脚本不进入依赖表、不被打包、不引入构建步骤。若将来需要框架或构建链路，需要新的 ADR 取代
  ADR 0003，而不是在本层逐步扩张。
