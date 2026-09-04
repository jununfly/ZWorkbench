<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `personal-workbench-w8-roadmap.json` | 最后更新: 2026-09-04 18:03:16

[~][X+] 1. W8 受控个人试点产品边界与最小纵向切片
├── [x][Y+] 1-1. 冻结受控个人试点的产品边界与责任地图
├── [x][Y+] 1-2. 定义本地数据、凭证、Provider 与副作用安全边界
├── [x][Y+] 1-3. 设计 local_read_only_run 最小纵向切片
├── [x][Y+] 1-4. 固化第一切片的验收、停止与回滚条件
├── [x][Y+] 1-5. 实现并验证 local_read_only_run
│   ├── [x][Y+] 1-5-1. 定义 local_read_only_run 入口配置与 preflight 结果结构
│   ├── [x][Y+] 1-5-2. 复用 composition owner 与 Codex adapter 完成运行编排 seam
│   ├── [x][Y+] 1-5-3. 建立成功与未知边界失败的隔离 fixture
│   ├── [x][Y+] 1-5-4. 验证身份关联、脱敏、网络零访问与默认拒绝
│   └── [x][Y+] 1-5-5. 验证 backup/restore 并生成第一切片 evidence
├── [~][X+] 1-6. 可恢复本地写操作与运行边界验收
│   ├── [!][X+] 1-6-3. 宿主强制边界与 Codex native approval 验证
│   ├── [x][X+] 1-6-4. 可恢复本地写操作故障矩阵验证
│   └── [x][X+] 1-6-5. ATAM CBAM 综合放行复审
├── [x][Y+] 1-7. local_read_only_run 产品入口与可安装运行闭环
├── [~][X+] 1-8. DeepSeek 独立挑战者 C1-C7 评估
│   ├── [x][Y+] 1-8-1. 按 Codex C1-C7 同形状补齐 DeepSeek 公平验证
│   ├── [x][X+] 1-8-2. DeepSeek 插件生态挑战与公平增量评估
│   └── [~][X+] 1-8-3. DeepSeek 首个 pinned plugin bundle 的 E1-E6 隔离验证
└── [~][Y+] 1-9. DSH 主 Harness + Codex Worker 混合只读实现
    ├── [x][Y+] 1-9-1. Stage 0：冻结 Worker contract、identity/schema 与 capability facade
    ├── [x][Y+] 1-9-2. H1 Bootstrap：固定 DSH profile 并启动 parent Run
    ├── [x][Y+] 1-9-3. H2 Worker handshake：绑定 DSH/Codex 与 owner identity
    ├── [x][Y+] 1-9-4. H3 隔离只读 coding：生成可审查 Worker artifact
    ├── [ ][Y+] 1-9-5. H4 中断恢复与进程生命周期：无孤儿 Worker
    ├── [ ][Y+] 1-9-6. H5 Evidence/replay：记录 owner 证据并隔离回放模式
    └── [~][X+] 1-9-7. 真实远程 Provider 兼容性：隔离 staging 与 owner-facing contract
<!-- ROADMAP_SECTION_END -->
