<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `personal-workbench-w7-roadmap.json` | 最后更新: 2026-08-31 20:44:07

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

本轮已收齐四类隔离 fixture-level C7 人工时间证据：fresh install 17.01 秒、upgrade/rollback 14.35 秒、backup/restore 12.38 秒、预制 fault diagnosis 2 分 51.31 秒，均低于冻结阈值；fresh install 人工 stopwatch 已与同一次 raw log 绑定，日志 SHA-256 为 6db2fe3abaf3febe72ab6a6acbd282e587daf1876b7c5cb255fd66e7eaefecb5，四个 artifact digest 与候选 manifest 一致。C7/G7 仍 unknown/stop：完整逐包 NOTICE/商业/API/商标审查、独立 reproducible rebuild、真实远端账户/Provider/retention 退出责任和 Codex native approval 继续阻断。ATAM 继续按独立敏感点拆分证据；CBAM 继续约束为一个 Codex runtime + 一个薄 SQLite composition owner，不引入常驻审计服务。

**决策：**
- Q: 1-8-5 完成后，C7 下一节点保留哪些未签核门？ → 继续保留 C7/G7 unknown/stop：真实单一操作者 stopwatch、真实候选安装与升级/回滚、NOTICE/商业边界审查、source-to-binary provenance、真实远端/账户/retention 退出责任，以及 Codex 原生 approval unknown。1-8-5 只关闭真实 owner state 缺失对 backup/restore 与 exit 机器控制的阻断。 (机器 6/6 pass 不足以签核；个人开发者/小团队约束继续要求维护服务≤3、无额外专家，并把新增外部系统的生命周期和退出成本计入 CBAM。)
- Q: 1-8-6 本轮继续的可执行范围与停止边界是什么？ → 先完成 agent 可验证的本机 artifact/license/依赖清单、发布 provenance evidence ledger、人工计时与原始 log 的关联，以及真实 owner-backed C7 evidence 的索引；不把单一 Apache-2.0 声明升级为完整 NOTICE/商业签核，不把本机 release-level digest 升级为 source-to-binary provenance，不代替操作者执行需要真实账户/全局安装/远端退出的动作。若关键一手证据缺失，C7/G7 继续 unknown/stop。 (ATAM 先关闭可低成本验证的身份、依赖、退出责任边界；CBAM 继续约束为个人开发者/小团队的一个主 Harness + 一个薄 owner，不新增常驻服务或第二 Harness。)
- Q: 本轮本机核对是否关闭 source-to-binary provenance？ → 将 source-to-binary 结论从完全 unknown 收窄为 npm artifact provenance pass-at-release-level：父包与 Darwin arm64 平台包均有 npm SLSA provenance，attestation 的 resolved dependency 指向 rust-v0.139.0 与 commit a7dff904308535e965aee87680c1fc5ef1d19eec；registry tarball SHA-512 与 attestation subject 一致，本机安装树与对应 tarball 内容一致。仍不宣称独立 Sigstore 验签、Homebrew/其他安装渠道等价、源码全部依赖许可证/NOTICE 完整或商业边界通过；这些继续 blocking。 (ATAM：把供应链风险拆成 release artifact provenance、installed-bytes binding、license/NOTICE/commercial 三个可独立验证的敏感点；CBAM：只保留现有 npm/Codex runtime + composition owner，不为审计引入新服务。)
- Q: 1-8-6 本轮证据更新后的 C7 结论是什么？ → source-to-binary 不再是完全 unknown：root 与 Darwin arm64 npm release artifact 的 SLSA provenance、registry tarball integrity、本机 npm 安装 bytes 已绑定到 rust-v0.139.0 / a7dff904…，记为 pass-at-release-level；Human 在临时 C7 prefix 真实完成 0.138.0→0.139.0→0.138.0，14.35 秒，记为 partial-exercised。C7/G7 仍 unknown/stop，因为 install raw evidence、backup/restore stopwatch、fault diagnosis stopwatch、schema/ledger migration compatibility、完整 NOTICE/商业边界、独立验签/重建、远端账户/retention 退出责任尚未签核。 (ATAM：关闭“发布包无来源绑定”和“完全没有版本切换证据”两个较窄未知，同时保留更高风险的责任边界；CBAM：继续维持一个 Codex runtime + 一个 SQLite composition owner，不添加审计服务。)
- Q: npm provenance 验证后还剩哪一项供应链未知？ → npm CLI 10.9.8 在仅含 Codex 0.139.0 的隔离安装中报告 root/platform 两个包的 registry signatures 与 attestations 均验证通过，因此独立 attestation verification 记为 pass-via-npm-cli；仍保留 independent reproducible rebuild=unknown、其他安装渠道不等价、完整 vendor/transitive NOTICE 与商业边界未知。 (ATAM：registry signature/provenance verification 与 independent rebuild 分开计量；CBAM：验证使用临时 package，不引入 cosign、服务或新的常驻依赖。)
- Q: 本轮如何处理剩余阻断？ → 仅推进可由隔离环境复核的证据：归档 fresh-install 原始日志并更新为 partial/unknown；在 owner-backed flow 上增加升级/回滚后的 schema、config、ledger identity 与失败恢复探针；生成 vendor/transitive 依赖许可证/NOTICE 事实清单但不代签法律结论。人工 stopwatch、真实账户/远端 retention 退出、商业边界与独立重建继续 unknown/stop。 (ATAM 将发布身份、状态迁移、依赖归属、人工可操作性和退出责任拆成独立敏感点；CBAM 约束为一个 Codex runtime + 一个薄 SQLite owner，不引入常驻审计服务。)
- Q: 本轮机器验证关闭了哪些 C7 未知？ → 关闭并固化：fresh-install 原始日志与版本/help 证据；同一 SQLite composition owner 跨 0.138.0→0.139.0→0.138.0 的 schema/config/ledger identity 保持和失败恢复 machine contract；vendor/transitive 依赖组件边界与 Cargo.lock 数量盘点。C7/G7 仍 unknown/stop：人工 backup/restore 与 fault diagnosis stopwatch、完整逐包 NOTICE/商业/API/商标审查、独立 reproducible rebuild、真实远端账户/Provider/retention 退出责任、Codex native approval。 (ATAM：把安装 raw evidence、owner schema/config/ledger、受控失败、vendor 依赖清单分别收窄，不跨 gate 推断；CBAM：保持一个 Codex runtime + 一个薄 SQLite owner，新增 runner 只用于隔离验证，不引入常驻服务。)
- Q: 本次真实 owner-backed backup/restore stopwatch 是否关闭对应人工门？ → 关闭 backup/restore 的人工时间门：单一操作者在隔离、case-local SQLite composition owner 与 loopback-only Provider 上完成 backup、损坏注入、restore 和 verifier；人工耗时 12.38 秒（0.2063 分钟），低于 ≤30 分钟阈值，verifier status=pass，20/20 operation checks=true。该结果记为 fixture-level human timing pass，不宣称生产 ledger 的 retention、加密、跨版本迁移、远端备份或灾难恢复已签核；C7/G7 仍 unknown/stop，fault diagnosis stopwatch、NOTICE/商业边界和真实远端退出责任等门继续保留。 (基于 evaluation/runs/w7-codex-c7-human-20260831T180332 的 operation-result.json 与 README；人工 stopwatch 与 machine_elapsed 分开记录。)
- Q: 本次预制故障定位 stopwatch 是否关闭对应人工门？ → 关闭预制 fault diagnosis 的人工时间门：单一操作者在固定、case-local、无网络/无凭证/无生产数据的 fault fixture 上完成 fault/run 关联读取、故障分类、影响范围与当前未知判断、bounded next action 编写和保存；耗时 2 分 51.31 秒（2.85517 分钟），低于 ≤30 分钟阈值。human-diagnosis.md 字段与 fault_id/run_id 一致，保留 candidate_provenance_unknown，不将 unknown 静默升级为 pass，且无额外专家。该结果为 fixture-level human timing pass，不宣称生产故障定位、完整供应链审计或 C7/G7 总体签核已完成。 (基于 evaluation/runs/w7-codex-c7-20260830T172916-565440Z/cases/fault_diagnosis/repeat-01/human-diagnosis.md（SHA-256 7966f449bd94bd5ea93a2da1bf03fca580d932f3444f568bb60e2492c27d2fe341）与同 case 的 machine operation-result.json。)
- Q: 故障诊断人工证据的 canonical SHA-256 是什么？ → 以实际文件重新计算的 SHA-256 为 7966f44994bd5ea93a2da1bf03fca580d932f3444f568bb60e2492c27d2fe341；此前记录中的 7966f449bd94… 为录入笔误，已在 w7-codex-c7-human-timings.json 修正。2 分 51.31 秒和 fixture-level pass 判定不变。 (Canonical file: evaluation/runs/w7-codex-c7-20260830T172916-565440Z/cases/fault_diagnosis/repeat-01/human-diagnosis.md；以 shasum -a 256 重新核对。)
- Q: 本次完整安装人工计时是否已与同一次 raw log 绑定？ → 已绑定：单一操作者在临时 C7 npm prefix 中完成 Codex 0.139.0 全新安装、版本验证、app-server --help、npm tree 和四个 artifact digest 核对；人工 stopwatch 为 17.01 秒（0.2835 分钟），同一次 raw log 出现 === C7_INSTALL_T_END_SAVED === 结束标记，日志 SHA-256 为 6db2fe3abaf3febe72ab6a6acbd282e587daf1876b7c5cb255fd66e7eaefecb5，四个 digest 与候选 manifest 一致。该结果关闭 fresh-install 人工日志绑定门，并不改变 C7/G7 overall unknown/stop。 (ATAM：将安装可操作性与候选完整生命周期、法律/NOTICE、远端退出和独立重建分开计量，不跨门推断。CBAM：仍保持一个 Codex runtime + 一个薄 SQLite composition owner，不新增常驻服务。)
- Q: NOTICE/商业边界处理后，C7 的签核状态和允许范围是什么？ → 已将 NOTICE/商业边界从完全未知收窄为 bounded-evidence / signoff-open：固定版本 Codex 的 LICENSE、vendor/transitive 依赖盘点、OpenAI 服务协议/个人服务条款/使用政策/品牌指南一手来源及工程边界地图均已记录。个人开发者或小团队可在各自机器上自行安装固定版本做受控内部试用，前提是 ZWorkbench 不捆绑或再分发 Codex artifact、不共享或转售账户/API key、不用个人 ChatGPT 服务账户驱动共享或对外 SaaS、不使用 logo 或暗示背书；OpenAI API 产品集成仍需按账户、数据、地区、服务协议和产品责任单独确认。完整逐包 SPDX/版权/NOTICE/例外 clearance、再分发材料、商业/API/账户/数据模式、商标/归属审查和远端退出责任未签核，因此 complete_notice_signoff 与 commercial_api_trademark_signoff 继续为 false，C7/G7 继续 unknown/stop。 (ATAM 将条款事实、组件 NOTICE、商业模式和退出责任拆为独立敏感点；CBAM 维持一个 Codex runtime + 一个 SQLite composition owner，不为合规审计引入第二 Harness、常驻 gateway 或观测服务。边界地图见 docs/plans/research/w7-codex-c7-notice-commercial-boundary.md。)
<!-- ROADMAP_SECTION_END -->
