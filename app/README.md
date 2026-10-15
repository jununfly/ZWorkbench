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

## 桌面包（1-1-3）

一键构建（Go 二进制 + 前端 dist + Electron 壳）：

```bash
bash app/scripts/build-desktop.sh          # 当前平台安装包：macOS→dmg，Windows→nsis
bash app/scripts/build-desktop.sh --dir    # 只出未打包的 app 目录，用于验证资源布局
```

打包后的资源布局：

```
<app>/Contents/Resources/bin/zworkbench-go    Go 本地服务（CGO_ENABLED=0，单二进制）
<app>/Contents/Resources/web/dist/            前端产物（由 Go 托管，见 internal/webstatic）
```

运行时契约（Electron → Go）：

| 事项 | 约定 | 原因 |
|---|---|---|
| 端口 | Electron 先取空闲端口再注入 `ZW_PORT` | 固定 18080 会与已运行的 `go run` 冲突 |
| 前端 | Electron 注入 `ZW_WEB_DIR=resources/web/dist` | 否则 Go 只能回退候选路径；产物缺失时 `/` 返 503 而非静默 404 |
| 配置 | `ZW_CONFIG` 指向 `userData/config.json` | packaged app 的 cwd 是 `/`，写 `config.json` 会失败 |
| 单实例 | `requestSingleInstanceLock()` | 防止第二个实例再拉起一个 Go 进程 |
| 启动时序 | 窗口加载前先探活端口 | 避免服务未起来导致首屏失败 |

未签名：macOS 出的是 unsigned / 仅 ad-hoc 签名的 dmg，**首次启动被 Gatekeeper 拦截**
（提示文案含「无法验证是否含恶意软件」——这是"开发者身份未知"的标准表述，不是真判毒）。

打开方式（二选一，推荐第 1 种）：

1. **右键（Control+点击）`ZWorkbench.app` → 「打开」**：弹窗里点「打开」即可，
   这是 Apple 官方绕过路径，**不依赖「隐私与安全性」里是否出现入口**。第一次成功后后续双击正常。
2. 双击触发拦截后，去「系统设置 → 隐私与安全性」点「仍允许打开」。

⚠️ 坑：**不要**先 `xattr -dr com.apple.quarantine ...` 再 `open`。删除隔离标记会一并删掉
「仍允许打开」按钮的触发条件，导致方式 2 没入口。如需命令行启动，用方式 1 的等价写法：
`xattr -d com.apple.quarantine <app> && open -a <app>` 也只在该 app 已右键打开过一次后才稳。

### XProtect（"已阻止恶意软件并移到废纸篓"）—— 与上面不是一回事

若弹窗/拦截文案是「已阻止恶意软件并移到废纸篓」，**那是 Apple 内置的 XProtect 杀毒，不是 Gatekeeper**。
区别：

- 上面的「右键打开」只绕过 Gatekeeper（开发者未知），**绕不过 XProtect**——XProtect 基于恶意软件特征库拦截，
  不给「仍允许打开」入口。
- 当前 dmg 内所有二进制（主程序 + Electron Helper + Framework）均为 **ad-hoc 签名且完整**，
  所以这不是"签名损坏"，而是 XProtect 对"无 Apple 公证票据的非可信来源 app"的拦截。
- **XProtect 没有用户侧绕过开关**（不像 Gatekeeper 的 Open Anyway）。可靠解法只有两条：
  1. **公证（notarize）**：需要 Apple Developer ID 证书（$99/年）+ App Store Connect API key。
     本脚本可加 `notarize` 阶段，提供证书后接入即可（见 `build-desktop.sh` 末尾注释）。
  2. **自签名证书（免费，先试）**：在钥匙串建一个 Code Signing 自签根证书（"始终信任"），用它重签整个 bundle。
     ⚠️ 重签**不要**加 `--options runtime`：hardened runtime 下 Electron 渲染进程(V8)无 JIT 权限会立刻"意外退出"。
     正确命令（本机终端跑，.app 从 dmg 拷到本地后签）：
     ```bash
     codesign --force --deep --sign "ZWorkbench Dev" ~/Downloads/ZWorkbench.app
     codesign --verify --deep --strict --verbose=2 ~/Downloads/ZWorkbench.app
     xattr -dr com.apple.quarantine ~/Downloads/ZWorkbench.app
     open ~/Downloads/ZWorkbench.app
     ```
     若之后要走公证(notarize)，再配合 `entitlements.plist`（allow-jit / allow-unsigned-executable-memory /
     disable-library-validation）**加** `--options runtime`。
     若 XProtect 只是卡"无有效签名"，自签能满足；若它按内容特征命中，则仍会被拦，需走公证。
- 排查到底是哪个在拦：用户的机器上跑
  `log show --predicate 'subsystem contains "XProtect"' --last 30m`（需 sudo/不放沙箱），
  或把弹窗原文贴出来区分。

代码签名/公证、Windows 构建、自动更新均不在本切片（公证接入可后续追加）。

## 设计要点

- **多 tab 工作台**：`internal/domain/tabs.go` 是 tab 注册表，stock 只是其中之一。
- **本地鉴权**：Electron 启动生成一次性 token，经 URL query 注入前端，Go 中间件校验。
- **LLM Provider 层**：`internal/agent` 统一接口，现 OpenAI/DeepSeek stub，待接真实端点。
- **证据底座**：`internal/data` 先用 MemStore，Phase 2 换纯 Go SQLite 驱动。
- **Python 核心**：既有 `src/zworkbench`（CompositionOwner 证据层）可作可选 sidecar，详见架构文档 §4。
