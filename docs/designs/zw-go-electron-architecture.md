# ZWorkbench → Go + Electron + React 工作台架构（提案）

> 状态：**已接受（2026-10-14 zj 选 B：Go 全 pivot）** ｜ 原提案待评审态已关闭
> 作者：zjj ｜ 参照：`docs/plans/comparison-easy-stock-vs-zworkbench-2026-10-13.md`（`C01`…`C41`）、`docs/plans/zw-electron-es-tab-plan-2026-10-13.md`、`docs/zj-adr/0013-desktop-shell-node-dependency-deviation.md`、`docs/zj-adr/0015-go-full-pivot-supersedes-0013.md`
> ✅ **zj 2026-10-14 已接受本提案（B 方向）**：推翻 ADR 0013 前提，由 **ADR 0015** `supersedes` 0013 并重新界定偏离边界。`desktop/` + Python ui-host 壳转入 **retired**（保留 git 历史，停止新开发）。路线图节点 `1-5` 承载落地切片。

> 🔴 **已提交事实（2026-10-14 补，影响决策）**：`desktop/` Electron 薄壳（Phase 1，ADR 0013）**已经建好并 commit+push**——`1-1-1`/`1-1-2`/`1-4`（含菜单/托盘/单实例锁/自检/截图验证）已完成，`1-1-3` electron-builder 打包 in_progress。它现在 spawn 的是 **Python `ui-host`（server-rendered HTML）**，并有一整套围绕 Python ui-host 的自检/截图 harness。
> 推论：**"变成桌面应用、加速 0→1" 这个目标已被已提交工作达成**，不是待办。语言切换只影响 **Phase 2（吸收 ES 内容）**，不影响桌面壳本身。因此本提案若被接受，代价是**废掉已提交的 `desktop/` + Python ui-host harness**（不是从零），请据此重新权衡（见 §1.5）。

## 0. 为什么又开这一篇

`zw-electron-es-tab-plan` 与 ADR 0013 已拍板的方向是：**Python 零依赖核心 + Electron 薄壳（spawn `ui-host` server-rendered HTML）+ Phase 2 把 ES 内容 merge 进 Python**。

zj 在 2026-10-14 重新发问："是否切换为 Go/Rust"。澄清后真实动机是：

1. **客户端对真实用户"功能可用"** —— 原型阶段想快速 go through 0→1；
2. **客户端顺畅对接 LLM provider** —— 想要现成的本地 Agent 服务范式；
3. **吸纳 easy-stock 产品内容作起点再改形** —— stock 只是工作台多 tab 之一；
4. **程序员视角**：Go/Rust 的静态编译运行时更稳、定位问题/写 tests 比 Python 更有优势。

这四条把"是否切语言"从"内容相关性"（zw 已明确不相关）重构为**工程质量 + 加速 0→1**的轴。结论：**现有 Python 核心 + server-rendered HTML 方案在"吸收 ES 内容"与"runtime/测试"两条上都不如直接镜像 easy-stock 的 Go+Electron+React**。

因此本提案建议：**以 Go 为主运行时（镜像 easy-stock），Python 的 CompositionOwner 证据核心降为可选本地 sidecar**，在不丢弃已投资差异化的前提下最大化 0→1 速度。

## 1. 决策冲突点（必须显式处理）

| 项 | ADR 0013 / 现有 plan | 本提案 |
|---|---|---|
| 主运行时 | Python（`ui-host` server-rendered HTML） | **Go**（本地 HTTP+WS API） |
| 前端 | server-rendered HTML（C21） | **React + TypeScript**（富前端，镜像 ES C21） |
| 桌面壳 | `desktop/` Electron 薄壳 spawn Python | Electron 壳 spawn **Go 服务** |
| 零依赖约束（C32） | Python 运行时零依赖 | 改为"Go 运行时零外部依赖、纯 stdlib 起骨架"，Python 仅作可选 sidecar |
| ES 内容接入 | A' merge-then-adapt 进 Python | **直接镜像 ES 的 Go/React 脚手架**，零翻译成本 |

> 推翻代价：ADR 0013 的"核心不被污染"边界失效，需新 ADR 重新划界；现有 `desktop/` 方案被本提案取代（Electron 壳改由 Go 应用持有）。

### 1.5 已提交 `desktop/` 对选项的影响（重写权衡）

因为 `desktop/` 已提交，三个选项的**真实成本**变了：

| 选项 | 与已提交 `desktop/` 的关系 | 真实代价 |
|---|---|---|
| **A. 维持现状**（ADR 0013 + A'） | 完全复用，零推翻 | 最低。只写 Python 版 ES 内容 tab；但吸收慢（Go→Python 翻译）+ server-rendered HTML UX 较弱 |
| **B-lite. Python 壳 + Go 股票服务** | 保留 `desktop/` + Python ui-host；Go 作为**独立股票服务**，ui-host 用 iframe/proxy 嵌入 | 中。拿到 Go runtime/测试（仅股票域），不废已提交工作；双运行时 |
| **B. Go 全 pivot**（本骨架方案） | **废掉 `desktop/` + Python ui-host harness**，Electron 改 spawn Go | 最高。重写桌面壳后端 + 迁移自检/截图 harness；但全工作台统一 Go runtime + React 富前端 |

> 之前我直接推 B 是错的——那时没意识到 `desktop/` 已提交。B 现在不是"从零加速"，而是"用已达成目标换统一技术栈"。**若只想解决 Phase 2 吸收慢，A' 或 B-lite 更诚实。**

## 2. 三个选项对比

| 选项 | 做法 | 加速 0→1 | runtime/测试 | 保住证据核心 | 复杂度 |
|---|---|---|---|---|---|
| **A. 维持现状**（ADR 0013 + A'） | Python 核心 + Electron 壳 + ES 内容翻成 Python | 慢（翻译 ES Go→Python + server-rendered HTML） | 弱（Python 大 App 难测稳） | ✅ 完整保留 | 低 |
| **B. Go 全 pivot**（本提案推荐） | Go 主运行时镜像 ES，Python 证据核心作 sidecar 或后续移植 | **最快**（直接复用 ES 范式，零翻译） | **强**（Go 静态/测试） | ⚠️ sidecar 保住 / 或后续移植 | 中 |
| **C. Rust + Tauri** | Rust 运行时 + Tauri 壳 | 慢（Tauri≠Electron，ES 桌面胶水不可直接复用） | 最强 | ⚠️ 同 B | 高（且违背加速意图） |

**修订推荐（2026-10-14）**：由于 `desktop/` 已提交，**不再无条件推 B**。按"最小代价命中动机"排序：
- 只想解决 Phase 2 吸收慢 + 拿到 Go runtime → **B-lite**（保留 `desktop/`，Go 仅做股票域服务）。
- 接受废掉已提交 `desktop/`、换全工作台统一 Go runtime + React 富前端 → **B**（本骨架即此方案）。
- 不想动已提交任何东西、最低风险 → **A'**（Python 吸收 ES 内容）。

C（Rust+Tauri）始终因违背"加速 0→1"被排除。请 zj 在 §1.5 三选项里拍板方向，骨架 `app/` 对应的是 B；若选 A'/B-lite，本骨架需调整或弃用。

## 3. 分层架构（镜像 easy-stock，适配 ZW 多 tab）

```
┌──────────────────────────────────────────────────────────┐
│ Electron 桌面壳（app/electron）                            │
│  - BrowserWindow 指向 http://127.0.0.1:{PORT}?token={T}   │
│  - preload 注入 apiBase + token 到渲染进程                │
│  - 单实例锁 / 托盘 / 原生菜单（Phase 1 后补）             │
└───────────────┬──────────────────────────────────────────┘
                │ loopback HTTP/WS
┌───────────────▼──────────────────────────────────────────┐
│ React + TypeScript 前端（app/web）                        │
│  - 多 tab 工作台壳（左侧 tab 注册表，stock 为其中之一）   │
│  - 各 tab 独立组件，经 apiBase 调本地 Go API             │
└───────────────┬──────────────────────────────────────────┘
                │ 本地 API（同进程 / 同机）
┌───────────────▼──────────────────────────────────────────┐
│ Go 本地服务（app/cmd/server + app/internal）              │
│  ├─ api         HTTP/WS 路由 + 处理器（鉴权中间件）      │
│  ├─ domain     领域服务：tab 注册表 + 各 tab 业务 stub   │
│  │   └─ stock  行情总览/个股研究/连板/题材（镜像 ES）    │
│  ├─ agent      LLM Provider 层（OpenAI/DeepSeek/...）     │
│  ├─ data       Store 接口 + SQLite 实现（证据快照）       │
│  └─ config     端口/token/db 路径 从 env 读取             │
└───────────────┬──────────────────────────────────────────┘
                │ 可选本地 sidecar（同机 loopback）
┌───────────────▼──────────────────────────────────────────┐
│ Python 证据核心 sidecar（src/zworkbench，既有）           │
│  - CompositionOwner 单一 durable owner（C26）            │
│  - safe-stop 安全模型（C28）                             │
│  - 仅 coding-evidence / 可复核任务调用，不进主 UI 热路径  │
└──────────────────────────────────────────────────────────┘
```

### 3.1 进程模型

- **主进程**：Electron 启动 → spawn `app` Go 二进制（或 dev 模式连 `go run`）→ 拿到 `PORT` + 一次性 `TOKEN` → 开窗口。
- **Go 服务**：绑定 `127.0.0.1`，所有 API 需 `?token=` 或 `Authorization: Bearer`；WebSocket 推行情/AI 事件。
- **Python sidecar（可选）**：Go 通过本地 HTTP 调 Python 的 `ui-host`/证据 API，用于 coding-evidence 类任务；删掉不影响主工作台。

### 3.2 Go 包结构（骨架已实现）

```
app/
├─ go.mod                      module github.com/jununfly/ZWorkbench/app
├─ cmd/server/main.go          启动：读 config → 建 store → 起 router
├─ internal/
│  ├─ config/config.go         PORT/TOKEN/DB 从 env，带默认值
│  ├─ api/router.go            /api/health /api/tabs /api/stock/* /api/agent/*
│  ├─ data/store.go            Store 接口 + MemStore（SQLite 后补，纯 Go 驱动）
│  ├─ agent/provider.go        Provider 接口 + OpenAI/DeepSeek stub
│  └─ domain/tabs.go           Tab 注册表（stock + 占位 tab）
├─ electron/main.js            壳：spawn Go、注入 token、开窗口
├─ electron/preload.js         暴露 window.__ZW__.{apiBase,token}
└─ web/                        React+TS+Vite 前端（多 tab 壳）
```

### 3.3 Tab 注册表（多 tab，stock 其一）

`domain/tabs.go` 返回有序 tab 列表，前端据此渲染侧边栏。初始：

| id | title | 来源 |
|---|---|---|
| `stock-overview` | 行情总览 | 镜像 ES C07 |
| `stock-research` | 个股分级研究 | 镜像 ES C08 |
| `stock-limitup` | 超短连板 | 镜像 ES C09 |
| `coding-evidence` | 编码证据（sidecar） | 接 Python 核心 C26 |
| `settings` | 设置 / LLM Provider | 本工作台 |

新增 tab = 在注册表加一项 + 前端加组件 + Go 加对应 domain stub，符合你"微进度、小切片"的节奏。

### 3.4 LLM Provider 层

`agent/provider.go` 定义统一 `Provider` 接口（Chat / Embed / 模型列表），先放 OpenAI / DeepSeek 两个 stub（返回占位响应），后续接真实 Responses API。多 provider 可切换，对应你动机②。

### 3.5 本地证据底座（SQLite）

`data` 层先用 `MemStore` 让骨架可离线编译运行；Phase 2 换 `SqliteStore`（纯 Go 驱动如 `modernc.org/sqlite`，无 cgo）。表设计沿用 ES 的"版本化快照 + 来源/时间"思路，并预留接入 CompositionOwner 单一 owner 的字段（见 3.1 sidecar 或后续移植）。

### 3.6 本地鉴权 Token

Electron 启动 Go 时生成一次性 `TOKEN`（随机 32 字节 hex），通过 env / preload 注入前端；Go 中间件校验。镜像 ES 的本机鉴权范式。

## 4. 与现有 Python 核心的关系（两条落地路线）

- **路线 B1（sidecar，推荐起步）**：Python 核心保持不动，Go 通过 loopback 调其证据 API。最快、零重写，但双运行时。
- **路线 B2（移植）**：把 CompositionOwner / safe-stop 概念用 Go 重写进 `data` + `api` 层，单运行时统一。工作量更大，但长期更干净；可在 1→100 阶段按需做。

> 无论 B1/B2，ZW 的差异化（可复核编码证据 C26/C28）都保留，只是承载位置不同。

## 5. 迁移与风险

| ID | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R-A | 推翻 ADR 0013 边界 | Python 零依赖核心前提失效 | 新 ADR 0015 重新划界；`src/zworkbench` 仍独立可跑 |
| R-B | 双运行时（B1） | 桌面包体积/启动复杂度升 | Phase 1 先用 B1；B2 在稳定后做 |
| R-C | License（PolyForm NC） | 镜像 ES 脚手架若拷代码需保留声明 | 仅参考架构/重写，非原样分发；个人非商业 OK |
| R-D | 产品定位稀释（C01/C03） | 加 A 股扩展 ZW 边界 | 明确为"工作台常驻 tab"，核心差异化仍在 evidence |

## 6. 构建 / 运行（骨架）

```bash
# Go 服务（纯 stdlib，离线可编译）
cd app && go run ./cmd/server          # 默认 :18080，token 见启动日志

# 前端（需联网 npm install 一次）
cd app/web && npm install && npm run dev

# 桌面壳（需先起 Go 服务）
cd app/electron && npm install && npm start
```

环境变量：`ZW_PORT`（默认 18080）、`ZW_TOKEN`（默认随机）、`ZW_DB`（默认内存）。

## 7. 下一步（1→100）

1. ✅ zj 已确认 B 方向 + 接受推翻 ADR 0013（ADR 0015 已写，supersede 0013；`desktop/` 转入 retired）。
2. 先让骨架 `go run` + 前端 tab 壳跑通（零业务逻辑）。
3. 第一个真 tab：镜像 ES「行情总览 C07」最小切片，验证多源适配/回退（C36）。
4. 接真实 LLM Provider（动机②）。
5. coding-evidence tab 走 B1 sidecar，验证与 Python 核心互通。
6. 逐步补齐其余 tab（C08/C09/C10/C11/C12/C19），每 tab 一微切片。
