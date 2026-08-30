<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `personal-workbench-roadmap.json` | 最后更新: 2026-08-30 18:26:32

[~][X+] 1. W6 统一评估矩阵与 ATAM/CBAM 持续验证门槛
├── [x][Y+] 1-1. 冻结候选分层与硬门槛
│   ├── [x][Y+] 1-1-1. 确认执行 Harness 候选：DeepSeek、Pi、Codex、OpenCode、Goose
│   ├── [x][Y+] 1-1-2. 确认组合件层：编排、调度、Provider、观测、评测
│   └── [x][Y+] 1-1-3. 固化个人开发者/小团队硬门槛
├── [~][Y+] 1-2. ATAM 质量属性场景与风险分析
│   ├── [ ][X+] 1-2-1. 代码任务闭环与可审计性场景
│   ├── [ ][X+] 1-2-2. 无人值守自动化与审批拦截场景
│   ├── [ ][X+] 1-2-3. 多 Provider 可迁移性场景
│   ├── [ ][X+] 1-2-4. 事件记录、回放与评测场景
│   └── [ ][X+] 1-2-5. 单人运维、恢复与生命周期场景
├── [~][Y+] 1-3. CBAM 场景收益、成本与组合增量分析
│   ├── [ ][X+] 1-3-1. 量化场景收益与风险降低
│   ├── [ ][X+] 1-3-2. 计算一次性、持续、迁移与退出成本
│   └── [ ][X+] 1-3-3. 评估第二 Harness 和组合件的增量价值
├── [~][Y+] 1-4. 自动化与持续评估协议
│   ├── [x][Y+] 1-4-1. 版本化基准与无副作用 fixture
│   ├── [x][Y+] 1-4-2. 指标、阈值、硬失败与证据留存
│   └── [~][Y+] 1-4-3. 触发、漂移监测、回归与暂停升级
└── [ ][X+] 1-5. 候选实测矩阵与 W7 决策交接包
    ├── [x][Y+] 1-5-1. 统一候选执行流程与隔离环境
    ├── [~][X+] 1-5-2. 形成候选证据矩阵与未知项账本
    ├── [~][Y+] 1-5-3. 生成 ATAM/CBAM 决策包
    └── [ ][Y+] 1-5-4. W6 signoff 并交接 W7 采用姿态决策

### 当前施工：1-5-3. 生成 ATAM/CBAM 决策包

ATAM/CBAM 已纳入 C2 adapter 增量证据：确认薄安全层可复用到 DeepSeek/Codex 双 Provider，记录 15 次无人审批全阻断、一次性批准边界和 ledger 成本；同时新增宿主级 sandbox/broker 嵌套兼容性风险。C3–C7 与宿主级 C2 强制边界仍 unknown，暂不形成 W7 采用建议。详见 docs/plans/w6-c2-adapter-findings.md、docs/plans/w6-atam-template.md、docs/plans/w6-cbam-template.md。
<!-- ROADMAP_SECTION_END -->
