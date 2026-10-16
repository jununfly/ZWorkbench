# ZWorkbench → Electron 客户端 + ES 常驻 Tab 计划草稿

> 状态：**已闭环（archived，仅作决策沿革保留）** ｜ 创建：2026-10-13 ｜ 末次变更：2026-10-15（§9 收口：路线图 `1` 及其下全部 **40** 个节点均 `completed`，含 5 个顶层子节点）
> 目标：以 easy-stock（ES）为参照，加速 ZW 产品可用性 —— 先把 ZW 客户端改造成 Electron 桌面应用，再把 ES 的产品内容作为本工作台常驻 tab 之一。
> 节奏：**微进度、小切片**，每个切片带可验收退出条件，避免一次性大改写。
> ⚠️ 治理提示：本计划存于 `docs/plans/`（2026-09-27 退役态）。**2026-10-14 zj 选 B（Go 全 pivot）后，本计划的结论已迁移至 `docs/designs/zw-go-electron-architecture.md`（已接受）+ `docs/zj-adr/0015`（supersedes 0013）+ `docs/zj-adr/0016`（B2 提前，supersedes 0015 部分条款）**，并落地为路线图节点 `1-5`；ES 常驻 Tab 的**产品内容层**决策（Q1–Q4、C07–C19 清单、C32 偏离登记）已于 2026-10-15 落为 [`docs/designs/pd-es-resident-tabs.md`](../designs/pd-es-resident-tabs.md)（路线图 1-3 收尾，非 ADR）。本草稿保留作决策沿革，**勿作新工作的依据**；新工作一律以上述 design/ADR 与路线图为准。
> ⚠️ **§4 的 A'（merge-then-adapt 进 Python）与 §3 的「Phase 1 spawn Python ui-host」已被 B 推翻**：ES 内容接入改为直接镜像 ES 的 Go/React 脚手架（零翻译），Electron 改 spawn Go 二进制。详见 §8。
> ✅ **2026-10-15 闭环**：路线图 [`roadmap-zw-electron-es-tab.json`](roadmap-zw-electron-es-tab.json)（事实源）+ 同名 `.md`（render 视图）顶层节点 `1` 及 `1-1`~`1-5` 全部 `completed`。详见 §9。

## 0. 范围与前提（先读）

- ZW 当前事实基准 = v1 **Codex-only 回退基线**（C38），DSH 主 Harness = `target/unknown`（C39），真实写/Push 仍门控未证明（C29/C40）。本计划只包装/扩展现有 v1，不假设未实现能力。
- 两者定位正交（C01/C03）：ZW=AI 编码任务的 durable 证据/编排；ES=A 股 AI 投研桌面工作台。本计划把 ES 的**产品内容**作为 ZW 工作台的常驻 tab，**不是**合并两项目核心逻辑。
- **许可证不再是门控**（见 §1 决策记录 D1/D2）：ZW 非商业意图、ES 内容 merge 进来作加速脚手架并随后改写 —— 落在 PolyForm Noncommercial 1.0.0 的「非商业使用/修改/衍生」许可范围内，无需作者书面授权，亦无需 ZW 先声明 LICENSE。

## 1. 决策记录（2026-10-13，zj 拍板）

| ID | 决策 | 依据 | 对计划影响 |
|---|---|---|---|
| D1 | **不做 P0.1**（ZW 不引入 LICENSE） | ZW 非商业意图，无需声明许可证 | 移除 P0.1；ZW 仓库维持现状（默认 all-rights-reserved，对个人非商业项目无碍） |
| D2 | **不做 P0.2**（merge ES 内容进来、作开发加速、随后改掉） | 非商业场景下 PolyForm NC 已许可使用/修改/衍生；merge 内容会改写故非「原样分发」 | 移除 P0.2 硬门；Phase 2 不再依赖授权；R1 降为软性署名建议 |
| D3 | ES 接入默认方向 = **merge-then-adapt**（见 §4） | 用户明确「merge 进来加速 + 后续改掉」 | Phase 2 起点从「自研参考 B」调整为「带 ES 脚手架的适配改写」 |

> 软性建议（非门控）：merge 进来的 ES 派生文件保留 ES 的版权/许可证声明并注明变更（PolyForm NC 要求），属好习惯。

## 2. 总体路径

```
Phase 1  Electron 化 ZW 客户端（薄壳，零 UI 重写）   ──▶ 第一个可交付：ZW 变桌面应用
Phase 2  ES 产品内容作为常驻 Tab（merge-then-adapt）
```

## 3. Phase 1 — Electron 化 ZW 客户端（薄壳优先）

设计原则：复用现有 `ui-host`（ADR 0003 server-rendered HTML，C21）与 loopback 宿主（C22），**不重写 UI**，仅加 Electron 外壳。

| 切片 | 动作 | 退出条件（可验收） |
|---|---|---|
| 1.1 | 引入 Electron 薄壳：main 进程启动 `zworkbench ui-host`（或打包的 Python），BrowserWindow 指向 loopback URL | `npm start` 打开桌面窗口，显示现有 home/task-detail/record-view 三视图 |
| 1.2 | 加原生菜单/托盘/单实例锁；保留 CLI（`zworkbench` 命令仍可用，不回归） | 菜单可触发 ui-host；CLI 行为不变 |
| 1.3 | 打包：electron-builder 产出 macOS/Windows 安装包，解决「无桌面安装包」缺口（C04/C34） | DMG/EXE 安装后零配置启动，等价于 ES 的分发体验 |
| 1.4 | 将「引入 Node/Electron 依赖」登记为**显式偏离零依赖（C32）**的 tracked deviation（写 design/ADR 备注），保证纯 Python 核心不被污染 | deviation 记录存在；`pyproject.toml` 仍 `dependencies=[]` |

> 此阶段不动 ZW 的证据核心（CompositionOwner，C26）与安全模型（safe-stop，C28）。Electron 只是宿主，不是第二个 owner。

## 4. Phase 2 — ES 产品内容作为常驻 Tab（merge-then-adapt）

**接入方式**（D3 后默认 = 方案 A'）：

| 方案 | 做法 | 优劣 | 关联对比点 |
|---|---|---|---|
| A' merge-then-adapt（**默认**） | 把 ES 的 A 股研究功能/数据适配/分析逻辑作为**初始脚手架**带进 ZW（Python 后端 + 新 tab），随后迭代改写、逐步并入 CompositionOwner 单一 owner | 最快拿到 ES 产品能力、加速可用性；需处理语言差异（ES=Go/React，ZW=Python）与随后改写成本 | C20,C26,C32,C36 |
| B 自研参考 | 在 ZW 重做 ES 功能，仅参考交互、不拷代码/品牌 | 统一技术栈、天然接入 owner；工作量大、慢 | C26,C36 |
| C 外链视图 | tab 用 webview 指向独立运行的 ES 实例 | 零 merge；但 ES 需单独安装运行，不算「merge 内容」 | C22 |

**推荐起点 = A'（merge-then-adapt）**，契合你「merge 进来加速、随后改掉」的指令；B/C 仍可作局部兜底（如某 tab 暂用外链验证数据）。

微进度切片（以 A' 为前提）：

| 切片 | 动作 | 退出条件 |
|---|---|---|
| 2.1 | 在 Electron 多视图中加「常驻 tab 容器 + 路由」，先空 tab 占位 | 桌面应用内出现可切换的常驻 tab 位 |
| 2.2 | 最小切片：先 merge/适配**一个** ES 风格 tab 原型（建议「行情总览」C07 或「个股分级研究」C08，最独立、价值高），验证数据接入（C36 多源适配/回退）与本地证据快照 | 该 tab 在应用内常驻可用，数据来自本地快照 |
| 2.3 | 证据层对齐：研究结论接入 CompositionOwner 单一 owner（C26），与编码任务证据并存 | 证据可追溯、不与编码 owner 冲突（C27） |
| 2.4 | 逐步补齐其余 tab（连板 C09 / 题材雷达 C09 / 大V复盘 C12 / 持仓巡检 C10 / AI 优化 C11 / 游资心法 C19），每 tab 一个微切片；merge 进来的 ES 脚手架在此阶段被逐步改写吸收 | 逐个 tab 常驻可用 |
| 2.5 | 清理：移除仍残留的「原样 ES 派生」片段，确认 ES 声明/变更注明到位（D2 软性建议） | 无未注明来源的 ES 派生代码 |

## 5. 风险登记

| ID | 风险 | 触发 | 影响 | 缓解 | 残余 | 责任方 |
|---|---|---|---|---|---|---|
| R1 | 署名/合规（**已降级**） | merge ES 派生代码未保留其版权/许可证声明 | 合规瑕疵（非商业下非致命） | D2 软建议：保留 ES 声明 + 注明变更 | 低（非商业） | zjj |
| R2 | 双技术栈膨胀 | A' 阶段带进 ES（Go/React）代码未及时改写成 Python | 体积大、维护分裂（C20/C32） | 2.4/2.5 强制改写吸收；边界隔离 | 中（A'） | zj |
| R3 | 证据模型冲突 | ES 模块级 SQLite 与 CompositionOwner 单一 owner 并存（C26） | 回放/审计口径分裂 | 2.3 统一进 owner | 低（A'） | zjj |
| R4 | 产品定位稀释 | 加 A 股研究扩展 ZW 核心边界（C01/C03） | 焦点模糊、证据核心被弱化 | 明确为「工作台常驻 tab」而非核心 | 中 | zj |
| R5 | 成熟度假设误用 | 误依赖 DSH 主 Harness（C39）或真实写门（C29/C40） | 计划悬空 | 仅包装现有 v1，不假设未实现能力 | 低 | zjj |
| R6 | 文档治理 | 本计划存于退役态 docs/plans | 结论丢失/断链 | 评审通过后转 design/ADR 并删本草稿 | 低 | zjj |

## 6. 未决 / 对齐项（需 zj 决策）

> **2026-10-15 更新：Q1–Q4 全部已拍板（路线图 `1-3-1`~`1-3-4` 均 completed），本节转为决策沿革记录。**

| # | 待决项 | 结论 | 落点 |
|---|---|---|---|
| 1 | ZW 是否引入 Node/Electron 依赖（偏离零依赖 C32）？ | **接受**，但边界收窄为「Node/Electron 仅 `app/electron` + `app/web`；Go 运行时零 cgo 外部依赖；Python 核心仍零依赖」 | 路线图 `1-3-1`、`1-1-4`；ADR 0015 → 0016 |
| 2 | ES 内容接入方式：A' merge-then-adapt / B 自研参考 / C 外链？ | **选 B 的 B2 变体**：镜像 ES 的 Go/React 脚手架（零翻译），证据核心（C26/C28）用 Go 重写进 `app/`，**零 Python 进程** | 路线图 `1-3-2`、`1-5`、`1-5-6`；ADR 0015 + 0016 |
| 3 | 第一个 ES 风格 tab 选哪个？ | **C07 行情总览 + C08 个股分级研究 同时落地**，选型无悬念 | 路线图 `1-3-2`、`1-2-2`；`StockTab.tsx` / `ResearchTab.tsx` |
| 4 | docs/plans 退役态下本草稿落点？ | **不删**，保留作决策沿革；结论分别落 `docs/designs/zw-go-electron-architecture.md`、`pd-es-resident-tabs.md` 与 ADR 0015/0016 | 路线图 `1-3-3` |

## 7. 微进度下一步（最小可跑）

- **立刻可做、零阻塞**：**1.1**（Electron 薄壳起现有 `ui-host` UI）。不触碰 ES、不触碰核心，立刻让 ZW「变成桌面应用」，对应你「加速可用性、先爬坡」的诉求。
- Phase 2（A'）在 Phase 1 的 1.1–1.3 跑通后即可并行启动 2.1/2.2，不再有许可证前置。

---

## 8. 决策变更：B Go 全 pivot（2026-10-14 追加，推翻 §3/§4 路径）

> 本条记录一次**方向级**决策变更。它使本草稿 §3（Phase 1 spawn Python ui-host）与 §4（A' merge-then-adapt 进 Python）失效，结论迁移至 `docs/designs/zw-go-electron-architecture.md`（已接受）与 `docs/zj-adr/0015`（supersedes 0013）。路线图同步新增节点 `1-5`。

### 8.1 决策内容

| 项 | 原方案（本草稿） | 新方案（B，2026-10-14） |
|---|---|---|
| 主运行时 | Python（`ui-host` server-rendered HTML） | **Go**（`app/`，纯 stdlib 起骨架） |
| 桌面壳 | Electron 薄壳 spawn Python ui-host | Electron 壳 spawn **Go 二进制** |
| 前端 | server-rendered HTML（C21） | **React + TypeScript** 富前端（镜像 ES C21） |
| ES 内容接入 | A' merge-then-adapt 翻成 Python | **直接镜像 ES 的 Go/React 脚手架**（零翻译） |
| 偏离边界（C32） | Python 运行时零依赖；Node/Electron 仅 desktop/ | Go 运行时零 cgo 外部依赖；Node/Electron 仅 app/electron；Python 仍零依赖（sidecar） |

### 8.2 推翻 ADR 0013 的前提

ADR 0013 的两个前提（Python 零依赖核心即运行时 + Electron 薄壳 spawn Python）被 B 同时推翻。**ADR 0015** 已 `supersedes` 0013 并重新划界。

### 8.3 `desktop/` + Python ui-host 壳的处理

已提交的 `desktop/`（1-1-1/1-1-2 完成、1-1-3 打包 in_progress）转入 **retired**：代码保留 git 历史、停止新开发、不再打包 Python 壳。新打包目标 = Go 二进制（归 `1-5-2`）。路线图节点 `1-1`（及子节点）经 `1-5` 的 `supersedes` 边 + retired 决策标注为历史。

### 8.4 落地切片（路线图 `1-5`，8 个子节点）

> **2026-10-15 更新：8/8 全部 completed**（证据见路线图 JSON 各节点 `notes`）。`1-5-6` 的路线已在落地过程中由 B1 改为 B2，见下。

| 节点 | 切片 | 状态 | 关键证据 |
|---|---|---|---|
| `1-5-1` | 冻结 desktop/ Python-ui-host 壳（retired） | completed | `desktop/` 停更、保留 git 历史；打包目标改为 Go 二进制 |
| `1-5-2` | Go 骨架 `app/` 跑通（go build + go run + 前端多 tab 壳） | completed | `app/go.mod`（go 1.26，仅 modernc/sqlite 等纯 Go 依赖）、`cmd/server`、`web/` React 壳 |
| `1-5-3` | 首个真 tab：镜像 ES 行情总览 C07 最小切片 | completed | `StockTab.tsx` + `GET /api/stock/overview`（`router.go:59`） |
| `1-5-4` | 接真实 LLM Provider（OpenAI/DeepSeek，动机②） | completed | `internal/agent/provider.go`（`openAICompatibleClient`，OpenAI/DeepSeek 兼容 `/chat/completions`） |
| `1-5-5` | 本地证据底座 SQLite（modernc.org/sqlite 无 cgo）+ 预留 CompositionOwner 字段 | completed | `internal/data/store_sqlite.go`（`modernc.org/sqlite`，无 cgo） |
| `1-5-6` | coding-evidence：**B1 sidecar → 改 B2** 用 Go 重写 C26/C28 进 app，零 Python 依赖 | completed | `internal/evidence/`（evidence.go / owner.go / approval.go / owner_test.go / router_evidence.go）+ `CodingEvidenceTab.tsx`；ADR 0016 |
| `1-5-7` | 其余 tab（C08/C09/C10/C11/C12/C19），每 tab 一微切片 | completed | 5 个 domain 包 + 5 路由端点 + 5 前端 Tab；`/api/tabs` 返 10 tab；各端点 `fallback=true`（本地快照生效）、401 鉴权正常 |
| `1-5-8` | ADR 0015 supersede ADR 0013 | completed | `docs/zj-adr/0015-go-full-pivot-supersedes-0013.md`（accepted）；随后 `0016` supersede 其 B1/sidecar 条款 |

### 8.5 风险与缺口（B 特有）

> **2026-10-15 更新**：第 2 项（go build 验证）已闭合；第 1 项（Go 侧零依赖守卫）**仍 open**，见下。

- ~~`app/` 骨架尚未在本机 `go build` 验证~~ → **已闭合**：`app/` 已在本机构建并打包（`app/electron/dist/ZWorkbench-0.0.1-arm64.dmg`，104MB，内嵌 `Resources/bin/zworkbench-go`）；**启动实测 PASS**（`#root childCount=1`、`/api/tabs` 返 10 tab）。macOS 首次启动拦截定性＝**XProtect**（"包含恶意软件"文案，无用户侧绕过）；治本＝公证（需 Developer ID 证书，$99/年，自用不需要）。
- ⚠️ **仍 open**：Go 侧零依赖守卫尚未建立（Python 侧有 `test_zero_dependency_guard.py`，Go 侧无对应物）。当前仅靠 `build-desktop.sh` 的 `CGO_ENABLED=0` 与各包注释约束，**没有静态断言**守 `go.mod` 无 cgo 依赖 / `app/electron` 仅 devDependency。建议落一个 `app/` 内的守卫测试（解析 `go.mod` 断 require 列表 + 断言 `CGO_ENABLED=0` 可编译）。

### 8.6 参照

- 架构提案（已接受）：`docs/designs/zw-go-electron-architecture.md`
- ES 常驻 Tab 产品内容层：`docs/designs/pd-es-resident-tabs.md`（Q1–Q4 + C07–C19 + C32 偏离登记）
- 新 ADR：`docs/zj-adr/0015-go-full-pivot-supersedes-0013.md`；`docs/zj-adr/0016-coding-evidence-b2-pulled-forward.md`（supersedes 0015 的 B1/sidecar 条款）
- 路线图节点：`1-5`（含 8 切片）、根节点决策 D4/D5、supersedes 边 e13/e14
- 路线图事实源：[`roadmap-zw-electron-es-tab.json`](roadmap-zw-electron-es-tab.json)（只经 `zj-roadmap-driven` CLI 读写）+ [`roadmap-zw-electron-es-tab.md`](roadmap-zw-electron-es-tab.md)（render 视图）
- 旧决策保留：D1/D2/D3（许可证/merge 授权/方向）在 B 下仍有效（仅实现路径变）；Q4（spawn ui-host）被 B 推翻，见 `1-3-4` 决策。

---

## 9. 收口状态（2026-10-15）

### 9.1 路线图终态

| 节点 | 标题 | 状态 |
|---|---|---|
| `1` | ZW → Electron 客户端 + ES 常驻 Tab（顶层） | **completed** |
| `1-1` | Phase 1 — Electron 化 ZW 客户端（薄壳） | completed（被 `1-5` supersede，`desktop/` retired） |
| `1-2` | Phase 2 — ES 产品内容常驻 Tab（A'） | completed（A' 路径被 B 取代；子节点 2026-10-15 经代码核验补标 completed） |
| `1-3` | 待决对齐项 Q1–Q4 | completed |
| `1-4` | 全量测试套件挂死排查与修复 | completed |
| `1-5` | Phase 3 — Go 全 pivot（B） | completed（8 个直接子节点全 completed，见 §8.4；另有 `1-5-6-1..3`、`1-5-7-1..6` 更深切片均 completed） |

> 事实源 `roadmap-zw-electron-es-tab.json` 最后更新 `2026-10-15 23:11:49`，**40/40 节点 `completed`**；render 视图 `roadmap-zw-electron-es-tab.md` 全节点 `[x][X+]`。

### 9.2 ES 常驻 Tab 交付清单（`internal/domain/tabs.go` 注册 10 tab）

| ES 对照点 | Tab | 后端 | 前端 |
|---|---|---|---|
| C07 | 行情总览 | `GET /api/stock/overview` | `StockTab.tsx` |
| C08 | 个股分级研究 | `GET /api/stock/research` | `ResearchTab.tsx` |
| C09 | 超短连板 | `/api/stock/limitup` | `LimitUpTab.tsx` |
| C10 | 大 V 复盘 | `/api/stock/review` | `ReviewTab.tsx` |
| C11 | 持仓巡检 | `/api/portfolio/inspection` | `InspectionTab.tsx` |
| C12 | 持仓优化 | `/api/portfolio/optimization` | `OptimizationTab.tsx` |
| C19 | 游资心法 | `/api/mastery` | `MasteryTab.tsx` |
| C26/C28 | coding-evidence（B2 Go 重写） | `internal/evidence/*` | `CodingEvidenceTab.tsx` |
| — | settings 设置 / LLM | `internal/config` | `SettingsTab.tsx` |
| — | chat 对话（1-5-4 真实 Provider） | `internal/agent/provider.go` | `ChatTab.tsx` |

ES 镜像 tab 全部走「`go:embed` 种子快照 + C36 FallbackChain + 前端组件」三段式；无真实数据源时 `fallback=true`，本地快照生效。

### 9.3 遗留 / open（不要误读为已完成）

1. **Go 侧零依赖守卫未建立**（§8.5）——唯一显式 open 的工程缺口。
2. **公证未做**：dmg 已产出、自签 + hardened runtime + entitlements 签名成立、启动实测 PASS；但 macOS XProtect 仍会拦截，正式分发需 Developer ID 证书 + notarize（`NOTARIZE=1` 门控已在 `app/scripts/build-desktop.sh` 就位，待证书）。
3. **前端未跑生产构建的类型门禁**：`1-5-7` 沿用既有模式、类型一致，但 `npm install` + Vite build 未在本机执行（`npx tsc --noEmit` 可作为替代验证）。
4. **本草稿与路线图仍留在退役态 `docs/plans/`**：按 2026-09-27 治理约定应「结论沉淀后即删」。现因作决策沿革保留，是否删除需 zj 显式决定。
