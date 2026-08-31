<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `personal-workbench-w7-roadmap.json` | 最后更新: 2026-08-31 15:52:14

[~][X+] 1. W7 候选固定版本验证与采用姿态决策
├── [x][Y+] 1-1. 冻结 Codex 优先候选与 DeepSeek 对照候选的源码运行身份
├── [x][X+] 1-2. 为优先候选建立真实 C2 fail-closed 安全 adapter
├── [x][X+] 1-3. 为优先候选建立 C3/C4 定时幂等与中断恢复 adapter
│   ├── [x][Y+] 1-3-1. 完成 Codex C3/C4 原生能力探针并固化 composition 边界
│   └── [x][X+] 1-3-2. 运行 Codex durable schedule与恢复 composition adapter
├── [x][X+] 1-4. 为优先候选建立 C5 Provider 故障切换与 C6 回放 adapter
├── [x][X+] 1-5. 由单一操作者完成优先候选 C7 运维许可证与退出审计
├── [x][X+] 1-6. 基于候选 C1至C7 证据完成 ATAM/CBAM 采用姿态决策
├── [x][X+] 1-7. 关闭 Codex C4 approval owner 与原生/组合边界
└── [~][X+] 1-8. 完成 Codex C7 真实单人生命周期验证与退出签核
    ├── [x][Y+] 1-8-1. 实现 composition owner 深模块接口与 SQLite 持久化
    ├── [x][Y+] 1-8-2. 实现 run、approval、effect、result 与 event durable ledger
    ├── [x][Y+] 1-8-3. 实现 fail-closed approval、幂等 claim 与中断后 reconcile
    ├── [x][Y+] 1-8-4. 实现 composition state backup、restore、导出与完整性校验
    └── [ ][X+] 1-8-5. 接入 Codex app-server adapter 并完成真实 owner 隔离回归
<!-- ROADMAP_SECTION_END -->
