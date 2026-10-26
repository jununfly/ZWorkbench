# UI-BRIEF.md — ZWorkbench Web 界面全量重写

brief_schema_version: 1.0.0
revision: c03ef07d8f24e5e090be82b27b732b7b06c484db656e8eaefcbee7c5d4952313
input_revision: conversation:2026-10-24 (zj 指令：用 zj-ui-* skills 全量重写 web 界面)
source: zagentic (zj-ui-brief S1)

## goal_users
- 个人开发者（自用为主；以 zj 为代表：资深程序员 + 技术架构师 + 技术部门负责人，兼产品/业务视角）
- 小团队（≤ 数人）协作为辅

## goal_task
在一个本地优先的个人综合工作台里，统一承载 A股投研、LLM 对话、编码证据管理、设置等常驻任务；并把当前以交易为中心的 11 个 tab 重梳为与「个人综合工作台」定位一致的新 tab 集合；用统一的设计系统重做外壳与全部 tab 界面，最终移植为 app/web 真实 React 代码。

## constraints
- 只重写界面，不改动后端契约：继续接现有 Go 后端（:18080），沿用 /api/tabs 注册机制与现有 REST 路由。
- 新增/重梳 tab 必须走三处注册：internal/domain/tabs.go 注册表 + web/src/App.tsx 条件渲染 + App.tsx 末尾非占位白名单数组。
- 视觉遵循 A股惯例：涨 = 红、跌 = 绿。
- 复用现有真实数据源（东方财富 provider，免费免 token），不新增外部付费依赖。
- 设计系统须满足 WCAG contrast 硬约束（zj-ui-core 契约）。
- 前端不引入重型新运行时依赖；构建门禁为 check-web（npm ci → tsc --noEmit → vite build）。
- 全量重写按 tab 切片推进，每个切片可独立验收、可回滚。
- UI 设计产物为 canonical artifact，由 zj-ui-* 链路（S1→S7）产出，不是 SSOT 代码。

## success_criteria
- UI-BRIEF / UI-DESIGN / ui-flow/v1 三份 canonical 产物齐全且通过 schema 校验（deny-first、unknown 四元组保留、必填零丢失）。
- 重梳后的 tab 集合与「个人综合工作台」定位一致：常驻 tab 明确（A股投研 / LLM 对话 / 设置 / 编码证据等），交易类 tab 已按决策删 / 并 / 改。
- 视觉方向经 zj 在 S3 选定并写入 UI-DESIGN.md 的 direction_choice。
- preview 可交互、只用 catalog 内组件，经 zj 在 S6 验收通过。
- 移植后的 app/web React 代码通过 check-web 门禁（tsc --noEmit 0 error + vite build 成功）。
- 全程 zj-ui-* 体验待改进项已随迭代消化（原记录于 docs/plans/ 的临时工作笔记已退役删除）。

## nav_structure (decided S2, zj 2026-10-24)
- 主导航固定左侧，一级导航共 7 项：首页 / 工作台 / 主题 / 项目 / 统计 / 日志 / 设置。
- 当前页：以不同背景色 + 图标高亮区分。
- 一级导航支持二级菜单：默认折叠，点击展开。示例：主题 →（A股投研）。
- 一级项即页面入口；二级展开后点击进入对应页。
- A股投研 为长页面（支持向下滚动），集中承载全部 A股交易类功能（行情总览 / 个股分级研究 / 超短连板 / 大V复盘 / 持仓巡检 / AI持仓优化 / 游资心法）。
- 现有 10 个 tab 的归属（zj 2026-10-25 最终定）：7 个交易类 → A股投研 长页面；设置/LLM → 设置；对话 chat + 编码证据 coding-evidence → 工作台（一级页，非占位）；首页 / 项目 / 统计 / 日志 → 暂为新增占位区（后续填真实内容，本轮不实现）。

## unknown[]
- path: constraints.brand_identity
  raw: null
  reason: ZW 是否有既定品牌色 / Logo / 字体规范未知，可能影响 S3 方向卡与 S4 tokens。
  source: conversation:2026-10-24
  resolved: "2026-10-25 via S3 direction_choice=card-e (Material Design 3, seed #6750A4, Roboto)。视觉基线不再未知，约束转入 UI-DESIGN.md tokens。不再阻塞。"
- path: success_criteria.quant_metric
  raw: null
  reason: 是否有量化验收指标（对比度数值、首屏性能、可访问性等级）未明确，S4/S7 可补。
  source: conversation:2026-10-24

## source_ref
- kind: human_dialogue
- id: conversation:2026-10-24
- summary: zj 指令：用 zj-ui-* skills 全量重写 web 界面；走完整 S1→S7 契约链路；prototype 验收后移植成 app/web React（体验待改进项原记于 docs/plans/，该临时笔记已退役删除）。
