<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap-zw-electron-es-tab.json` | 最后更新: 2026-10-14 19:29:08

[~][X+] 1. ZW → Electron 客户端 + ES 常驻 Tab
    ├── [ ][X+] 1-1. Phase 1 — Electron 化 ZW 客户端（薄壳，零 UI 重写）
    │   ├── [~][X+] 1-1-3. 1.3 electron-builder 打包 macOS/Windows（补 C04/C34 缺口）
    │   ... 该层还有 3 个兄弟，0 个 in_progress ▸
    ... 该层还有 4 个兄弟，1 个 in_progress ▸
<details><summary>阻塞链：5 个节点被阻塞</summary>

- 1-2-1. 2.1 常驻 tab 容器 + 路由（先空占位） ← e5: 1-1-3. 1.3 electron-builder 打包 macOS/Windows（补 C04/C34 缺口） [~]
- 1-2-2. 2.2 首个 ES 风格 tab 原型（C08 个股分级研究 / C07 行情总览） ← e6: 1-2-1. 2.1 常驻 tab 容器 + 路由（先空占位） [ ], e7: 1-3-2. Q2 首个 ES 风格 tab 选型：C08 个股分级研究 vs C07 行情总览 [ ]
- 1-2-3. 2.3 证据层对齐 CompositionOwner 单一 owner（C26） ← e8: 1-2-2. 2.2 首个 ES 风格 tab 原型（C08 个股分级研究 / C07 行情总览） [ ]
- 1-2-4. 2.4 补齐其余 tab（连板/题材/大V复盘/持仓巡检/AI优化/游资心法） ← e9: 1-2-3. 2.3 证据层对齐 CompositionOwner 单一 owner（C26） [ ]
- 1-2-5. 2.5 清理 ES 派生残留 + 保留声明/注明变更 ← e10: 1-2-4. 2.4 补齐其余 tab（连板/题材/大V复盘/持仓巡检/AI优化/游资心法） [ ]

</details>


### 当前施工：1-1-3. 1.3 electron-builder 打包 macOS/Windows（补 C04/C34 缺口）

Scope gate: Product execution（实现 electron-builder 打包，补 C04/C34 缺口）。退出条件：DMG/EXE 安装后零配置启动。首切片：electron-builder 配置 + 本地 macOS 构建证据；代码签名/公证留作后续决策点（需用户证书，跨 macOS 出 Windows 包受限）

**决策：**
- Q: 打包目标与首切片？ → 先本地 macOS dmg（unsigned）作证据；Windows exe 与代码签名/公证留后续 (electron-builder 入 desktop/ devDependencies；首切片只验证 dmg 能产出且安装后零配置启动 ui-host 子进程。签名/公证需用户证书；macOS 直出 Windows 包不可行（wine 脆弱），Windows 包改在 CI/Windows 跑。本环境无证书，先 unsigned 验证链路)
- Q: 本切片在 B pivot 下状态？ → 冻结（retired）：desktop/ Python-ui-host 壳被 1-5 取代 (2026-10-14 zj 选 B：Electron 改 spawn Go。本切片（打包 Python 壳）不再推进，保留 git 历史作证据。新打包目标 = Go 二进制，归 1-5-2。)

### 下一步可开工（ready 前 3）

- 1-1. Phase 1 — Electron 化 ZW 客户端（薄壳，零 UI 重写） [ ]
- 1-2. Phase 2 — ES 产品内容常驻 Tab（A' merge-then-adapt） [ ]
- 1-3. 待决对齐项（需 zj 拍板） [ ]
<!-- ROADMAP_SECTION_END -->
