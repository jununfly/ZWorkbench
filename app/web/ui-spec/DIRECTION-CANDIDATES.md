# DIRECTION-CANDIDATES.md — S3 方向候选（non-canonical，未选定）

> 本文件为 S3 方向候选工作稿，**不是 canonical 产物**。只有 zj 在 Human gate 选定后，
> `direction_choice` 才会写入 canonical `UI-DESIGN.md`。本稿参考为 MIT / Apache-2.0 license，无 quarantine。
> 约束继承：A股数据层 涨=红(#cf1322) / 跌=绿(#389e0d) 为内容层规则，与主题主色无关，各卡均遵守。

## card-a — 中后台蓝（Ant Design 取向）

- 色彩：主色 Ali Blue `#1677ff`；表面 `#ffffff` / `#f5f5f5`；文字 `#000000 / rgba(0,0,0,.65)`；边框 `#f0f0f0`。
- 字体：系统字体栈 `system-ui / -apple-system / "PingFang SC"`；代码 `ui-monospace`。
- 密度：中（默认 padding 12–16px，列表行高 ~40px）。
- 动效：轻量（hover 0.2s，折叠/展开 0.2s ease，无大位移）。
- 适用：信息密集的后台/工作台，组件语义明确、认知负担低。
- 取舍：最"企业感"、稳，但略保守；与现有 React 生态亲和，落地成本最低。
- 来源 / license：Ant Design 5 设计语言（仅作视觉参考，不复制组件）。Ant Design — MIT。`https://ant.design`

## card-b — 开发者中性灰（GitHub Primer 取向）

- 色彩：主色 GitHub Blue `#0969da`；表面 `#ffffff` / `#f6f8fa`；边框 `#d0d7de`；文字 `#1f2328`。
- 字体：`-apple-system / "Segoe UI" / "PingFang SC"`；等宽 `ui-monospace / SFMono` 用于证据/日志区。
- 密度：偏高（紧凑列表，行高 32–36px，适合长数据表与审计流）。
- 动效：极克制（仅 hover、focus ring；无展开动画）。
- 适用：偏开发者工具、长表格 / 日志 / 身份链，扫读效率最高。
- 取舍：朴素、可信赖，视觉个性弱；最贴合「编码证据」审计气质。
- 来源 / license：GitHub Primer 设计系统。Primer — MIT。`https://primer.style`

## card-c — 极简近单色（Geist / Vercel 取向）

- 色彩：近单色；主色低饱和 `#0070f3` 或近黑 `#111111`；大量留白；语义色 A股红绿。
- 字体：`Geist Sans` / `Inter`（MIT）；代码 `Geist Mono`。
- 密度：偏低（大留白，区块间距 24–32px），更"现代感"。
- 动效：细腻（subtle fade/scale，组件入场上浮 4px）。
- 适用：想让产品显"设计感强、轻"，弱化企业感。
- 取舍：好看但信息密度低，A股长页面需更多滚动；与"密集工作台"略有张力。
- 来源 / license：Geist (Vercel) 字体与 Vercel 设计取向。Geist — MIT；Inter — MIT。`https://vercel.com/geist`

## card-d — 企业超密蓝（IBM Carbon 取向）

- 色彩：主色 Blue 60 `#0f62fe`；hover Blue 70 `#0043ce`；表面 White `#ffffff` / Gray 10 `#f4f4f4`；边框 `#e0e0e0`；文字 `#161616`（主）/ `#525252`（次）。
- 字体：`IBM Plex Sans`（SIL Open Font License 1.1，自由可用，非 quarantine）；代码 `IBM Plex Mono`。
- 密度：高（默认表格行高 32px 紧凑、组件间距 16px 网格、专为超长数据表设计）。
- 动效：productive 动效体系（位移短、缓动 `carbon` 标准曲线，企业感、克制；另有 expressive 可选但默认不用）。
- 适用：高密度数据工作台，A股长页面（行情/持仓/复盘表）天然契合，无障碍达标最严。
- 取舍：最"工程化"、表格体验行业顶级，但视觉个性偏冷、观感偏"老牌企业软件"。
- 来源 / license：IBM Carbon 设计系统 — Apache-2.0；IBM Plex 字体 — SIL OFL 1.1。`https://carbondesignsystem.com`

## card-e — 规范动态紫（Material Design 3 取向）

- 色彩：M3 由 seed 生成 tonal palette；基线 seed 紫 Primary `#6750A4`、on-primary `#ffffff`、surface `#FFFBFE`、surface-variant `#E7E0EC`、outline `#79747E`；**hue 可换**（任挑一个主色即自动派生全套中性/容器色，明暗主题同源）。
- 字体：`Roboto`（Apache-2.0）；代码 `Roboto Mono`。
- 密度：中（M3 支持 comfortable/compact 双密度，默认 comfortable；列表行高可调）。
- 动效：M3 完整动效规范（标准缓动 `cubic-bezier(0.2,0,0,1)`、时长 200–500ms、强调/退出曲线成套），最成熟。
- 适用：想要"规范、现代、跨平台一致"，且希望明暗主题一键同源派生（减少双主题维护成本）。
- 取舍：组件/规范最全、动效体系最完整；但默认观感偏"Google 系"、个性弱，深主题派生子需过 contrast 校验。
- 来源 / license：Material Design 3（material.io）。规范与 material-components — Apache-2.0；Roboto — Apache-2.0。`https://m3.material.io`

## 待 zj 决策（Human gate required）
- 五选一：card-a / card-b / card-c / card-d / card-e，或描述变体（如 "d 的密度但 e 的 hue 派生机制"）。
- 选定后写入 `UI-DESIGN.md.direction_choice`，S4 方可开工。

## direction_choice（zj 2026-10-25 选定 · Human gate 已签）
- **card-e — 规范动态紫（Material Design 3 取向）**。
- 种子色 seed `#6750A4`；hue 可派生，明暗主题同源。
- 字体 Roboto（Apache-2.0）；代码 Roboto Mono。
- 已写入 canonical `UI-DESIGN.md.direction_choice`，S4 据此外推 tokens + catalog。
