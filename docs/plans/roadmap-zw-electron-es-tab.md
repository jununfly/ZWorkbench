<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap-zw-electron-es-tab.json` | 最后更新: 2026-10-15 23:11:49

[x][X+] 1. ZW → Electron 客户端 + ES 常驻 Tab
├── [x][X+] 1-1. Phase 1 — Electron 化 ZW 客户端（薄壳，零 UI 重写）
│   ├── [x][X+] 1-1-1. 1.1 Electron 薄壳：main 进程起 ui-host，BrowserWindow 指向 loopback
│   ├── [x][X+] 1-1-2. 1.2 原生菜单/托盘/单实例锁；CLI 不回归
│   ├── [x][X+] 1-1-3. 1.3 electron-builder 打包 macOS/Windows（补 C04/C34 缺口）
│   └── [x][X+] 1-1-4. 1.4 登记 Node/Electron 依赖为 tracked deviation（偏离零依赖 C32）
├── [x][X+] 1-2. Phase 2 — ES 产品内容常驻 Tab（A' merge-then-adapt）
│   ├── [x][X+] 1-2-1. 2.1 常驻 tab 容器 + 路由（先空占位）
│   ├── [x][X+] 1-2-2. 2.2 首个 ES 风格 tab 原型（C08 个股分级研究 / C07 行情总览）
│   ├── [x][X+] 1-2-3. 2.3 证据层对齐 CompositionOwner 单一 owner（C26）
│   ├── [x][X+] 1-2-4. 2.4 补齐其余 tab（连板/题材/大V复盘/持仓巡检/AI优化/游资心法）
│   └── [x][X+] 1-2-5. 2.5 清理 ES 派生残留 + 保留声明/注明变更
├── [x][X+] 1-3. 待决对齐项（需 zj 拍板）
│   ├── [x][X+] 1-3-1. Q1 接受引入 Node/Electron 依赖？（偏离零依赖 C32）
│   ├── [x][X+] 1-3-2. Q2 首个 ES 风格 tab 选型：C08 个股分级研究 vs C07 行情总览
│   ├── [x][X+] 1-3-3. Q3 本草稿评审通过后落点（design/ADR 编号）
│   └── [x][X+] 1-3-4. Q4 Electron 如何拉起 Python：spawn ui-host 子进程 vs 用户先跑再连 loopback
├── [x][X+] 1-4. 全量测试套件挂死排查与修复
│   ├── [x][X+] 1-4-1. 复现并定位挂死测试（限时+二分+逐测试计时）
│   ├── [x][X+] 1-4-2. 修复挂死根因或显式隔离（skip+原因登记）
│   ├── [x][X+] 1-4-3. 建立可靠全量回归门禁（限时跑通+退出码0）
│   └── [x][X+] 1-4-4. 处置 4 个既有 FAIL（deep_link/overlay/runtime_skill/skill_installation）
└── [x][X+] 1-5. Phase 3 — Go 全 pivot（B）：Electron 改 spawn Go + React 富前端（镜像 ES，supersede 1-1/1-2）
    ├── [x][X+] 1-5-1. 1.5.1 冻结 desktop/ Python-ui-host 壳（保留 git 历史，停止新开发）
    ├── [x][X+] 1-5-2. 1.5.2 Go 骨架 app/ 跑通（go build + go run + 前端多 tab 壳，零业务逻辑）
    ├── [x][X+] 1-5-3. 1.5.3 首个真 tab：镜像 ES 行情总览 C07 最小切片
    ├── [x][X+] 1-5-4. 1.5.4 接真实 LLM Provider（OpenAI/DeepSeek Responses API，动机②）
    ├── [x][X+] 1-5-5. 1.5.5 本地证据底座 SQLite（modernc.org/sqlite 无 cgo）+ 预留 CompositionOwner 字段
    ├── [x][X+] 1-5-6. 1.5.6 coding-evidence tab 走 B2 Go 重写证据核心（C26/C28）进 app，零 Python 依赖
    ├── [x][X+] 1-5-7. 1.5.7 其余 tab（C08/C09/C10/C11/C12/C19），每 tab 一微切片
    └── [x][X+] 1-5-8. 1.5.8 写 ADR 0015 supersede ADR 0013（重新划界 Go 运行时零依赖 + 偏离边界）
<!-- ROADMAP_SECTION_END -->
