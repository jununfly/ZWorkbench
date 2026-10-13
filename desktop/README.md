# ZWorkbench desktop shell

Electron 薄壳（路线图切片 `1-1-1`）。它**不是**第二个 owner：不打开 owner 数据库、
不改持久状态、不接 Provider。它只做一件事——把 `zworkbench ui-host` 作为子进程拉起，
然后把一个桌面窗口指向它的 loopback 地址。

## 运行

```bash
cd desktop
npm install     # 只装 devDependency: electron
npm start       # = electron .
```

## 它依赖的契约（`src/zworkbench/cli.py`）

| 契约 | 位置 |
|---|---|
| `ui-host` 只绑 loopback，`--port 0` 让 OS 分配空闲端口 | `cli.py:365-378` |
| 进入服务循环前先向 **stdout** 打一行 `{"event":"serving","base_url":"http://127.0.0.1:<port>"}` | `cli.py:1450` + `_announce` (`cli.py:1627`) |
| trap SIGINT/SIGTERM → 关 socket → 打 `{"event":"stopped"}` → exit 0 | `cli.py:1459-1474` |

所以 shell **不猜端口、不轮询**：读那一行公告即就绪；停止发 SIGTERM，SIGKILL 只是兜底。

## 环境变量（CLI 定位）

默认执行 PATH 上的 `zworkbench`。源码直跑时用环境变量覆盖：

```bash
ZWORKBENCH_CLI=/path/to/python3 \
ZWORKBENCH_CLI_PREARGS="-m zworkbench.cli" \
PYTHONPATH=../src \
npm start
```

| 变量 | 含义 |
|---|---|
| `ZWORKBENCH_CLI` | 可执行程序，默认 `zworkbench` |
| `ZWORKBENCH_CLI_PREARGS` | 子命令前的前置参数，如 `-m zworkbench.cli` |
| `ZWORKBENCH_READY_TIMEOUT_MS` | 等 serving 公告的超时，默认 20000 |

## 截图模式（无头环境下验证窗口内容）

「窗口渲染出来了没有」不能靠 HTTP 200 证明——那只能说明服务器应答了。设
`ZW_DESKTOP_SHOTS_DIR` 即进入截图模式：离屏渲染、逐个路由存 PNG + DOM 探针 +
像素统计，然后自行退出。

```bash
env -u ELECTRON_RUN_AS_NODE \
  ZW_DESKTOP_SHOTS_DIR=/tmp/zw-shots \
  ZWORKBENCH_CLI=/path/to/python3 ZWORKBENCH_CLI_PREARGS="-m zworkbench.cli" \
  PYTHONPATH=../src \
  ./node_modules/.bin/electron . --no-sandbox --disable-gpu
```

产物：`<dir>/<route>.png` + `<dir>/report.json`。**退出码 0 = 所有视图渲染正常**。

三层证据，逐层比前一层强：

| 层 | 判据 | 能证明什么 |
|---|---|---|
| HTTP 200 | 状态码 | 服务器应答了（最弱，证明不了渲染） |
| DOM 探针 | 节点数、文本长度、标题、`looksBroken`（捕获 Traceback/500） | DOM 建起来了、有可见内容、不是错误页 |
| 像素统计 | `uniqueColors`、`inkRatio`、`dominantColor`、`blank` | **真的画出来了**——纯色/空白页会被判 `blank=true` |

`inkRatio` = 非主色像素占比。一个正常页面不会是单一颜色：`blank` 判定为
`inkRatio < 0.005 或 uniqueColors < 8`。像素统计走 `capturePage()` 的 RGBA 位图，
在进程内算完，不落中间文件。

PNG 是给**人眼**的（有 GUI 或多模态模型时直接看）；`report.json` 与退出码是给
**CI/机器**的。两者不互相替代。

| 变量 | 含义 |
|---|---|
| `ZW_DESKTOP_SHOTS_DIR` | 设了即进入截图模式；产物目录 |
| `ZW_DESKTOP_SHOTS_ROUTES` | 逗号分隔路由，默认 `/home,/record-view,/task-detail` |
| `ZW_DESKTOP_SHOTS_WIDTH` / `_HEIGHT` | 视口，默认 1280×860 |
| `ZW_DESKTOP_SHOTS_SETTLE_MS` | load 后等待布局/paint 的时间，默认 1500 |

截图模式会把 `userData` 重定向到 `<dir>/_userdata`：验证运行不该污染真实的
`~/Library/Application Support`，且在受限宿主上那场退出清理会被拒绝、把一次成功的
运行变成非零退出（实测）。

## 本机环境坑（本机实测，换机器可能不适用）

| 现象 | 原因 | 处置 |
|---|---|---|
| `TypeError: Cannot read properties of undefined (reading 'whenReady')` | 环境注入了 `ELECTRON_RUN_AS_NODE=1`，Electron 退化成纯 Node，`require('electron')` 只返回二进制路径字符串 | `env -u ELECTRON_RUN_AS_NODE npm start` |
| `sandbox initialization failed: Operation not permitted` → GPU/network 进程连环崩 → SIGTRAP | Chromium 自带沙箱在受限执行环境里无法初始化（与本机 `ps` 被拒同源：嵌套沙箱被禁） | 加 `--no-sandbox` 启动；**这是环境绕行，不要写进 `package.json` 固化**，会削弱安全性 |
| electron 二进制下载卡在 0%、22 分钟零字节 | 默认走 github.com releases，国内网络基本不动 | `env ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ npm install`（实测 129M / <50s） |
| 截图模式退出码非 0，stderr 报 `~/Library/Application Support/zworkbench-desktop/... file-delete 被拒绝` | 宿主沙箱拒绝 Electron 关闭时清理真实 user-data 目录；产物其实已经写好了 | 已修：截图模式把 `userData` 重定向到 `<dir>/_userdata`。正常 GUI 模式不受影响 |

排查提示：`electron --version` 打印的是**内置 Node 的版本**（44.7.0 内置 Node 24.21.0），不是 Electron 版本。
要确认 Electron 版本看 `node_modules/electron/dist/version` 或 Info.plist。

## 验证记录（切片 1-1-1，2026-10-14）

| 项 | 结果 |
|---|---|
| `node --check main.js` | 通过 |
| Electron 实际版本 | 44.7.0（Info.plist `CFBundleShortVersionString`） |
| 主进程日志 | `[desktop] serving at http://127.0.0.1:62481` |
| `GET /home` `/record-view` `/task-detail` | 均 200（三视图） |
| 杀掉 Electron 后端口 | 已释放，无孤儿后端残留 |
| **窗口像素** | **已闭合（机器判定）**：截图模式离屏渲染三视图，`blank=false`，退出码 0。见下表 |

### 像素证据（2026-10-14，截图模式）

| 路由 | 尺寸 | uniqueColors | inkRatio | blank | nodes | text |
|---|---|---|---|---|---|---|
| `/home` | 1280×860 | 1927 | 0.6426 | false | 227 | 1272 |
| `/record-view` | 1280×860 | 399 | 0.1233 | false | 30 | 96 |
| `/task-detail` | 1280×860 | 167 | 0.0510 | false | 23 | 101 |

三个视图都不是纯色页，即 Chromium 确实完成了布局与绘制。PNG 落在
`.workbuddy/shots-1-1-1/`（gitignored），可直接打开过目。

顺带的观察（属产品现状，不是本切片缺陷）：`record-view` / `task-detail` 在未选中
具体 run/task 时内容很稀薄（节点 30 / 23），样式也朴素于 `home`。CSS 是统一注入的
（`ui_host.py` 的 `DOCUMENT.format(stylesheet=...)`），所以这不是样式没加载，而是
这两个视图自身的 HTML 结构较简、且当前处于空态。

## 已知限制（留给后续切片）

- **窗口关掉即退出后端**：`window-all-closed` → SIGTERM 子进程 → 退出。
- **Electron 被强杀时子进程可能残留**：`process.on('exit')` 只是 best-effort SIGKILL
  兜底，真正的 supervisor 级守卫属于后续切片，不在本切片范围内。
- **单实例锁 / 原生菜单 / 托盘**：切片 `1-1-2`。
- **打包分发**：切片 `1-1-3`。
- **Node 依赖偏离零依赖（C32）的登记**：切片 `1-1-4`。
