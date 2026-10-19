---
doc-kind: design
authority: supporting
status: accepted
decided-by: zj
decided-at: 2026-10-15
references:
  - docs/designs/zw-go-electron-architecture.md   # 技术接线（进程模型/包结构/spawn），本文件不重复
  - docs/zj-adr/0015-go-full-pivot-supersedes-0013.md  # 运行时边界重新划界
  - docs/references/zw-vs-es-capability-matrix.md  # C01–C41 能力对照 canonical 来源（原 docs/plans 底稿经 1-6-1 退役、根目录临时稿经治理沉淀为长期 reference）
---

# ES 常驻 Tab 产品内容设计

> 状态：**已接受（2026-10-15 随路线图 1-3 收尾定稿）**
> 定位：本文件是 ES（easy-stock）产品内容作为 ZWorkbench 常驻 tab 的**产品内容层**长期设计实体。
> 技术接线（Electron↔Go 进程模型、包结构、spawn 机制、鉴权 token）归 [`zw-go-electron-architecture.md`](zw-go-electron-architecture.md)，本文件不重复；运行时偏离边界归 [`ADR 0015`](../../zj-adr/0015-go-full-pivot-supersedes-0013.md)。
> 落点说明（Q3）：本设计为路线图节点 `1-3-3` 决议指定的长期载体（design 文档，非 ADR）。

## 0. 摘要

把 easy-stock（ES）的 A 股投研**产品内容**作为 ZWorkbench 工作台的**常驻 tab** 之一，以加速 ZW 客户端 0→1 可用性；内容以**镜像 ES 的 Go/React 脚手架**方式落地（零翻译），随 `1-5` 切片全部交付。ZW 的可复核编码证据（C26/C28）保留为独立 `coding-evidence` tab。

> 定位订正（2026-10-19，zj 拍板）：ZW = **个人综合工作台**——编码证据与 ES 投研、LLM 对话等是并列能力面，多域并列是预期形态，不存在「稀释」问题。本文件原「证据核心不被稀释」表述基于旧定位（ZW=AI 编码工作台），已失效。

## 1. 背景与动机

- **正交定位（C01/C03）**：ZW = 个人综合工作台（2026-10-19 订正；编码证据、A 股投研、LLM 对话等能力面并列常驻 tab，旧口径「AI 编码任务的 durable 证据/编排」为历史表述）；ES = A 股 AI 投研桌面工作台。本设计只把 ES 的**产品内容**作为 ZW 工作台的常驻 tab，**不合并两项目核心逻辑**。
- **加速 0→1（动机①）**：原型阶段想快速 go through 桌面可用性；ES 已是成熟的 Go+Electron+React 投研工作台，镜像其脚手架比自研快得多。
- **对接 LLM Provider（动机②）**：现成本地 Agent 服务范式（OpenAI/DeepSeek Responses API），对应 ZW 的 Provider 层。
- **吸纳作起点再改形（动机③）**：stock 只是 ZW 多 tab 之一；先拿到 ES 产品能力，再逐步改写吸收。
- **许可证非门控（D1/D2）**：ZW 非商业意图、ES 内容 merge 进来作加速脚手架并随后改写，落在 PolyForm Noncommercial 1.0.0 的「非商业使用/修改/衍生」范围内，无需作者书面授权。

## 2. 已决议的对齐项（路线图 1-3，zj 拍板）

以下四项为 `1-3`「待决对齐项」的最终决议，2026-10-15 经 `decide` 落库：

| ID | 问题 | 决议 | 依据 |
|---|---|---|---|
| **Q1（1-3-1）** | 是否接受引入 Node/Electron 依赖（偏离零依赖 C32）？ | **接受**，登记为 tracked deviation；纯 Python 核心（`src/zworkbench`）保持零依赖、不被污染 | `desktop/` 已提交（1-1-1/1-1-2）证明桌面壳价值；依赖仅限桌面壳层 |
| **Q2（1-3-2）** | 首个 ES 风格 tab 选型：C08 个股分级研究 vs C07 行情总览？ | **选型无悬念**：C07 行情总览（1-5-3）与 C08 个股分级研究（1-5-7-2）**均已交付、并存、无需单选** | `1-5` 把两者都作为独立切片交付 |
| **Q3（1-3-3）** | 本草稿评审通过后落点（design/ADR 编号）？ | **以 design 文档形式落地为长期文档**（`docs/designs/`，非 ADR）；随 1-5 已交付的 C07/C08 归入对应 design 实体 | 本文件即该落点 |
| **Q4（1-3-4）** | Electron 如何拉起后端：spawn ui-host 子进程 vs 用户先跑再连 loopback？ | **A：Electron 主进程 spawn Go 二进制**（`app/cmd/server`）；原 A（spawn Python ui-host）被 `1-5` 推翻 | Go 全 pivot（B）后后端是 Go，不再 spawn Python ui-host；B（先跑再连 loopback）降级为冒烟兜底 |

> Q4 原 A 结论（spawn Python ui-host）已被 `1-5` 推翻；当前事实 = Electron spawn Go。详见技术架构文档 §3.1。

## 3. 偏离登记（C32 tracked deviation）

- **偏离项**：引入 Node/Electron（桌面壳层 `app/electron`）+ Go 运行时（`app/`）。
- **边界（B-pivot 后）**：
  - Go 运行时 = 零 **cgo 外部**依赖（`go.mod` 纯 stdlib 起骨架 + `modernc.org/sqlite` 无 cgo）；
  - Node/Electron 仅作 `app/electron` 桌面壳，**devDependency** 隔离，不进 ZW 核心；
  - Python 核心 `src/zworkbench` 仍 `pyproject.toml` `dependencies=[]`，零依赖不变。
- **守卫**：需在 `app/` 落地 `go.mod` 无 cgo 依赖 / `app/electron` 仅 devDependency 的静态断言（对应 `1-5-8` 后的零依赖守卫补全）。
- **登记位置**：本设计为长期记录；运行时边界重划见 `ADR 0015`。

## 4. Tab 内容清单（C07–C19 镜像到 Go）

所有 ES 内容 tab 以**镜像 ES 的 Go/React 脚手架**方式落地（零翻译）。tab 注册表在 `app/internal/domain/tabs.go`，前端 `app/web` 按 id 渲染组件。落地切片均属路线图 `1-5`，状态 completed。

| C 码 | ES 产品内容 | ZW tab id | 标题 | 落地切片 | 状态 |
|---|---|---|---|---|---|
| C07 | 行情/市场数据聚合（开盘啦/东财/新浪/财联社统一行情、K线、题材、涨停、资讯） | `stock-overview` | 行情总览 | 1-5-3 | ✅ completed |
| C08 | 个股/标的分级研究（量化速览/AI快速/标准/深度研判，分观察/新开仓/持仓） | `stock-research` | 个股分级研究 | 1-5-7-2 | ✅ completed |
| C09 | 题材/连板/情绪（超短连板梯队、趋势题材雷达、情绪周期识别） | `stock-limitup` | 超短连板 | 1-5-7-1 | ✅ completed |
| C12 | 大V/资讯自动复盘（雪球/淘股吧/微信自动同步、去重归档、今日共识） | `stock-review` | 大V复盘 | 1-5-7-3 | ✅ completed |
| C10 | 持仓管理/组合巡检（多持仓方案、AI 巡检、四维评分：逻辑35/结构25/风险25/策略15） | `portfolio-inspection` | 持仓巡检 | 1-5-7-4 | ✅ completed |
| C11 | AI 持仓优化/配仓（候选筛选、投资比较、程序配仓、原/目标同次复评） | `portfolio-optimization` | AI持仓优化 | 1-5-7-5 | ✅ completed |
| C19 | 知识库/游资心法（游资心法库、人物资料、Hermes 深度研读） | `trading-mastery` | 游资心法 | 1-5-7-6 | ✅ completed |
| C26 | 编码证据核心（CompositionOwner 单一 owner、safe-stop C28） | `coding-evidence` | 编码证据 | 1-5-6（B2：Go 重写 C26/C28，零 Python 进程，见 ADR 0016） | ✅ completed |
| — | LLM Provider 配置 / 设置 | `settings` | 设置 / LLM | 本工作台 | ✅ 内建 |
| — | 通用对话（Agent 入口） | `chat` | 对话 | 本工作台 | ✅ 内建 |

> 七个 ES 投研 tab（C07/C08/C09/C12/C10/C11/C19）对应路线图 `1-5-7` 的 6 个切片（C09/C08/C12/C10/C11/C19 各一微切片；C07 在 `1-5-3`）。`coding-evidence` 走 B2（ADR 0016）：C26/C28 用 Go 重写进 `internal/data` + `internal/evidence`，零 Python 进程，保留 ZW 差异化。

## 5. 内容接入范式

- **镜像而非翻译**：直接复用 ES 的 Go 领域服务 + React 组件骨架，零 Go→Python 翻译成本。种子数据经 `go:embed` 内置，离线可跑。
- **多源适配/回退（C36）**：行情类 tab 内置多数据源适配与回退（主源失败自动切次源），保证常驻可用。
- **前端富交互（C21）**：React + TypeScript 多 tab 工作台壳，左侧 tab 注册表按 `domain/tabs.go` 渲染；各 tab 独立组件经 `apiBase` 调本地 Go API。
- **本地证据快照**：研究结论/数据落地本地 SQLite（`modernc.org/sqlite` 无 cgo），表设计沿用 ES「版本化快照 + 来源/时间」思路。

## 6. 证据所有权（C26）

- ES 研究结论**接入 CompositionOwner 单一 durable owner**（C26），与编码任务证据并存、不冲突（C27）。
- `coding-evidence` tab 走 **B2**（ADR 0016）：C26/C28 已用 Go 重写进 `internal/data` + `internal/evidence`，零 Python 进程；`src/zworkbench`（Python 实现）仅保留为 git 历史 / 参考，不再被 `app/` 接线。
- 研究类 tab 的结论可追溯、可复核，回放/审计口径统一进 owner。

## 7. 产品定位（2026-10-19 订正，原「定位护栏」）

- **现行定位（zj 拍板）**：ZW = **个人综合工作台**。编码证据（C26/C28，`coding-evidence` tab）与 ES 投研内容（各常驻 tab）是**并列能力面**，不存在「谁稀释谁」。
- 原护栏三条（ES=常驻 tab / 证据核心第一公民 / 不被稀释）基于旧定位「ZW=AI 编码工作台」，随定位订正失效；历史原文见本文件 git 历史与路线图 1-7 决策记录。
- 边界仍然成立的是**工程隔离**事实：各能力域包级隔离（`internal/datasource` 与 `internal/evidence` 零耦合），能力并列不等于逻辑耦合。

## 8. 许可证（PolyForm NC）

- ZW 非商业意图下，merge/改写 ES 内容落在 PolyForm Noncommercial 1.0.0 许可范围（D1/D2）。
- 软性建议（非门控）：merge 进来的 ES 派生文件保留 ES 版权/许可证声明并注明变更；个人非商业使用无需作者书面授权。

## 9. 与相邻文档关系

| 文档 | 职责 | 本文件关系 |
|---|---|---|
| `zw-go-electron-architecture.md` | 技术架构（进程模型、包结构、spawn、token、构建） | 本文件引用其 §3，不重复 HOW |
| `ADR 0015` | 运行时边界重新划界（supersede 0013） | 偏离边界的权威来源 |
| `zw-electron-es-tab-plan-2026-10-13.md`（已退役） | 历史草稿（决策沿革） | 已于 1-6-1 退役删除；结论已迁移至本文件 + zw-go-electron-architecture.md + ADR 0015/0016 |
| `docs/references/zw-vs-es-capability-matrix.md` | C01–C41 能力对照（canonical） | C01–C41 对照的长期 reference 来源；C 码语义以本文件 §4 表格为准 |

## 10. 状态与后续

- **状态**：已接受。七类 ES 投研 tab + `coding-evidence` 均随 `1-5` 交付（completed）；路线图 `1`（ZW → Electron 客户端 + ES 常驻 Tab）已闭环。
- **后续（1→100 阶段，非本设计范围）**：
  - 各 tab 业务深度扩展（如 C08 四级研判的完整 AI 链路、C10 四维评分的实算）。
  - `app/` 零依赖静态守卫落地（对应 §3 守卫项）。
  - B2 移植路线（把 CompositionOwner/safe-stop 用 Go 重写进 `data`+`api`，单运行时统一）按需推进。
