<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `workbench-ui-interactive.roadmap.json` | 最后更新: 2026-09-24 10:44:29

[x][X+] 1. 完整工作台 Web-UI（含交互）执行路线图
├── [x][X+] 1-1. Round 1 — 纯 UI 壳 + 只读投影（本轮构建）
│   ├── [x][X+] 1-1-1. F1 IA 方向落定：A 会话优先（D1 已决）
│   ├── [x][X+] 1-1-2. F2 顶栏状态语义 shell（tags/pills 状态语义）
│   ├── [x][X+] 1-1-3. F3 侧栏工作记录导航（A 向：新建/近期/工作区）
│   ├── [x][X+] 1-1-4. F4 会话消息流（message/avatar/meta/plan-card 只读渲染）
│   ├── [x][X+] 1-1-5. F5 计划卡（done/current/pending 步骤，投影驱动）
│   ├── [x][X+] 1-1-6. F7 运行事实检查器（渲染壳；实时值留 product gate）
│   ├── [x][X+] 1-1-7. F10 运行轨道栏（渲染壳；可执行 Run 留 product gate）
│   ├── [x][X+] 1-1-8. F11 场景状态机 UI（empty/planning/approval/stopped 四态渲染）
│   ├── [x][X+] 1-1-9. F13 安全停止 / reconcile（横幅 + stopped 态渲染；越界判定留 product gate）
│   ├── [x][X+] 1-1-10. F14 扩展 DSH 只读投影（不引 dsh-web 运行时，ADR 0007）
│   ├── [x][X+] 1-1-11. F15 r2 协同可视化（profile_status / runtime_status 呈现）
│   └── [x][X+] 1-1-12. F19 三变体调试切换器（?variant=A/B/C，纯 client 端分支）
├── [x][X+] 1-2. Product gate — 触碰运行时（独立 product scope gate）
│   ├── [x][X+] 1-2-1. F6 输入 composer 真实发送（触发 agent Run）
│   ├── [x][X+] 1-2-2. F12 审批执行 UI（apply diff / Approval / effect receipt）
│   ├── [x][X+] 1-2-3. F7 实时值（来自投影 / 运行时）
│   ├── [x][X+] 1-2-4. F10 可执行 Run（按钮触发，触碰 CompositionOwner）
│   └── [x][X+] 1-2-5. F13 越界判定逻辑（identity unresolved → reconcile）
└── [x][X+] 1-3. B-C 变体 — B 画布 / C 日记（后续独立 gate）
    ├── [x][X+] 1-3-1. F8 命令画布（canvas-layout：command-path/decision/artifact/run-rail）
    └── [x][X+] 1-3-2. F9 项目日记（journal-layout：index/reading/evidence-table）
<!-- ROADMAP_SECTION_END -->
