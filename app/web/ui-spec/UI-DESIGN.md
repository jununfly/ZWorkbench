# UI-DESIGN.md — ZWorkbench Web 界面全量重写（S4 canonical）

design_schema_version: 1.0.0
revision: c930f65a7b62be701bf15209f285577caa842a258e2c0ee4044ba3eb2ca8a0ae
input_revision: UI-BRIEF.md@157d2665 + S3 direction_choice=card-e
source: zagentic (zj-ui-design-system S4)
direction_choice: card-e  (Material Design 3 取向，seed `#6750A4`，hue 可派生，明暗同源)

> 本文件为 canonical 产物，由 `zj-ui-design-system` 写出。组件 catalog 字段值由本仓库拥有；
> 下游 S5/S6 只允许引用本 catalog 内组件，不得注册未声明来源组件，不得引入外部 runtime 替代 catalog。
> 约束继承：A股数据层 涨=红 / 跌=绿 为内容层硬规则，与主题主色无关。

## direction_choice（来自 S3 Human gate）
- 体系：Material Design 3（material.io），视觉参考、不复制组件。
- 种子色 seed：`#6750A4`（紫）。**hue 可换**：任一主色即自动派生全套 tonal palette，明暗主题同源。
- 字体：`Roboto`（Apache-2.0）；代码 `Roboto Mono`（Apache-2.0）。
- 取舍接受：规范全、动效体系完整、明暗主题维护成本低；默认观感偏 Google 系、个性弱（已为 zj 接受）。

## tokens

### typography（Roboto / Roboto Mono，Apache-2.0）
- 中文字形回退：`"PingFang SC", "Microsoft YaHei", "Noto Sans SC"`。
- 字号/行高（M3 类型尺度，单位 px）：
  - title-lg 22/28 (500) — 页标题
  - title-md 16/24 (500) — 区块标题
  - title-sm 14/20 (500) — 卡片标题
  - body-lg 16/24 (400)
  - body-md 14/20 (400) — 默认正文
  - label 12/16 (500)
  - code 13/20 (400, Roboto Mono)
- 不引入网络字体运行时：Roboto 以系统/本地可用字体栈引用，缺失时回落系统无衬线，不阻断。

### color — M3 tonal palette（由 seed `#6750A4` 派生）
浅色主题（primary deliverable）：
- primary 40 `#6750A4`（主色 / 强调 / 链接）
- on-primary `#FFFFFF`
- primary-container 80 `#D0BCFF`；on-primary-container 10 `#21005D`
- surface 99 `#FFFBFE`；on-surface 10 `#1D1B20`
- surface-variant 90 `#E7E0EC`；on-surface-variant 30 `#49454F`
- outline 50 `#79747E`（仅边框，非文本）
- 语义色（A股内容层硬规则）：
  - up（涨/红）`#cf1322`；on-up 白
  - down（跌/绿）`#389e0d` — **仅用于大字（≥24px）与非文本（柱/点）**
  - down-text（跌/绿 正文）`#1b7d2e` — 正文字号（<18px）下跌专用，contrast 5.225 达标
  - 注：up 红 `#cf1322` 正文已达标（5.434），无需深红变体。

深色主题（M3 同源派生，prototype 以浅色优先；如需深色即启用，无需重设计）：
- primary 80 `#D0BCFF`；on-primary 20 `#381E72`
- surface 6 `#1D1B20`；on-surface 90 `#E6E1E5`
- surface-variant 30 `#49454F`；on-surface-variant 80 `#CAC4D0`
- outline 60 `#938F99`
- up/down 在深底各取更高 tonal stop 以保 contrast（S6 preview 验证时定稿）。

### spacing（M3 4dp 基线）
- 4 / 8 / 12 / 16 / 24 / 32 / 48（px）。默认组件内距 12–16，区块间距 24。

### density
- 默认 comfortable（列表行高 44px）；A股长页面表格提供 compact 变体（行高 36px）。

### radius（M3 shape）
- sm 8 / md 12 / lg 16–28 / pill 999（px）。

### motion（M3 标准缓动）
- 标准缓动 `cubic-bezier(0.2, 0, 0, 1)`；时长：enter 300 / exit 200 / emphasized 400 / expressive 500（ms）。
- 导航展开/折叠 200–300ms；hover/focus ring 即时。

## component catalog（已注册，source 声明，下游仅可引用）
| 组件 | 来源 | 状态 | 说明 |
|---|---|---|---|
| AppShell | zj-ui catalog（in-house React + CSS vars） | stable | 左侧固定栏 + 可滚动内容区 |
| Sidebar / NavRail | zj-ui catalog | stable | 7 个一级项 |
| NavItem（一级） | zj-ui catalog | stable | 当前页：不同背景色 + 图标高亮 |
| NavGroup（二级折叠） | zj-ui catalog | stable | 默认折叠，点击展开（如 主题→A股投研） |
| Page | zj-ui catalog | stable | 滚动容器（A股投研长页） |
| Card | zj-ui catalog | stable | surface 容器 |
| DataTable（高密度变体） | zj-ui catalog | stable | 行高 44/36，承载 A股行情/持仓/复盘 |
| Tabs（页内二级） | zj-ui catalog | stable | A股投研 内分区 |
| Badge / Pill（语义涨跌） | zj-ui catalog | stable | up 红 / down 绿 |
| Button（text/contained/tonal） | zj-ui catalog | stable | — |
| TextField / Select | zj-ui catalog | stable | 表单输入 |
| List / ListItem | zj-ui catalog | stable | chat 历史、evidence 事件流 |
| StatusChip | zj-ui catalog | stable | 编码证据生命周期态（created/running/waiting_approval/recovering/completed/failed/safe_stopped） |
| ExpandablePanel | zj-ui catalog | stable | 复盘/研究分区展开 |
| Icon | Material Symbols（Apache-2.0）inline-SVG 派生集 | stable | 不引入 icon font 运行时 |

> 实现边界：catalog 全部以**手写 React + CSS 变量**实现，**不合并 @material/web 等外部 runtime**（避免 catalog 事实源漂移，并满足 brief「不引入重型新运行时依赖」）。adapter（最终 app/web 代码）只投影这些 tokens，不持有 catalog 字段值。

## forbidden combinations
- 不得用 up-红 表达下跌、down-绿 表达上涨（A股约定硬约束）。
- 不得把 primary 铺满大面积 surface（M3 准则：primary 用于容器/强调，不用于整页背景）。
- 正文（<18px）下跌须用 `down-text #1b7d2e`，不得用 `#389e0d`。
- 不得在 catalog 外注册/新增组件；adapter 只投影。
- 不得引入外部组件 runtime 替代 catalog。

## tradeoffs
- 接受「Google 系观感、个性弱」换取规范完整、动效成熟、明暗同源低成本维护。
- 接受手写组件（非 Material Web）换取零额外运行时、可控、契合现有 React 外壳。
- 跌绿为正文另设深绿 token，增加 1 个语义变量，但保证 WCAG 不降级。

## provenance / license
- Material Design 3 规范与 material-components — Apache-2.0；Roboto / Roboto Mono — Apache-2.0；Material Symbols — Apache-2.0。仅作视觉参考，组件手写。来源 `https://m3.material.io`。
- 全部参考 license 已知，无 quarantine。

## contrast verification（S4 硬门槛，达标方可落盘）
| 配对 | 对比度 | 判定 |
|---|---|---|
| on-primary #FFF on primary #6750A4 | 6.441 | OK |
| primary #6750A4 on surface #FFFBFE | 6.282 | OK（链接/强调文本） |
| on-surface #1D1B20 on surface #FFFBFE | 16.654 | OK |
| on-surface-variant #49454F on surface | 9.113 | OK |
| outline #79747E on surface | 4.441 | 边框专用（非文本），可接受 |
| on-primary-container #21005D on #EADDFF | 13.319 | OK |
| up #cf1322 on surface | 5.434 | OK（涨红正文） |
| down #389e0d on surface | 3.377 | 仅大字/非文本 |
| down-text #1b7d2e on surface | 5.225 | OK（跌绿正文） |

> 无对比度不达标被静默替换的情况；down #389e0d 正文不达标以新增 `down-text` token 解决，而非改动约定色。
