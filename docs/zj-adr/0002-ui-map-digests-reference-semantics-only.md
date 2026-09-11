---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.ui-reference.semantic-only-mapping-version
---

# ADR 0002：映射版本只摘要引用语义

## Context

界面语义元素通过代码声明获得稳定引用，构建派生出 UI Reference Manifest，并以映射版本
`ui_map` 标识一次引用语义的快照。Human 复制的反馈 token 钉在某个 `ui_map` 上，AI 依据它回到
代码声明。

因此凡是进入该摘要的字段，都具备一种能力：它一变，所有历史 token 立即失效。源码内容 digest、
构建 receipt、无障碍名称和界面文案都会随重构、改字甚至改注释而变动，而这些变动并未移动任何
界面语义。若它们参与摘要，反馈的有效期将短于一次日常提交。

## Decision

`ui_map` 只摘要引用语义：引用名、中文语义名、元素类型、视图归属、父级关系与生命周期元数据
（别名、退役、替代目标）。源码锚点、构建 receipt、无障碍名称与上一版本指针记录在 manifest 中
但不参与摘要。

引用身份的变更必须显式声明：改名为 alias，解析为 `migrated`；语义替换为退役加替代目标，解析为
`retired` 且不表述为同一身份。兼容窗口只覆盖紧邻上一版本，且窗口内解析必须出示旧 manifest
实物核对。

## Consequences

- 视觉重排、文案与无障碍名称调整不移动引用身份；语义改变必须新建引用并声明迁移。
- 源码锚点仍保存在 manifest 中用于定位代码；内容不符时报告 `source-mismatch`，不宣称精确命中。
- 别名自指、别名与在用引用冲突、两个声明争夺同一旧名、替代目标缺失或成环，一律在构建期拒绝。
- 当前 manifest 不得静默替代它无法证明的历史版本；缺少旧 manifest 即 `incompatible`。
- 任何向摘要新增字段的提议，必须先说明该字段变动时作废全部历史反馈是可接受的。
