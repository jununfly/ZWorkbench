# ZWorkbench Go + Electron + React 工作台（骨架）

> 提案方向 B（见 `docs/designs/zw-go-electron-architecture.md`）。**推翻 ADR 0013 前提，需 zj 显式接受。**
> 当前为骨架：无业务逻辑，纯 stdlib Go 服务 + React 多 tab 壳 + Electron 宿主。
> 📌 闭环后的未完成项（1→100 收尾）见 [`ROADMAP.md`](ROADMAP.md)（事实源 `roadmap-zw-go-1to100.json`，只经 `zj-roadmap-driven` CLI 读写）。

## 目录

```
app/
├─ cmd/server/main.go      Go 本地服务入口（读 config → 起 router）
├─ internal/               config / api / data / agent / domain
├─ electron/               Electron 壳（spawn Go、注入 token、开窗口）
└─ web/                    React + TS + Vite 前端（多 tab 壳）
```

## 运行

### 0) 门禁（改完就跑）

```bash
bash app/scripts/check-go.sh                 # go vet + go test ./...（限时 180s，无缓存）
bash app/scripts/check-web.sh                 # npm ci + tsc --noEmit + vite build
bash app/scripts/check-web.sh --skip-install  # 依赖已装好，只跑类型 + 构建
bash app/scripts/check-package.sh             # unsigned 完整 dmg 回归（慢，几分钟）
bash app/scripts/check-package.sh --dir       # 只出 .app（快），额外验资源布局
```

- `check-go.sh` 会在「已登记有测试的包变成零测试」时判失败，并把还没测试的包以 WARN 列出。
- `check-web.sh` 会校验产物是本次构建的（mtime 新于运行标记），并守住 dist / node_modules 不入库。
- `check-package.sh` 只守 **unsigned 路径**（带 `NOTARIZE`/`SIGN_ID`/`SIGN_CERT` 进来直接拒），四道检查：
  ① unsigned 契约 ② `build-desktop.sh` 退出码 0 且产物在 ③ 产物 mtime 新于本次运行标记（挡掉上一次遗留的 dmg/.app 假阳性）
  ④ 仅 `--dir` 验包内资源布局（Go 二进制可执行 + web/dist/index.html + 至少一个 JS chunk，挡 prod 白屏类缺陷）。
  ⚠️ 本门禁依赖 electron-builder 完整跑通；在本 WorkBuddy 沙箱内 `node-safe-delete-shim` 与 `node-brokered-fs-shim`
  会拦掉打包过程，**绿跑需在真机终端或干净 CI 执行**——门禁在沙箱内会正确失败-closed，不代表打包脚本回归。

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

> dev 模式不经打包，`api.ts` 那类「只打包后才暴露」的缺陷在 dev 下看不见，所以发布前必须跑
> `check-web.sh`（`npm ci` + `tsc --noEmit` + `vite build` + 产物新鲜度 + 入库守卫），任一步
> 失败即退出码 1。

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

未签名：macOS 出的是 unsigned / 仅 ad-hoc 签名的 dmg。首次启动会被拦，**弹窗文案有两条分支，处理方式完全不同**：

| 弹窗文案 | 拦截者 | 有没有用户侧绕过 |
|---|---|---|
| 「无法验证是否含恶意软件」/「来自身份不明的开发者」 | Gatekeeper（开发者身份未知） | ✅ 右键打开 / 「仍允许打开」 |
| 「已阻止恶意软件并移到废纸篓」 | XProtect（Apple 内置杀毒） | ❌ 无（详见下节） |

下面是 **Gatekeeper 分支**（文案含「无法验证是否含恶意软件」——这是"开发者身份未知"的标准表述，不是真判毒）。

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
- **XProtect 没有用户侧绕过开关**（不像 Gatekeeper 的 Open Anyway）。右键打开 / `xattr -dr` / 自签证书
  **三者都无效**（已实测：右键打开仍被"移到废纸篓"）。可行方向只有一条：
  **公证（notarize）**——需要付费 Apple Developer Program 的 Developer ID 证书，见下节。
  注意公证解的是"无公证票据"类规则；若 XProtect 是按**内容特征**命中（Electron + 内嵌 Go 二进制的
  结构可能近似已知套壳样本），公证也可能清不掉，需改打包结构或等 Apple 更新特征库。
- 排查到底是哪个在拦：跑
  `log show --predicate 'process contains "syspolicyd" OR process contains "XProtect" OR subsystem contains "Xprotect"' --last 30m --info --debug`
  （默认会跳过 Info/Debug 级，检测明细通常在那两级；弹框由 `syspolicyd` 弹出，谓词别只写 XProtect）
  或把弹窗原文贴出来区分。

#### 自用启动（无需 Developer ID）

如果只是**你自己一台 Mac 上用**，不需要 Developer ID 证书，也不需要公证。证书和公证都只解决「分发给别人」的信任问题，不影响你本机执行。

已验证：本项目 app 在本机可直接运行——从终端拉起 `.app` 后 Go 服务自启、GUI 渲染（`#root childCount=1`）、UI 配置落盘 `~/Library/Application Support/zworkbench-electron/config.json` 均正常。下面是自用启动的几种方式（都不需要证书）：

1. **本地构建后直接 `open`**（最省事）：`app/electron/dist/mac-arm64/ZWorkbench.app` 是你本机产物，通常不带 quarantine 标记，直接 `open app/electron/dist/mac-arm64/ZWorkbench.app` 即可。
2. **右键（Control+点击）打开**：走上面的 Gatekeeper 分支，第一次成功后后续双击正常。
3. **去 quarantine 后打开**（仅当 Finder 拦时）：
   ```bash
   xattr -dr com.apple.quarantine app/electron/dist/mac-arm64/ZWorkbench.app
   open app/electron/dist/mac-arm64/ZWorkbench.app
   ```
   ⚠️ 注意上面「坑」：不要先 `xattr -dr` 却指望「仍允许打开」入口；如需该入口，先右键打开过一次。

何时才需要 Developer ID + 公证（见下节）：

| 场景 | 需要？ |
|---|---|
| 自己一台 Mac 跑 | ❌ |
| 自己多台 Mac 同步 | ❌（拷贝 + 去 quarantine） |
| **发给别人 / 团队 / 公开下载** | ✅ |
| 上架 App Store | ✅（走 Distribution 证书，非 Developer ID） |

成本判断：$99/年的 Apple Developer Program 只在「要分发给他人」时有回报；solo 自用工具现阶段可省，代码侧（签名配置 + 公证门控 + 填参模板）已就绪，等真要发别人再入会、填参跑 `NOTARIZE=1` 即可。

唯一保留风险：若某天 Apple 的 XProtect **特征库**真把本二进制误判（概率低，且已实跑成功说明当前未拦），自用也会卡住、只能靠公证洗白——但那已属分发场景考量，自用无碍。

### 公证接入（`NOTARIZE=1`）

`build-desktop.sh` 已内置公证门控，**默认关**（不上传、不改变 unsigned 产物）。打开方式：

```bash
# 先把凭证存进钥匙串（推荐，凭证不进命令行历史）
xcrun notarytool store-credentials zw-notary \
  --apple-id "<你的 Apple ID>" --team-id "<TEAMID>" --password "<App 专用密码>"

NOTARIZE=1 \
DEV_ID_APP="Developer ID Application: <名字> (<TEAMID>)" \
APPLE_KEYCHAIN_PROFILE=zw-notary \
bash app/scripts/build-desktop.sh
```

| 环境变量 | 必填 | 说明 |
|---|---|---|
| `NOTARIZE` | 是（值 `1`） | 门控开关；不设＝完全走原来的 unsigned 流程 |
| `SIGN_ID` | 另一模式 | 只签名、不公证（见下节）；与 `NOTARIZE` / `SIGN_CERT` 互斥 |
| `DEV_ID_APP` | 是 | 钥匙串里 Developer ID Application 证书名；脚本会先校验存在性 |
| `APPLE_KEYCHAIN_PROFILE` | 三选一 | 推荐。凭证来源 A |
| `APPLE_ID` + `APPLE_APP_SPECIFIC_PASSWORD` + `APPLE_TEAM_ID` | 三选一 | 凭证来源 B（teamId 必须给全） |
| `APPLE_API_KEY` + `APPLE_API_KEY_ID` + `APPLE_API_ISSUER` | 三选一 | 凭证来源 C（App Store Connect API key） |

#### 拿证书 + 填参模板（真公证前置）

真公证的硬前置是 **Developer ID Application 证书**，只能从付费 Apple Developer Program（$99/年，个人/组织同价；Enterprise $299 不需要）拿：

1. 入会 developer.apple.com/programs/（个人约 2 天过审；组织需 D-U-N-S 核验，更久）。
2. Keychain Access → 证书助理 → 从证书颁发机构请求证书（CSR，存盘）。
3. developer.apple.com/account → Certificates → `+` → **Developer ID Application** → 上传 CSR → 下载 `.cer` → 双击装进 login keychain。
   校验：`security find-identity -v -p codesigning` 应列出 `Developer ID Application: <名字> (<TEAMID>)`。

证书就绪后，下面三选一直接复制运行（`DEV_ID_APP` 是证书 Common Name **字符串**，不是路径）：

```bash
# 来源 A（推荐）：钥匙串 profile
NOTARIZE=1 \
DEV_ID_APP="Developer ID Application: <名字> (<TEAMID>)" \
APPLE_KEYCHAIN_PROFILE=zw-notary \
bash app/scripts/build-desktop.sh

# 来源 B：Apple ID + App 专用密码
NOTARIZE=1 \
DEV_ID_APP="Developer ID Application: <名字> (<TEAMID>)" \
APPLE_ID="<你的 Apple ID>" \
APPLE_APP_SPECIFIC_PASSWORD="<app-specific-password>" \
APPLE_TEAM_ID="<TEAMID>" \
bash app/scripts/build-desktop.sh

# 来源 C：App Store Connect API key
NOTARIZE=1 \
DEV_ID_APP="Developer ID Application: <名字> (<TEAMID>)" \
APPLE_API_KEY=/path/to/AuthKey_<KEYID>.p8 \
APPLE_API_KEY_ID="<KEYID>" \
APPLE_API_ISSUER="<ISSUER>" \
bash app/scripts/build-desktop.sh
```

⚠️ 两个易错点：
- `electron-builder` **不读** `APPLE_TEAM_ID` 环境变量——只有来源 B 需要 teamId，且必须写进 `package.json` 的 `build.mac.notarize.teamId`（来源 C / 钥匙串只覆盖 identity，`notarize` 保持 undefined）。
- 送审 + `stapler` 通常 1–30 分钟；失败看 `notarytool` 日志，多半是某个嵌套二进制没签或 entitlements 不匹配（本项目已把 Go 二进制和四键 entitlements 纳签）。

执行链路：预检（缺证书/凭证**在构建前**即失败）→ Developer ID 签名（hardened runtime +
`electron/build/entitlements.mac.plist`，并把内嵌 `zworkbench-go` 显式纳入签名清单）→ electron-builder
送公证并 staple `.app` → dmg 产出后再送公证 + staple dmg → `codesign --verify` / `stapler validate` 留证。

已与 `SIGN_CERT`（自签）设为互斥：自签会改写签名使公证票据失效，同时给出两者会直接报错退出。

#### 只签名、不公证（`SIGN_ID`）

用于**两段式验收**：先单独确认签名链路正确，再上公证。这样公证首跑失败时能区分「签名坏了」还是「Apple 拒了」。

```bash
SIGN_ID="ZWorkbench Dev" bash app/scripts/build-desktop.sh        # 出安装包
SIGN_ID="ZWorkbench Dev" bash app/scripts/build-desktop.sh --dir  # 只出 .app，更快
```

- 走 electron-builder 的 identity 路径，**打包时**即签名（hardened runtime + `electron/build/entitlements.mac.plist`
  + 内嵌 Go 二进制纳签），**不送 Apple 公证**。
- 构建末尾自动打证据：`codesign --verify`（含内嵌二进制）、hardened runtime 标志、entitlements 键、
  内嵌 `zworkbench-go` 的签名状态。任何一条不过即 `exit 1`。
- 产物行带 `mtime`，用于区分「本次产物 vs 上次遗留」——`--dir` 的产物是 `.app`，而 `dist/` 下常还躺着上一次的 dmg。
- 与 `NOTARIZE` / `SIGN_CERT` **均互斥**（同时给直接报错退出）。

对比 `SIGN_CERT`（旧入口，保留但**仅 `--dir` 模式有效**）：它在打包**之后**用 `codesign --force --deep` 补签，
dmg 模式下签的是中间产物、包内仍是 unsigned（脚本会明确告警）。需要「打包即签名」请用 `SIGN_ID`。

签名链路已用 `SIGN_ID` 在本机实跑验证（自签证书，四项校验全过）；**公证本身尚未真跑过**（缺 Developer ID 证书）。
Windows 构建、自动更新仍不在本切片。

## 设计要点

- **多 tab 工作台**：`internal/domain/tabs.go` 是 tab 注册表，stock 只是其中之一。
- **本地鉴权**：Electron 启动生成一次性 token，经 URL query 注入前端，Go 中间件校验。
- **LLM Provider 层**：`internal/agent` 统一接口，现 OpenAI/DeepSeek stub，待接真实端点。
- **证据底座**：`internal/data` 先用 MemStore，Phase 2 换纯 Go SQLite 驱动。
- **Python 核心**：既有 `src/zworkbench`（CompositionOwner 证据层）可作可选 sidecar，详见架构文档 §4。
