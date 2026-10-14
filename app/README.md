# ZWorkbench Go + Electron + React 工作台（骨架）

> 提案方向 B（见 `docs/designs/zw-go-electron-architecture.md`）。**推翻 ADR 0013 前提，需 zj 显式接受。**
> 当前为骨架：无业务逻辑，纯 stdlib Go 服务 + React 多 tab 壳 + Electron 宿主。

## 目录

```
app/
├─ cmd/server/main.go      Go 本地服务入口（读 config → 起 router）
├─ internal/               config / api / data / agent / domain
├─ electron/               Electron 壳（spawn Go、注入 token、开窗口）
└─ web/                    React + TS + Vite 前端（多 tab 壳）
```

## 运行

### 1) Go 服务（纯 stdlib，离线可编译）

```bash
cd app
go run ./cmd/server
# 默认监听 127.0.0.1:18080，token 随机（见启动日志）
# 自定义：ZW_PORT=18080 ZW_TOKEN=xxx ZW_DB=mem go run ./cmd/server
```

验证：

```bash
curl 'http://127.0.0.1:18080/api/health?token=<启动日志里的token>'
```

### 2) 前端（dev，需联网 npm install 一次）

```bash
cd app/web
npm install
npm run dev          # http://localhost:5173，自动调 127.0.0.1:18080
```

### 3) 桌面壳

```bash
cd app/electron
npm install
ZW_WEB_URL=http://localhost:5173 npm start   # dev：前端走 Vite
# prod：先 `go build -o bin/zworkbench-go ./cmd/server`，再 `npm start`（Electron 托管 Go 服务）
```

## 设计要点

- **多 tab 工作台**：`internal/domain/tabs.go` 是 tab 注册表，stock 只是其中之一。
- **本地鉴权**：Electron 启动生成一次性 token，经 URL query 注入前端，Go 中间件校验。
- **LLM Provider 层**：`internal/agent` 统一接口，现 OpenAI/DeepSeek stub，待接真实端点。
- **证据底座**：`internal/data` 先用 MemStore，Phase 2 换纯 Go SQLite 驱动。
- **Python 核心**：既有 `src/zworkbench`（CompositionOwner 证据层）可作可选 sidecar，详见架构文档 §4。
