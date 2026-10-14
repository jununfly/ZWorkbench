---
adr: 0014
title: UI 真引擎测试默认加门——`ZW_UI_ENGINE=1` 显式开启
date: 2026-10-14
status: accepted
related: [0004, roadmap 1-4-1 / 1-4-2]
---

# ADR 0014：UI 真引擎测试默认加门——`ZW_UI_ENGINE=1` 显式开启

## Context

2026-10-14 排查"全量测试套件挂死"（roadmap 1-4-1）得到三层结论：

1. 1229 个测试中 **768 个（62%）是 `test_ui_*` 真引擎测试**（经 `tests/browser.py`
   的 CDP 客户端驱动本机 Chrome，ADR 0004 的证据通道）。在受限执行环境下引擎
   退化到 8~60 秒/测试，全量套件天然是小时级——9h53m 的后台运行不是死锁，
   是**无预算的慢**。
2. 等待原语是 `browser.py` 的 `_WebSocket.read`：涓流字节让每次 `recv` 都在
   10s socket 超时内返回，`while len(chunk) < count` 退化为无界慢读。
3. 两套件并发运行时，还会在 owner-db 锁/端口上互相争用，产生额外 error 与
   无限等待。

全量回归门禁（roadmap 1-4-3）需要一个**默认快、有界、退出码可信**的套件；
而真引擎证据（布局/焦点/剪贴板等，ADR 0004）在任何环境下都值得保留。

## Decision

- `tests/browser.py` 的 `browser()` 工厂在 `ZW_UI_ENGINE != 1` 时抛
  `unittest.SkipTest`（理由文本随 skip 呈现）。
- 单点改动覆盖全部真引擎测试（它们都经 `browser()` 取引擎），48 个
  `test_ui_*.py` 文件零改动；`chrome_available()` 语义不变（只回答
  "本机是否有引擎"）。
- 默认全量跑 = 非 ui 测试真实执行 + ui 测试全部 skip；`ZW_UI_ENGINE=1`
  显式开启后 ui 测试真实跑引擎。

## Consequences

- 默认全量套件回到分钟级、有界、退出码可信——1-4-3 的门禁成立。
- 真引擎证据不会被静默丢失：skip 计数可见、理由明确；需要 ui 证据时
  显式 `ZW_UI_ENGINE=1`（单文件/单测跑，避免全量串行慢磨）。
- 已验证：默认路径单测 0.5s skip；opt-in 路径单测 1.9s 真引擎通过。
- 风险：`ZW_UI_ENGINE=1` 全量串行仍是无界的慢——分桶/限时属于 1-4-3
  的后续工作，不在本 ADR 范围内。
