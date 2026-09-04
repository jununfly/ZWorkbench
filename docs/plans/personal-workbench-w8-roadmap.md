<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `personal-workbench-w8-roadmap.json` | 最后更新: 2026-09-05 02:15:32

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
    ├── [x][Y+] 1-9-5. H4 中断恢复与进程生命周期：无孤儿 Worker
    ├── [x][Y+] 1-9-6. H5 Evidence/replay：记录 owner 证据并隔离回放模式
    └── [~][X+] 1-9-7. 真实远程 Provider 兼容性：隔离 staging 与 owner-facing contract

### 当前施工：1-6-3-2. DNS 宿主拒绝与 Codex host profile 联合继承

最终 external-sandbox acceptance/evaluation 摘要 final2：host-profile candidate 子面 6/6 pass；native approval 0/6 request，6/6 真实进入 waitingOnApproval，request→decision→resolved→completed 链缺失，L2 unknown/stop。runner receipt 显式记录 approval_wait_observed 与 wait kind；节点保持 HOLD，真实写操作禁止。下一步仅查明固定 runtime/transport 的 native request 可观察性，不修改默认产品 runtime。

**决策：**
- Q: broker 化可观察边界采用什么 interface？ → 新增 acceptance/evaluation 专用 case-local CapabilityBroker interface：request 只包含 operation、resource class、target、request_id 和固定 policy identity；broker 先持久化 policy decision，再执行允许的 case-local effect，并返回 decision/reason/policy_sha256/effect_status/physical_effect_count/external_io_count。DNS 使用 broker 内静态 allowlist，不调用系统 resolver；非 loopback network、credential.read、未声明 process.spawn 和 workspace 外 write 必须在 broker 内显式 deny。该 interface 不进入 src/zworkbench 默认产品运行时，不接触真实 Provider/API key，不证明 Codex host profile inheritance 或 native approval。 (这是 acceptance/evaluation 的新可观察 seam：用显式 broker receipt 解决 system resolver gaierror 无法作为 host denial 的问题；未知协议/未知 operation/缺少 identity 一律 deny/unknown，Codex→host profile 联合继承仍单独 HOLD。)
- Q: CapabilityBroker candidate evidence 是否关闭 1-6-3-2？ → 不关闭。case-local broker 已在 9 个场景、每场景 3 次中达到 27/27 candidate-pass，并提供 request→policy digest→decision→effect receipt；但这不证明 Codex host profile 联合继承，也不产生 Codex native approval request/decision。继续保持 1-6-3-2 为 blocked/HOLD，真实写入禁止。 (正式证据：evaluation/runs/w8-capability-broker-20260905-rerun2/summary.json；real_provider、real_credentials、real_project_write 均为 false；默认产品运行时未改动。)
- Q: 本轮如何验证 Codex host-profile 继承与 native approval？ → 新增 acceptance/evaluation 专用 external-sandbox Codex runner：固定 Codex 0.139.0 在 macOS sandbox-exec targeted profile 内启动，turn/start 使用官方 v2 sandboxPolicy.type=externalSandbox；loopback fake Responses Provider 只发 case-local direct_write 命令。host-profile 通过必须同时满足 commandExecution started/completed、子进程 ancestry 含 Codex PID、越界写返回 PermissionError/预期退出码且哨兵未改变，以及 workspace allow 控制成功。native approval 通过必须观察真实 item/commandExecution/requestApproval，记录 request 的 thread/turn/item identity，客户端返回 decline 或精确 accept，随后观察 serverRequest/resolved 与 item/completed；缺 request/decision/identity 继续 unknown。 (不改 src/zworkbench，不使用真实 Provider/凭证/工作区；所有外部网络仅 loopback fake Provider，所有写入仅 case-local。正式结果按 host inheritance 与 native approval 分开计分，不以 protocol schema、approvalPolicy 字段或目标未变化替代事件证据。)
- Q: external-sandbox 联合继承与 native approval 重跑结果是什么？ → 固定 Codex 0.139.0 在 macOS sandbox-exec targeted profile 内，使用显式 w8-loopback Responses provider、case-local ready/release probe 与 v2 turn/start.sandboxPolicy.type=externalSandbox 完成 12 case（4 场景×3 次）：host-profile 越界拒绝和工作区允许均 3/3，Codex PID 到 direct child ancestry 与 commandExecution started/completed 可观察，合计 6/6 candidate-pass；native approval decline/accept 合计 0/6 request，Codex 进入 waitingOnApproval 但未向 stdio client 发出 item/commandExecution/requestApproval，因此 request→decision→serverRequest/resolved→item/completed 链仍 unknown/stop。节点保持 in_progress/HOLD，真实写入不放行。 (正式摘要为 evaluation/runs/w8-external-sandbox-native-approval-20260905-final1/summary.json；修复了绝对 fixture 路径、临时 loopback 端口、显式 provider 配置和 ready/release terminal 观察窗口。仅 acceptance/evaluation，src/zworkbench 默认 runtime、真实 Provider、真实凭证和真实项目均未使用。)
- Q: final2 正式摘要路径纠正 → 正式摘要路径为 evaluation/runs/w8-external-sandbox-native-approval-20260905-final2/summary.json；该路径对应 12 case、6/12 pass、6/12 unknown/stop，host-profile 6/6 candidate-pass，native request 0/6 且 waitingOnApproval 6/6。 (上一条决策的路径文本曾被 shell 特殊字符吞掉；本条使用纯文本路径。)
<!-- ROADMAP_SECTION_END -->
