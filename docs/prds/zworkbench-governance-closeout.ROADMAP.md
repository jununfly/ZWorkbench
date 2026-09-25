<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `zworkbench-governance-closeout.roadmap.json` | 最后更新: 2026-09-24 11:12:34

[x][X+] 1. ZWorkbench 治理收尾 — 路线图状态/代码同步化
├── [x][X+] 1-1. 根因与判定规则
│   ├── [x][X+] 1-1-1. 复盘 F6/F12 desync 实例（commit 证据）
│   └── [x][X+] 1-1-2. 定义 desync 判定规则（feat 先于 chore(roadmap)）
├── [x][X+] 1-2. 现状审计
│   ├── [x][X+] 1-2-1. 全量扫描 workbench-ui-interactive completed 节点核对代码落地
│   └── [x][X+] 1-2-2. 产出 desync 清单（结论：仅 F6/F12）
├── [x][X+] 1-3. 预防机制
│   ├── [x][X+] 1-3-1. 设计 commit 顺序门禁（feat → chore(roadmap) 硬顺序）
│   └── [x][X+] 1-3-2. 实现校验脚本（closeout 前 verify completed 节点均有对应已提交代码）
├── [x][X+] 1-4. 规则沉淀
│   ├── [x][X+] 1-4-1. 把『代码先于状态』写入 AGENTS.md 收尾约定
│   └── [x][X+] 1-4-2. 更新本仓库 MEMORY / 今日 log
└── [x][X+] 1-5. 收尾闭环
    └── [x][X+] 1-5-1. 跑一次全量 closeout verify，确认无遗留 desync，报告两阶段结果
<!-- ROADMAP_SECTION_END -->
