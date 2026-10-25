# HANDOFF — ZWorkbench Web 重写（S10 / zj-ui-handoff）

handoff_schema_version: 1.0.0
status: PENDING_COMMIT       # G-V4 a11y 自动化已补（jsx-a11y, CI 强制）；receipt 全 PASS 待 commit 冻结指纹；以下六段已备齐
owner: zjj (AI 搭档) → 交接对象：下一次会话 / 移植执行者 / zj
canonical_artifacts:
  UI-BRIEF.md@718fee2c / DIRECTION-CANDIDATES.md@cc48dae76 / UI-DESIGN.md@8d564ece / ui-flow/v1.md@6c2e9dca / VERIFICATION-RECEIPT.md (本目录)
commit_sha: PENDING（按项目约定需 zj 显式 commit+push）

## 1. 变更摘要（change summary）
- 用 zj-ui-* S1→S7 契约链路重做 ZWorkbench Web 界面：导航由「扁平 10 tab」改为「7 一级 + 主题→A股投研 二级折叠」的个人综合工作台。
- 视觉基线选定 card-e Material Design 3（seed #6750A4, Roboto），产出 UI-DESIGN.md 设计系统（tokens + 15 组件 catalog + contrast 全达标）。
- 工作台 = 对话（会话列表+右键菜单+切换）+ 编码证据；A股投研 = 长页面承载 7 个交易类分区；设置 = 通用 + LLM。
- 可交互 preview（`preview/index.html`，非 canonical）已通过 zj 人工验收。
- 已移植为 `app/web` 真实 React（接现有 Go 后端 :18080），构建门禁（tsc + eslint + vite build）全 PASS。

## 2. 可复现运行命令（reproducible commands）
- 看 preview：`open app/web/ui-spec/preview/index.html`（纯静态，无需后端）
- React 构建门禁（移植后）：`cd app/web && bash check-web.sh`（npm ci → tsc --noEmit → eslint a11y 门禁 → vite build）
- 本地 dev：`cd app/web && npm run dev`（Vite，连 :18080）
- Go 后端：仓库 `app/` 内 `go run ./cmd/zworkbench-go`（默认 :18080）

## 3. 风险（risks）
- R1：A股投研长页直接内嵌现有 7 个 tab 组件，若某组件在 prod 同源模式下因 apiBase 解析失败会局部报错（ErrorBoundary 仅兜顶层，组件内已 err 直显）。
- R2：对话会话列表为前端内存态，刷新即丢；移植到 React 后接 `/api/agent/chat` 仅对当前会话生效，多会话持久化需后端新增会话接口（当前无）。
- R3：G-V4 已补自动化 a11y 门禁（eslint-plugin-jsx-a11y，CI 强制，0 error）；运行期 error→aria-describedby 关联与 axe/对比度运行期核验列为后续迭代（见缺口清单）。
- R4：`/api/tabs` 端点仍返回旧 10 tab，新导航为前端固定结构，该端点暂未使用（非破坏性，但属冗余）。

## 4. 已知限制（known limits）
- preview 与 React 移植均尚未 commit；canonical 指纹未冻结。
- 首页 / 项目 / 统计 / 日志 为占位（本轮不实现真实内容）。
- 深色主题为 M3 派生 token，preview 未启用切换；React 移植可加主题切换。
- 自动化 a11y 门禁已接入（eslint-plugin-jsx-a11y，CI 强制，0 error）；运行期 axe / 对比度自动核验仍需后续补（见缺口清单）。

## 5. fallback（回退）
- 设计回退目标：S6 preview revision（preview/index.html@c05c391368a9f0b7）与 UI-DESIGN.md@8d564ece。
- 代码回退：移植前 `app/web/src` 为旧扁平 tab 结构，git 历史可回滚到本次移植前 commit（commit 触发后才有）。
- 外部依赖：无第三方设计系统运行时（M3 仅取 token 与字体思路，不引 @material/web），不依赖外部链接恢复。

## 6. 责任人（owner）
- 设计链路 owner：zj-ui-* skills（source: zagentic）
- 本链路执行：zjj（AI 搭档）
- 验收 / 决策：zj
- 移植执行者：zjj → 交接给下一次会话或 zj 复审

## 缺口清单（handoff incomplete 原因）
- [ ] commit sha 未生成（等 zj 显式 commit+push；届时冻结 UI-BRIEF/UI-DESIGN/ui-flow/preview 指纹）
- [x] G-V4 a11y 自动化门禁已补（eslint-plugin-jsx-a11y，CI 强制，0 error；见 VERIFICATION-RECEIPT G-V4）
- [x] 移植（app/web React）已执行并通过构建门禁（tsc + eslint + vite build 均 PASS）
- [ ] 后续迭代：运行期 a11y（aria-describedby 错误关联、axe/对比度运行期核验）+ 深色主题切换 + 首页/项目/统计/日志 真实内容
