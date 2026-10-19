<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap-zw-go-1to100.json` | 最后更新: 2026-10-19 13:11:15

[~][X+] 1. ZW Go/Electron 工作台 1→100 收尾
    ├── [~][X+] 1-5. 分发与安装
    │   ├── [~][X+] 1-5-1. Developer ID + 公证真跑（NOTARIZE 门控已在，只差证书）
    │   ... 该层还有 3 个兄弟，1 个 in_progress ▸
    ... 该层还有 6 个兄弟，0 个 in_progress ▸

### 当前施工：1-5-1. Developer ID + 公证真跑（NOTARIZE 门控已在，只差证书）

门控 NOTARIZE=1 + DEV_ID_APP 已在 app/scripts/build-desktop.sh；README 明示「公证本身尚未真跑过（缺 Developer ID 证书，/年）」。自用场景非必须。

**决策：**
- Q: Developer ID 公证是否现在做？ → 暂缓：需付费 Developer ID $99/年，自用非必须；NOTARIZE 门控已就绪，待 zj 决定是否购证
- Q: 1-5-1 维持现状如何落地？ → 维持现状：不购 Developer ID 证书（$99/年，自用非必须）、不跑公证；NOTARIZE 门控（build-desktop.sh 1b 节）保留待未来激活。节点以 in_progress(parked) 持续可见，待购证再推进 (本切片只改 roadmap 元数据，不动项目代码/证书/README)

### 下一步可开工（ready 前 3）

- 1-7. 产品定位复核（R4 风险：ES 内容是否稀释 ZW 编码证据核心） [ ]
<!-- ROADMAP_SECTION_END -->
