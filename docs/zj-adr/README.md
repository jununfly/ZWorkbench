---
doc-kind: adr
authority: supporting
---

# ZWorkbench ADR

ADR（Architecture Decision Record）记录会长期约束系统结构的选择。它仅在
`zj-grilling` 的决策前沿完成、Human 明确确认共同理解后创建或接受；尚未确认的 ADR 标记为
`proposed`。

每条 ADR 保持简短，只记录稳定的上下文、决定、理由与必要后果。语义不可改写：实质变化以新的
ADR 表达并明确 `supersedes ADR-NNNN`；旧 ADR 以 `superseded by ADR-NNNN` 指向新决定并保留
历史语义。链接或排版等非语义错误可以更正。

ADR 不保留 grilling 问题、候选项、反例、测量或原始证据；它只表达确认后的稳定决定及其理由。

## 索引

- [ADR 0001：CompositionOwner 是唯一 durable owner](0001-composition-owner-is-the-unique-durable-owner.md)
- [ADR 0002：映射版本只摘要引用语义](0002-ui-map-digests-reference-semantics-only.md)
- [ADR 0003：工作台宿主是经回环提供的服务端渲染 HTML](0003-workbench-host-is-server-rendered-html-over-loopback.md)
