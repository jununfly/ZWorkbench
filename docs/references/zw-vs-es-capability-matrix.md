---
doc-kind: reference
authority: supporting
---

# ZWorkbench vs easy-stock 能力对照矩阵（C01–C41）

> 缩写：ZW = ZWorkbench（本仓库本地项目）；ES = easy-stock（github.com/jundizhou/easy-stock）。
> 表格格式：`| # | 对比点 | ZW（有/无） | ES（有/无） | 主要差异 |`，对话引用用 `C01`…`C41`。
> 证据来源：ZW 取自仓库 `README.md` / `AGENTS.md` / `pyproject.toml` 及架构 ADR；ES 取自其 GitHub README 与「AI 原生架构」说明。
> **核心前提**（2026-10-19 定位订正后）：ZW 是「个人综合工作台」——AI 编码证据、A 股投研、LLM 对话 agent 等能力面并列常驻 tab；ES 是「A 股 AI 智能投研桌面工作台」。旧口径「ZW=AI 编码任务的 durable 证据/编排工作台」为 C01 对照时的历史底色，见 C01 行注。

本文件为 C01–C41 能力对照的**长期 reference（canonical 来源）**。其战略结论（ZW 与 ES 正交定位、Go 全 pivot + B2 提前）已沉淀于 `docs/designs/pd-es-resident-tabs.md` §4 与 `docs/zj-adr/0015-go-full-pivot-supersedes-0013.md`、`docs/zj-adr/0016-coding-evidence-b2-pulled-forward.md`，本文件不再复述结论、只保留能力对照事实。

## 一、定位与产品域

| # | 对比点 | ZW（有/无） | ES（有/无） | 主要差异 |
|---|---|---|---|---|
| C01 | 产品定位 | 有 | 有 | ZW=个人综合工作台（本地优先；编码证据/投研/对话等能力面并列常驻 tab，2026-10-19 订正；旧口径「AI 编码工作台」为对照时历史底色）；ES=A 股行情分析+AI 智能投研桌面工作台 |
| C02 | 目标用户 | 有 | 有 | ZW=个人资深开发者/小团队；ES=A 股个人投资者/研究员 |
| C03 | 面向业务领域 | 无（通用） | 有（A 股） | ZW 不绑定任何金融/垂直市场，处理代码仓库；ES 专注 A 股语境（题材/连板/情绪） |
| C04 | 桌面安装包 | 无 | 有 | ZW 仅 CLI + 本地 loopback Web UI，无安装包；ES 提供 Electron 桌面安装包（GitHub Releases，macOS/Windows） |
| C05 | 本地优先（Local First） | 有 | 有 | 两者均强调本机数据自持、AI 在本地闭环 |
| C06 | 是否实际交易/券商下单 | 无 | 无 | 两者均不接入券商、不执行交易；ES 明确「不构成投资建议」，仅研究/分析 |

## 二、产品功能

| # | 对比点 | ZW（有/无） | ES（有/无） | 主要差异 |
|---|---|---|---|---|
| C07 | 行情/市场数据聚合 | 无 | 有 | ES 聚合开盘啦/东方财富/新浪/财联社等统一行情、K 线、题材、涨停与资讯；ZW 不接外部数据源 |
| C08 | 个股/标的分析研究 | 无 | 有 | ES 有「个股分级研究」（量化速览/AI 快速/标准/深度研判，分观察/新开仓/持仓）；ZW 研究的是代码而非标的 |
| C09 | 题材/连板/情绪分析 | 无 | 有 | ES 有超短连板梯队、趋势题材雷达、情绪周期识别；ZW 无 |
| C10 | 持仓管理/组合巡检 | 无 | 有 | ES 支持多持仓方案、AI 巡检、四维综合评分（逻辑35%/结构25%/风险25%/策略15%）；ZW 无 |
| C11 | AI 持仓优化/配仓 | 无 | 有 | ES 有候选筛选、投资比较、程序配仓、原/目标同次复评；ZW 无 |
| C12 | 大 V/资讯自动复盘 | 无 | 有 | ES 自动同步雪球/淘股吧/微信公众号、去重归档、生成「今日大 V 观点共识」；ZW 无 |
| C13 | 量化回测引擎 | 无 | 无（无独立引擎） | ES「量化」指量化速览/基线视图，非策略回测；两者均无回测引擎 |
| C14 | 定时任务调度 | 无 | 有 | ES 有定时复盘（交易日前 22:00）、定时持仓巡检；ZW 为一次性 `run`，无调度 |
| C15 | 消息通知（飞书/钉钉） | 无 | 有 | ES 支持飞书/钉钉机器人推送 Markdown 结果；ZW 无通知能力 |
| C16 | 浏览器自动化采集 | 无 | 有 | ES 有 Browser Bridge 复用 Electron 持久会话访问雪球/淘股吧，缺桥时 agent-browser 回退；ZW 无 |
| C17 | 证据/可追溯结论 | 有（强） | 有 | ZW=CompositionOwner 记账+来源/时间+可回放证据（架构硬约束）；ES=带来源与时间的版本化快照、检查点续跑 |
| C18 | 人工复核/标注模式 | 有 | 部分 | ZW 有 `ui-host --review`（悬停语义名、脱敏反馈 token、深链接定位）；ES 有 AI 会话授权与澄清，无独立标注模式 |
| C19 | 知识库/游资心法 | 无 | 有 | ES 有游资心法库、人物资料与 Hermes 深度研读；ZW 无业务知识库 |

## 三、技术能力与架构

| # | 对比点 | ZW（有/无） | ES（有/无） | 主要差异 |
|---|---|---|---|---|
| C20 | 主语言/后端 | Python（纯） | Go | ZW 纯 Python、零第三方依赖；ES Go 后端负责采集/量化/编排 |
| C21 | 前端/UI 技术 | server-rendered HTML | React + TypeScript | ZW UI 为 server-rendered HTML（ADR 0003，无前端打包）；ES 为 React/TS 富前端 |
| C22 | 桌面宿主 | 无（loopback HTTP） | 有（Electron） | ZW 只读 loopback 宿主绑 127.0.0.1，三视图；ES Electron 装配 Go/Hermes/Codex/Python，分配本机端口+启动 Token |
| C23 | 持久化存储 | SQLite | SQLite | 均为 SQLite；ZW=CompositionOwner 单一库，ES=多模块快照库 |
| C24 | AI 运行时 | Codex-only（v1） | Hermes 或 Codex 双运行时 | ZW v1 仅 Codex 编码 Worker；ES 统一 Agent 服务可选 Hermes/Codex，共享模型连接/Skills/MCP |
| C25 | 多模型供应商 | 受限 | 有 | ZW 受 Codex 连接约束（需支持 Responses）；ES 已接 OpenAI/DeepSeek/通义千问/Moonshot/Anthropic + 自定义兼容端点 |
| C26 | 单一 durable 状态源 | 有（硬约束） | 部分 | ZW 强制 CompositionOwner 唯一 owner（run/attempt/event/effect/result/approval/replay/backup）；ES 为模块级 SQLite，无单一 owner 概念 |
| C27 | 回放/证据可复核 | 有 | 有 | ZW=owner-backed replay metadata；ES=证据快照+来源时间+阶段检查点续跑 |
| C28 | 越界/安全拦截（safe-stop） | 有 | 部分 | ZW 未知工具/越界 workspace/未确认 approval/网络凭证/不可关联事件一律 safe-stop（H 系列）；ES 有本机鉴权、参数校验、请求日志，无同等 fail-closed 拦截语义 |
| C29 | 真实写副作用（diff/commit） | 无（默认） | 无 | ZW 默认 safe-stop，真实写须经 S0 host enforcement 出证（当前 0 行实现、未证明）；ES 为分析/研究，不写代码 |
| C30 | Git 集成 | 有（显式授权门） | 无 | ZW commit/push 为显式、可记账、进 receipt 的授权动作（S4 push 单独门）；ES 非代码仓库工具，无 Git 集成 |
| C31 | Agent/任务编排 | 有（部分） | 有 | ZW=CompositionOwner 编排 run/attempt/event/effect，DSH 主 Harness 仍 target/unknown；ES=Go 领域服务+任务编排+定时同步 |
| C32 | 第三方依赖 | 无（dependencies=[]） | 有 | ZW 纯 Python 自包含 wheel；ES 依赖 Go/React/Electron 生态 |
| C33 | 测试体系 | 有 | 有（深度 unknown） | ZW 有 pytest 行为测试+evaluation fixtures；ES 开发者文档提及测试，深度未核实 |
| C34 | 安装/分发方式 | pip wheel / 源码 | GitHub Releases 桌面包 | ZW 无桌面安装包；ES 下载 DMG/EXE 覆盖安装、应用内更新（mac 仍手动） |
| C35 | 许可证 | 未声明 | PolyForm Noncommercial 1.0.0 | ZW 仓库无 LICENSE（个人/内部工作台）；ES 为 source-available、明确禁止商业用途，需单独商业授权 |
| C36 | 数据源适配/回退 | 无 | 有 | ES 多源适配与回退、断网可用 7 天缓存；ZW 不接外部数据源 |
| C37 | 跨平台 | 有（Python CLI） | 有（Electron） | 均跨 macOS/Windows |

## 四、成熟度与路线

| # | 对比点 | ZW（有/无） | ES（有/无） | 主要差异 |
|---|---|---|---|---|
| C38 | v1 出货状态 | 有（回退基线） | 有（多版本） | ZW=Codex-only 回退基线已出货（零凭证首跑可用）；ES 已发布 v1.5.3+ 桌面应用、有产品路线图 |
| C39 | 主 Harness 完成度 | 无（target/unknown） | 有 | ZW 的 DSH 主 Harness=target/unknown（H7 deferred-until-demand，0 实现）；ES 已有完整 AI 原生架构（Go+React+Electron+Hermes/Codex） |
| C40 | 真实 Provider 接入 | 无（未证明） | 有（生产可用） | ZW 真实远程 Provider 写副作用/Push 经 S0 出证、当前 0 行未证明、属路线外按需验证（ADR 0009）；ES 已接多模型供应商生产可用 |
| C41 | 代码修改执行（AI→diff→commit） | 规划中（门控） | 无 | ZW 设计上 AI 可改代码并经授权落 commit；ES AI 产出研究文本/判断，不写代码 |

## 证据与对齐项

- **关键假设（对齐项）**：本对比以「ZW 当前 v1 Codex-only 回退基线」为事实基准，未把 target 态（DSH 主 Harness、真实 Provider 写）当作已实现；ES 以官方 README/架构说明为基准。
- **信息缺口（unknown）**：
  1. ES 的自动化测试深度与 CI 覆盖未核实（开发者文档提及测试，无量化证据）。
  2. ZW 的产品许可证未声明（仓库根无 LICENSE 文件），商业/分发边界不明。
  3. ES 是否在 Codex/Hermes 运行时执行「代码级」动作未核实（其定位为研究而非编码，但 Codex app-server 具备执行能力）。
- **结论导向**：两者正交 —— ZW 解决「AI 编码任务的可复核证据与编排」，ES 解决「A 股研究的结构化感知与 AI 投研」。无功能重叠可复用为彼此单元能力；若要做「量化策略代码的 AI 编写+可回放证据」，ZW 的 CompositionOwner 证据层可作 ES 类产品的编码侧底座，但需先补齐 S0 真实写门（当前未证明）。
