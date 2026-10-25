# VERIFICATION RECEIPT — ZWorkbench Web 重写（S7 / zj-ui-verify）

receipt_schema_version: 1.0.0
oracle_version: zj-ui-* skill set (no pinned version; source: zagentic)
environment_fingerprint:
  node: v22.22.2 (managed)
  python: 3.13.12 (managed)
  runtime: static HTML preview (no Storybook adapter available in this workspace)
  browser_a11y_automation: eslint-plugin-jsx-a11y (static, CI-gated; runtime axe pending)
status: PASS                    # G-V4 自动化 a11y 门禁已 PASS；commit 已触发并推送到 origin/main
commit: 103c81e (feat) + 95417ca (chore)   # zj 于 2026-10-25 显式触发 commit+push，已上 origin/main
baseline_commit: 9a0f1dd        # 两提交前的 main HEAD（fingerprint 冻结基准）

## artifact provenance（链路指纹，commit 前以 sha256:16 记录）
- UI-BRIEF.md        sha256:16 = 718fee2c5552f3c6
- DIRECTION-CANDIDATES.md sha256:16 = cc48dae761fd03e8
- UI-DESIGN.md       sha256:16 = 8d564eceb3040ab3
- ui-flow/v1.md      sha256:16 = 6c2e9dca55533e2b
- preview/index.html sha256:16 = c05c391368a9f0b7
- eslint.config.js / package.json(jsx-a11y) / check-web.sh / .github/workflows/web-build.yml  # G-V4 a11y 门禁（devDep: eslint@9, @typescript-eslint/parser@8, eslint-plugin-jsx-a11y@6.10.2）

## cells（claim / threshold / command / fixture+env hash / status）
- C1 视觉基线一致性
  claim: preview 使用 card-e (M3) 主色 #6750A4 + Roboto；与 UI-DESIGN.md tokens 一致
  threshold: 主色/中性色/半径/字体与 UI-DESIGN.md 逐字段一致
  command: 人工比对 preview/index.html CSS 变量 vs UI-DESIGN.md tokens 段
  fixture+env hash: preview=c05c391368a9f0b7 / UI-DESIGN=8d564eceb3040ab3
  status: PASS（人工）
- C2 对比度（WCAG）
  claim: UI-DESIGN.md 已核验 M3 主色对比度达标；跌绿正文新增深绿 #1b7d2e(5.225) 达标
  threshold: 正文文本 >= 4.5:1；大字 >= 3:1
  command: S4 已跑 Python contrast 核验（见 UI-DESIGN.md contrast 段）
  fixture+env hash: UI-DESIGN=8d564eceb3040ab3
  status: PASS（设计期核验，非运行期）
- C3 导航结构（六义）
  claim: 7 一级 + 主题→A股投研 二级折叠；当前项高亮；ui-flow/v1 round-trip 无丢义
  threshold: 7 一级可路由 + 当前项背景/图标区别于他项 + 二级默认折叠可展开
  command: 人工走查 preview；比对 ui-flow/v1 semantic round-trip 段
  fixture+env hash: preview=c05c391368a9f0b7 / ui-flow=6c2e9dca55533e2b
  status: PASS（人工）
- C4 对话历史交互
  claim: 左侧对话历史列表，当前会话背景高亮；点击切换右侧内容；右键菜单 分享/归档/删除
  threshold: 切换会话右侧同步；右键三动作可执行（删除移除 / 归档置灰 / 分享提示）
  command: 人工走查 preview（工作台→对话）
  fixture+env hash: preview=c05c391368a9f0b7
  status: PASS（人工）
- G-V1 state-transition UI reachability
  claim: 编码证据 7 态状态机迁移均有 UI 控件（CodingEvidenceTab 的 transition/safe-stop/reconcile 按钮）
  threshold: 每个合法迁移有可达入口
  command: 静态审查 CodingEvidenceTab.tsx（真实后端组件，非 preview）
  fixture+env hash: src/tabs/CodingEvidenceTab.tsx (working tree)
  status: PASS（静态审查；运行期需后端联调）
- G-V2 no-fake-success / no-silent-data-loss
  claim: 错误态显式展示（ChatTab/CodingEvidenceTab/SettingsTab 均有 err 直显，ErrorBoundary 防白屏）
  threshold: error/failed 不被渲染为 success；持久化/请求失败显式报错
  command: 静态审查 + main.tsx ErrorBoundary
  fixture+env hash: src/main.tsx, src/tabs/*
  status: PASS（静态审查）
- G-V3 illegal-transition return checked
  claim: 后端 transition 返回非 2xx 时前端 err 直显（reqJSON 抛错，catch 展示）
  threshold: 非法迁移返回值不被静默丢弃
  command: 静态审查 api.ts reqJSON + 各 tab catch 分支
  fixture+env hash: src/api.ts
  status: PASS（静态审查；运行期需后端联调）
- G-V4 required-input accessibility (automated a11y gate)
  claim: 必填/关键输入必须有可访问名称（label 关联或 aria-label）；由 eslint-plugin-jsx-a11y 在 CI 强制，0 error 通过门禁
  threshold: control-has-associated-label / label-has-associated-control = error；交互元素键盘可达性 = warn（后续迭代跟踪）
  command: cd app/web && npm run lint  （已接入 check-web.sh 与 .github/workflows/web-build.yml，push/PR 自动跑）
  fixture+env hash: eslint.config.js, package-lock.json (eslint-plugin-jsx-a11y@6.10.2)
  status: PASS（自动化，0 error；运行期 error→aria-describedby 关联列为后续迭代）

## aggregate
- 人工核验 cell: C1,C2,C3,C4,G-V1,G-V2,G-V3 = PASS
- 自动化门禁 cell: G-V4 = PASS（eslint-plugin-jsx-a11y，CI 强制，0 error）
- 整体 status = PASS（所有 cell PASS；commit 已触发：103c81e + 95417ca，已推送 origin/main，fingerprint 以 baseline_commit=9a0f1dd 冻结）
- baseline 不等于通过：本 receipt 仅证明当前工作树与 canonical 一致 + 自动化 a11y 门禁通过；运行期全通过仍需后端联调与 axe/对比度运行期核验。
