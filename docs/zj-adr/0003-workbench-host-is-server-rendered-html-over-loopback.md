---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.ui-host.server-rendered-html-over-loopback
---

# ADR 0003：工作台宿主是经回环提供的服务端渲染 HTML

## Context

界面引用协议已经实现，但三个视图只是产出 HTML 字符串的纯函数，没有宿主承载它们。缺少宿主
使若干验收面无法判定：CSS 视口、指针事件、剪贴板与 DOM 焦点都只有真实渲染引擎能表达。

宿主形态因此不是外观选择，而是决定哪些验收面可达。它同时要服从既有的长期约束：本地优先、
依赖可退出、不新增 durable owner、不扩张常驻服务。

## Decision

工作台宿主是服务端渲染的 HTML，经本机回环地址上的只读 HTTP 入口提供。渲染保持为纯函数：
视图接收已脱敏的展示模型并返回带 `data-ui-ref` 属性的 HTML，不在浏览器内保存跨会话状态。

不引入前端框架、桌面外壳与打包链路。浏览器是查看器，不是产品运行时依赖；交付物是任何浏览器
都能打开的普通 HTML。

## Consequences

- 页面必须经 `http://127.0.0.1` 提供而非 `file://` 或 `data:` URL。后两者不是安全上下文，
  剪贴板能力在其中不存在，相关验收面将永远无法判定。
- 文档必须输出 viewport meta。缺少它时渲染引擎会回退到默认布局视口，窄视口断言会在测试通过
  的表象下失真。
- HTTP 入口按需启动、随会话结束退出，不是常驻服务，也不持有任何 canonical state。
- 视图仍不得直接读取 owner 存储；展示数据经 Control Plane façade 脱敏后传入。
- 浏览器不进入依赖表、不被分发、不被 pin。更换宿主形态需要新的 ADR，而不是在实现中悄悄替换。
