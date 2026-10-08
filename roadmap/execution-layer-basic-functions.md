<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `execution-layer-basic-functions.json` | 最后更新: 2026-10-08 22:47:29

[~][X+] 1. 执行层基本功能 — 讨论结论落地路线
├── [x][Y+] 1-1. Provider 适配与降级（sub-05）
│   ├── [x][Y+] 1-1-1. P0 fallback 审计硬化：fallback 计账落 owner-backed + reason 缺失即拒绝回归（<1.5 人日）
│   ├── [x][Y+] 1-1-2. P1 attempt 计账入 owner（扩展 provider_exit_ledger 或新增 retry_budget_ledger）
│   ├── [x][Y+] 1-1-3. P1 Provider 级 retry 预算表（声明 owner + 上限 + attempt/failure_class/target/reason，~2.5 人日）
│   └── [x][Y+] 1-1-4. P1 真实 Provider gate 收口（真实路由/计费接入受控 gate，~2 人日）
├── [x][Y+] 1-2. 证据与回放（sub-06）
│   ├── [x][Y+] 1-2-1. P0 DSH Harness 端到端三模式收口（recorded/simulated/live 串成契约 + 回归测试）
│   ├── [x][Y+] 1-2-2. P1 provenance↔IdentityChain 会话级关联 + 空串识别为缺失
│   ├── [x][Y+] 1-2-3. P1 live 零外部执行断言守卫（断言式计账，非结构性）
│   └── [x][Y+] 1-2-4. P1 owner 增 evidence 来源枚举字段（native/plugin-composed/outer-composed）并强制分类
├── [x][Y+] 1-3. 终止与资源生命周期（sub-07）
│   ├── [x][Y+] 1-3-1. P1 DSH adapter 增 process_group_clean/orphan 字段 + 验证 setsid 子进程不误报 0
│   ├── [x][Y+] 1-3-2. P1 退出账本对称接线（调用点配对：谁在何时记哪边）
│   ├── [x][Y+] 1-3-3. P1 常驻服务 runtime registry，强制 ≤3 上限
│   ├── [x][Y+] 1-3-4. P1 fail-stop 升级契约（不可处理→fail-stop，非 silent unknown）
│   └── [x][Y+] 1-3-5. C7 真实世界退出记账（safe-stop Provider-side：远端 retention/账单/本地退出≠Provider 退出，owner-backed 证据补齐）
├── [x][Y+] 1-4. 执行层 effect 授权（sub-04）
│   ├── [x][Y+] 1-4-1. P1 owner schema 增 declared_side_effects/exposure 字段 + Q4 preflight deny 逻辑（越界 workspace/未声明网络·凭证·子进程）
│   ├── [x][Y+] 1-4-2. P1 create_worktree case-local 校验 + apply_diff 加 resource==worktree_path 断言 + repo 指纹校验
│   ├── [x][Y+] 1-4-3. P1 complete_run 在 read-only 路径 finally 显式闭合（统一 run 闭合锚点）
│   └── [x][Y+] 1-4-4. P1 read-only 二选一落文（preflight 准入即授权、不进 claim seam）+ 补测试
├── [~][Y+] 1-5. Run 生命周期编排（sub-01）
│   ├── [x][Y+] 1-5-1. P0 complete_run 拒绝未决 approval + 关键 identity 缺失（调 detect_identity_violations + 查 approvals pending；无 schema 变更）
│   ├── [x][Y+] 1-5-2. P1 run 级 restart 预算 + 跨层（DSH/Worker/Provider）retry 单一 owner 计账
│   └── [ ][Y+] 1-5-3. P1 caller-auth 缺口（ZW_OWNER_SANDBOX=1 弱化 fail-closed）真实架构前硬前置
├── [x][Y+] 1-6. 唯一 owner 持久化（sub-03）
│   ├── [x][Y+] 1-6-1. P0 secret 不入 owner：external_receipt 必经拒密 + 值级扫描
│   ├── [x][Y+] 1-6-2. P1 run 级 attempt 一等实体决策
│   ├── [x][Y+] 1-6-3. P1 无第二 canonical 升可审计契约（audit_owner_isolated + CI 断言）
│   ├── [x][Y+] 1-6-4. P1 unknown 术语拆两层（远端/委托侧存字面 unknown；内部 identity 缺失 safe-stop 不存值）
│   └── [x][Y+] 1-6-5. P1 create_run 不拒密：run input/metadata 归 redaction 模型（owner 存原始、view 遮罩），值级拒密仅限外部 evidence 落库 seam
├── [ ][Y+] 1-7. Worker 调度与监督（sub-02）
│   ├── [ ][Y+] 1-7-1. P0 Q4 双重钳制（worker_bridge 构造处 assert replay_mode==normal + WorkerBridge 加 real_worker_mode: bool=False）
│   ├── [ ][Y+] 1-7-2. P1 H1/H3/H4 fixture 补齐（BLOCKED→落地，含心跳/lifecycle cancel/stop_parent/recover）
│   ├── [ ][Y+] 1-7-3. P1 IdentityChain 完成性分层（须 ADR：required vs UNKNOWN 分级，停止 fake 编造 codex 身份）
│   └── [ ][Y+] 1-7-4. P1 真实 Worker 硬前置（host sandbox / 值级拒密 / 出站脱敏 / reaper killpg / digest 校验）
├── [ ][Y+] 1-8. 真实架构硬前置（共享）
│   ├── [ ][Y+] 1-8-1. host sandbox（seatbelt/namespace/unshare）作为真实 Workspace 写入前置
│   ├── [ ][Y+] 1-8-2. 值级拒密 _reject_secrets 扫描（覆盖 external_receipt + stdout/stderr）
│   ├── [ ][Y+] 1-8-3. semantic_result / codex_adapter.close() stderr 出站脱敏
│   ├── [ ][Y+] 1-8-4. bridge 进程异常退出 reaper 兜底 killpg
│   └── [ ][Y+] 1-8-5. worker 可执行体 digest 实测校验
├── [ ][Y+] 1-9. 首跑与 onboarding（R4 缺口：target/unknown）
│   ├── [ ][X+] 1-9-1. 零配置首跑脚手架（run --prompt 自动 case-root/workspace/state + --codex PATH 探测 + 默认 fake-loopback）
│   ├── [ ][X+] 1-9-2. 只读自检 doctor（探测 Codex 可执行性 / case 目录约定 / loopback 可达 + readiness 报告 + 每项 fix hint）
│   ├── [ ][X+] 1-9-3. 价值演示缝合（run 末 stdout 追加 next_steps 数组 + --open 自动拉起 ui-host，仍 loopback 只读）
│   ├── [ ][X+] 1-9-4. fail-closed UX 成本回收（PreflightViolation.hint + timeout/failed 区分 + 重试提示）
│   └── [ ][X+] 1-9-5. 端到端首跑回归脚本（fake-loopback、零凭证、recorded_view_present 验证；依赖 #40/S0 解后补测）
└── [ ][Y+] 1-10. solo 真实可用 / 真实可用路线图（R3 缺口：in-progress/partial）
    ├── [ ][X+] 1-10-1. S0 host-enforcement spike（ADR 0008 三判据出证：独立约束路径/进程/网络，失效即拒启动）；↩ ADR 0010 撰写时编号 1-9-4（B2 spike），其 1-9-* 引用为旧编号，见 ADR 0010 顶部「路线图节点引用勘误」
    ├── [ ][X+] 1-10-2. S1 单 Provider 产品化（Ark 无 failover；issue #39 pre-gate：identity<->transport 单一来源 + 删 setdefault 反填 + 4 条 fail-closed 测试）
    ├── [!][X+] 1-10-3. S2 写 seam 产品验收（隔离 worktree diff apply + local commit；push 单独门；owner 层见执行层 1-4/1-5/1-7）
    ├── [ ][X+] 1-10-4. S3 dogfood N=10 闸门（连续 10 次默认入口全链路；acceptance evidence exercises_default_product_path=true）
    ├── [ ][X+] 1-10-5. S4 push 单独门（Git push 网关控，爆炸半径分级：diff apply→commit→push）
    ├── [ ][X+] 1-10-6. 价值基线实证（H1-H8/C1-C7 runner 出数：省 X% 时间 / 少 Y 次复查；作为继续投安全外壳前置论证）
    └── [ ][X+] 1-10-7. H6-full / H7 / H8 deferred-until-demand（标 deferred，不参与『可用』AND 门）
<details><summary>阻塞链：1 个节点被阻塞</summary>

- 1-10-3. S2 写 seam 产品验收（隔离 worktree diff apply + local commit；push 单独门；owner 层见执行层 1-4/1-5/1-7） ← e6: 1-10-1. S0 host-enforcement spike（ADR 0008 三判据出证：独立约束路径/进程/网络，失效即拒启动）；↩ ADR 0010 撰写时编号 1-9-4（B2 spike），其 1-9-* 引用为旧编号，见 ADR 0010 顶部「路线图节点引用勘误」 [ ]

</details>


### 下一步可开工（ready 前 3）

- 1-10. solo 真实可用 / 真实可用路线图（R3 缺口：in-progress/partial） [ ]
- 1-10-1. S0 host-enforcement spike（ADR 0008 三判据出证：独立约束路径/进程/网络，失效即拒启动）；↩ ADR 0010 撰写时编号 1-9-4（B2 spike），其 1-9-* 引用为旧编号，见 ADR 0010 顶部「路线图节点引用勘误」 [ ]
- 1-10-2. S1 单 Provider 产品化（Ark 无 failover；issue #39 pre-gate：identity<->transport 单一来源 + 删 setdefault 反填 + 4 条 fail-closed 测试） [ ]
<!-- ROADMAP_SECTION_END -->
