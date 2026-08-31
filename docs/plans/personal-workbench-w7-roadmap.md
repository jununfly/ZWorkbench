<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `personal-workbench-w7-roadmap.json` | 最后更新: 2026-08-31 17:11:36

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
    ├── [x][Y+] 1-8-5. 接入 Codex app-server adapter 并完成真实 owner 隔离回归
    └── [~][X+] 1-8-6. 关闭 C7 剩余人工生命周期、许可证与真实退出责任

### 当前施工：1-8-6. 关闭 C7 剩余人工生命周期、许可证与真实退出责任

本轮完成 agent 可验证的 C7 证据收敛：固化 Human upgrade/rollback 原始日志（0.138.0→0.139.0→0.138.0，14.35 秒，临时 C7 prefix，单人）；root/platform npm SLSA provenance 与官方 registry tarball integrity 绑定到 rust-v0.139.0 / a7dff904…，本机 npm 安装内容核对通过；npm CLI 10.9.8 隔离验证 2/2 registry signatures、2/2 attestations；新增许可证/provenance 审计文档。结论：source-to-binary 为 pass-at-release-level，independent attestation verification pass-via-npm-cli，升级/回滚为 partial-exercised；C7/G7 仍 unknown/stop。剩余门：fresh install 原始证据、backup/restore 与故障定位真实 stopwatch、schema/ledger 迁移兼容、独立 reproducible rebuild、完整 NOTICE/商业边界、远端账户/retention 退出责任。

**决策：**
- Q: 1-8-5 完成后，C7 下一节点保留哪些未签核门？ → 继续保留 C7/G7 unknown/stop：真实单一操作者 stopwatch、真实候选安装与升级/回滚、NOTICE/商业边界审查、source-to-binary provenance、真实远端/账户/retention 退出责任，以及 Codex 原生 approval unknown。1-8-5 只关闭真实 owner state 缺失对 backup/restore 与 exit 机器控制的阻断。 (机器 6/6 pass 不足以签核；个人开发者/小团队约束继续要求维护服务≤3、无额外专家，并把新增外部系统的生命周期和退出成本计入 CBAM。)
- Q: 1-8-6 本轮继续的可执行范围与停止边界是什么？ → 先完成 agent 可验证的本机 artifact/license/依赖清单、发布 provenance evidence ledger、人工计时与原始 log 的关联，以及真实 owner-backed C7 evidence 的索引；不把单一 Apache-2.0 声明升级为完整 NOTICE/商业签核，不把本机 release-level digest 升级为 source-to-binary provenance，不代替操作者执行需要真实账户/全局安装/远端退出的动作。若关键一手证据缺失，C7/G7 继续 unknown/stop。 (ATAM 先关闭可低成本验证的身份、依赖、退出责任边界；CBAM 继续约束为个人开发者/小团队的一个主 Harness + 一个薄 owner，不新增常驻服务或第二 Harness。)
- Q: 本轮本机核对是否关闭 source-to-binary provenance？ → 将 source-to-binary 结论从完全 unknown 收窄为 npm artifact provenance pass-at-release-level：父包与 Darwin arm64 平台包均有 npm SLSA provenance，attestation 的 resolved dependency 指向 rust-v0.139.0 与 commit a7dff904308535e965aee87680c1fc5ef1d19eec；registry tarball SHA-512 与 attestation subject 一致，本机安装树与对应 tarball 内容一致。仍不宣称独立 Sigstore 验签、Homebrew/其他安装渠道等价、源码全部依赖许可证/NOTICE 完整或商业边界通过；这些继续 blocking。 (ATAM：把供应链风险拆成 release artifact provenance、installed-bytes binding、license/NOTICE/commercial 三个可独立验证的敏感点；CBAM：只保留现有 npm/Codex runtime + composition owner，不为审计引入新服务。)
- Q: 1-8-6 本轮证据更新后的 C7 结论是什么？ → source-to-binary 不再是完全 unknown：root 与 Darwin arm64 npm release artifact 的 SLSA provenance、registry tarball integrity、本机 npm 安装 bytes 已绑定到 rust-v0.139.0 / a7dff904…，记为 pass-at-release-level；Human 在临时 C7 prefix 真实完成 0.138.0→0.139.0→0.138.0，14.35 秒，记为 partial-exercised。C7/G7 仍 unknown/stop，因为 install raw evidence、backup/restore stopwatch、fault diagnosis stopwatch、schema/ledger migration compatibility、完整 NOTICE/商业边界、独立验签/重建、远端账户/retention 退出责任尚未签核。 (ATAM：关闭“发布包无来源绑定”和“完全没有版本切换证据”两个较窄未知，同时保留更高风险的责任边界；CBAM：继续维持一个 Codex runtime + 一个 SQLite composition owner，不添加审计服务。)
- Q: npm provenance 验证后还剩哪一项供应链未知？ → npm CLI 10.9.8 在仅含 Codex 0.139.0 的隔离安装中报告 root/platform 两个包的 registry signatures 与 attestations 均验证通过，因此独立 attestation verification 记为 pass-via-npm-cli；仍保留 independent reproducible rebuild=unknown、其他安装渠道不等价、完整 vendor/transitive NOTICE 与商业边界未知。 (ATAM：registry signature/provenance verification 与 independent rebuild 分开计量；CBAM：验证使用临时 package，不引入 cosign、服务或新的常驻依赖。)
<!-- ROADMAP_SECTION_END -->
