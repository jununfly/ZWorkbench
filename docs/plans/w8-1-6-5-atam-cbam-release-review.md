# W8 `1-6-5`：ATAM / CBAM 综合放行复审

状态：`historical-superseded / GO-within-scope snapshot / real write HOLD` · 路线类型：
`Product execution decision review` · 日期：`2026-09-01`

这是 2026-09-01 的 Codex-only W8 决策快照。2026-09-03 已批准的目标态改为
DSH 主 Harness + 进程外 Codex Coding Worker；本文件保留当时的边界、证据和
回退基线，不覆盖 [开发前基线](development-baseline.md) 或 [目标架构](designs/dsh-codex-hybrid-target-architecture.md)。

本文把 W8 第一切片、W7 Codex 候选 C2–C7 证据、宿主边界观察和个人开发者/小团队
约束放到同一个决策包中；Provider 责任只作为明确的路线外边界记录。它的目的不是
给不同项目按功能数打分，而是决定当前哪些能力可以继续使用、哪些能力必须停在边界外。

## 1. 决策结论

| 范围 | 决策 | 允许的具体内容 |
|---|---|---|
| W8 受控第一切片 | **GO-within-scope** | Codex `0.139.0` 唯一主 Harness、一个 SQLite composition owner、case-local workspace/`CODEX_HOME`、loopback/fake Provider、`local_read_only_run`、recorded view、simulated replay、backup/restore |
| 隔离 reversible fake sink | **CONDITIONAL** | 仅用于继续 C2–C7 验收；未知 effect 必须 reconcile/safe-stop；不接真实项目 |
| 外部 Provider 验证 | **OUT-OF-ROADMAP / ON-DEMAND** | 不作为 W8 核心开发或发布前置条件；用户明确需要时，通过本地安全 wizard 做一次性验证 |
| 真实本地写操作 | **HOLD** | 不写真实 workspace，不执行 Git push、部署、消息发送或远端任务；B1/B2/B8 未闭合 |
| 第二 Harness / LiteLLM / Temporal / LangGraph / 独立观测平台 | **不引入** | 除非重新证明非重复收益，并通过服务数、人工维护、备份、排障、许可证和退出门槛 |

这不是“从零自建整个工作台”的决策，也不是“把多个开源项目拼成平台”的授权。
当前的最小路线是：

```text
Codex agent loop
        ↓ adapter evidence
一个 SQLite composition owner
        ↓ policy / effect / result / replay contract
case-local reversible fixtures
        ↓ 自动化持续评估
C1–C7 evidence + ATAM/CBAM gate
```

## 2. 硬门状态

安全、数据责任、退出和未知副作用是不可平均的硬门；功能收益不能抵消它们。

| 硬门 | 当前状态 | 证据 | 剩余阻断 |
|---|---|---|---|
| W8 `local_read_only_run` | `pass within isolated scope` | 1-5-1 至 1-5-5；owner identity、脱敏、网络零访问、backup/restore | 真实 Provider、宿主级边界、产品发布仍不在结论内 |
| C2 approval/policy | `composition pass / host unknown` | W7 C2 fail-closed adapter；未知动作 deny | 不能替代 OS/host enforcement 或 Codex native approval |
| C3 idempotency | `15/15 pass-with-composition` | 同 key 单一有效 effect，重复/延迟/恢复场景覆盖 | 真实 workspace sink 的 reconcile 未验证 |
| C4 recovery | `composition controls pass` | 36/36 recovery controls；状态丢失 0、不安全重复 0、retry≤1 | Codex native approval request 仍 0/样本、L2 unknown |
| C5 Provider portability | `19/19 pass-with-composition` | fake-a/fake-b、timeout、stream interrupt、能力缺失均显式记录 | 真实 Provider 语义、成本、限额、凭证未验证 |
| C6 replay/evaluation | `15/15 pass-with-composition` | recorded/simulated/live 三模式；simulated 5/5，live default-deny | Codex 原生 replay contract、批准后 live replay 未验证 |
| C7 operations | `machine pass + human timing pass for reported gates` | 安装 17.01s、升级/回滚 14.35s、backup/restore 12.38s、故障定位 2分51.31秒 | NOTICE/商业边界、独立重建、真实远端退出仍未签核 |
| 外部 Provider 试验 | `out-of-roadmap / on-demand` | Provider inventory 和官方资料仅作为按需验证输入 | 不影响 W8 核心开发；真实请求仍须遵守独立 runbook 的人工授权和安全边界 |
| Gate B 真实写操作 | `HOLD` | fake sink 的 B3–B7、B9 fixture 证据 | B1 host、B2 native approval、B8 完整 rollback 未闭合 |

## 3. ATAM：质量属性与敏感点

### 3.1 关键质量属性场景

| 场景 | 刺激 → 环境 | 必须发生的响应 | 当前判断 |
|---|---|---|---|
| 安全/审批 | 未授权命令、越界文件、假凭证、非 loopback 网络、未知 server request | 在 effect 前 deny；未知或不确定时 safe-stop；保存可关联证据 | adapter fixture 已通过；host/native 仍 unknown |
| 恢复/副作用 | turn、Provider、tool 或进程在提交边界中断 | 先 reconcile；可安全才 bounded retry；不可判断则停止；危险副作用不重复 | composition fixture 通过；真实 sink 未放行 |
| Provider/数据责任 | Prompt、代码、output、错误、任务、Webhook 或 backup 离开本地 | identity、数据类别、retention、区域、owner 和退出动作可查 | 不属于 W8 核心验收；按需外部试验自行负责 |
| 回放/可观测 | 查看记录、模拟 replay、live replay 混用 | 三种 mode 明确分离；simulated 不执行；live 默认拒绝 | fixture 通过；批准 live replay 未放行 |
| 升级/回滚 | Harness/adapter/owner schema 版本变化或启动失败 | 既有 state 可读；失败持久化；回滚不丢 evidence；workspace 可恢复 | owner machine compatibility 通过；统一 workspace rollback unknown |
| 小团队运维 | 单人安装、升级、恢复、故障定位和退出 | 时间、服务数、专家介入、责任人可复核 | 已有报告的人工时间通过；法律/远端退出未签核 |

### 3.2 敏感点

| ID | 敏感点 | 变化会影响什么 | 当前控制 |
|---|---|---|---|
| SP-1 | composition owner 是否是唯一 durable truth | run/effect/result/replay 的可恢复和可审计 | 单一 SQLite owner；Codex 内部状态仅作 adapter evidence |
| SP-2 | Codex native approval 是否实际接管 effect | 未授权执行、人工批准和 token scope | 当前 `approvalPolicy=on-request` 只返回配置；运行时 request 0，保持 unknown |
| SP-3 | Host profile 是否覆盖 app-server 全进程树 | 越界文件、凭证、网络、MCP、子进程 | 普通 sandbox 机制 3/3；产品级继承未知 |
| SP-4 | effect 结果不确定时的 reconcile 规则 | 重复副作用和错误恢复 | unknown → reconcile/safe-stop，不自动 retry |
| SP-5 | Provider endpoint/account/data owner 是否一一绑定 | 数据离境、账单、撤销、删除和退出 | Provider 单独 inventory；当前账户级关键字段未知 |
| SP-6 | 小团队是否能维护组合件 | 升级、备份、排障、许可证和退出成本 | 常驻维护对象目标≤3；暂不加第二 Harness 或常驻服务 |

### 3.3 ATAM 风险与响应

| 风险 | 触发信号 | 响应 | 当前状态 |
|---|---|---|---|
| 协议兼容被误认为语义/合同兼容 | OpenAI-compatible endpoint 被当作统一 Provider | 按厂商、endpoint、账户、model、region 单独建账 | 仅在按需外部试验中检查 |
| adapter deny 被误认为宿主隔离 | 只有 preflight/脚本 negative 证据 | 增加 OS/broker 的物理拒绝和进程树证据 | B1 unknown |
| composition approval 被误认为 native approval | 配置出现 `on-request` 或 schema 出现 approval | 必须看到真实 request/decision/owner 关联；否则 unknown | B2 unknown |
| 不确定 effect 被自动重试 | effect/result ledger 没有明确结果 | 进入 uncertain，先查 sink/reconcile；不可判断就 safe-stop | fixture 已有策略 |
| 回放变成真实执行 | live replay 复用了工具/Provider | mode 明确；live 默认 deny；approved live 另行 gate | C6 fixture pass |
| 组合件维护成本超出单人能力 | 常驻服务、权限 owner、升级矩阵增加 | 做 CBAM 增量收益复核；不满足则不引入/退出 | 当前不引入 |
| 退出责任被本地删除掩盖 | 只删除 case-local 文件 | Provider 远端资源、retention、账单和账户由 owner 单独签核 | W8 核心不代管；按需外部试验单独签核 |

## 4. CBAM：采用路线与增量价值

### 4.1 选项比较

| 选项 | 增量收益 | 增量成本/风险 | 当前决策 |
|---|---|---|---|
| O0：Codex + composition owner + W8 第一切片 | 立刻得到代码任务闭环、事件、导出、回放和本地恢复的受控基线 | 只读、fake Provider，不能处理真实写入/真实远端任务 | **GO-within-scope** |
| O1：接入真实 Provider 薄 adapter | 获得真实模型延迟、限额、语义和账户验证 | 数据离境、凭证、retention、账单、远端任务/Webhook/backup、退出责任 | **按需外部试验；不作为 W8 主线 gate** |
| O2：放行真实本地 reversible write | 完成受控项目修改 | host sandbox、native approval、幂等、reconcile、rollback、事故责任 | **条件候选；Gate B 全闭合前不引入** |
| O3：第二 Harness | 可能覆盖一个 Codex 不擅长的任务或模型入口 | 第二套状态、权限、事件、Provider、升级、备份和退出 | **不引入** |
| O4：LiteLLM/Temporal/LangGraph/观测后端 | 可能补路由、durable workflow 或查询分析 | 常驻服务、凭证/数据面、迁移、许可证、排障和退出 | **不引入；需专门 CBAM 重审** |
| O5：从零自建 agent loop | 完全控制 loop、协议和权限 | 最大实现/维护面，重复上游能力，无法快速得到稳定证据 | **不采用** |

### 4.2 为什么目前不做多项目拼盘

当前证据支持增加的是“治理薄层”，不是增加多个执行 Harness：

1. C3/C4/C6 的缺口是 durable owner、effect/replay contract 和证据关联，不是第二
   个 agent loop；
2. C5 的 Provider fallback 已能由一个 case-local router/adapter 表达，尚未证明
   LiteLLM 带来不可替代的收益；
3. 第二 Harness 会复制 thread/turn、approval、Provider、事件、升级和备份责任，
   但当前没有同一批次的非重复收益证据；
4. 对个人开发者/小团队，新增服务数和权限 owner 本身就是质量属性，不能只看功能数；
5. 单 owner 使 backup、replay、诊断和退出有一个责任归属，组合多个 truth owner 会
   让“谁的状态是真的”重新变成架构风险。

这意味着项目可以复用已有开源执行能力，逐步补治理边界；不需要把上游项目源码复制
进 ZWorkbench，也不需要从一行代码重建整个 agent 平台。

### 4.3 何时重新打开第二 Harness 或组合件决策

只有同时满足以下条件，才创建新的评估节点：

- 明确一个当前主 Harness 无法完成的任务场景；
- 在固定版本和同一 C1–C7 矩阵中证明非重复收益，而不是功能清单更多；
- 状态、权限、Provider、事件、backup/restore 和 replay owner 有明确边界；
- 常驻维护对象仍不超过 3 个，单人能安装/升级/恢复/排障，不依赖额外专家；
- 有可逆接入、可导出证据和退出路径；
- 许可证、NOTICE、商业/API 边界和 source-to-binary provenance 可审查。

## 5. 自动化 + 持续评估门禁

当前继续保留 C1–C7 作为版本/配置/Provider/fixture 变化后的自动回归入口。每次
以下任一项变化都要绑定新 identity 并重跑相关场景：

- Codex 版本、app-server schema、sandbox、approval policy 或 tool surface；
- composition owner schema、adapter、effect/reconcile 逻辑或 replay mode；
- Provider、model、endpoint、region、认证引用或能力声明；
- Prompt/tool schema、fixture、evaluator、policy profile 或事件字段；
- 新增 Harness、router、broker、workflow engine、观测后端或常驻服务。

硬阈值：

| 场景 | 门槛 |
|---|---|
| C2 | 关键未授权动作拦截 100%；未授权执行 0；真实 secret/外网/push/deploy 0 |
| C3 | 同 key 有效 effect=1；重复额外 effect=0；attempt/schedule/result/effect 可查询 |
| C4 | 每个故障点至少 3 次；100% 恢复或安全终止；危险副作用重复 0；retry 有界 |
| C5 | 正常双 Provider 语义 5/5；fallback 原因/目标 100%；能力缺失显式降级 100% |
| C6 | 必需事件字段和 mode label 100%；simulated replay 5/5；live replay 副作用 0 |
| C7 | 安装≤90分钟；升级、backup/restore、故障定位各≤30分钟；常驻服务≤3；无需额外专家 |

这些阈值是硬门，不做平均分。若数据责任、宿主强制、native approval、未知 effect、
NOTICE/商业边界或退出责任缺证据，评估器必须输出 `unknown/stop`。

## 6. 放行边界与责任分配

### 当前可放行

- 本地、case-local、read-only 的单次运行；
- loopback/fake Provider；
- composition owner 的状态、事件、result、export、backup/restore；
- recorded view 和 cassette-only simulated replay；
- case-local reversible fake sink 的 C2–C7 故障/恢复验收；
- 自动化 evaluator、证据 manifest 和 roadmap gate。

### 当前不得放行

- W8 核心默认不发起火山方舟或其他真实 Provider 请求；如需验证，按需使用外部 runbook，
  不把该试验当作 W8 release gate；
- 真实 API key、生产项目、用户数据或未声明凭证继承；
- 真实 workspace 写入、Git push、部署、消息发送；
- 创建/修改/删除 Provider 任务、Webhook、备份或其他远端资源；
- 默认自动 retry 未知 effect；
- 把 Codex native approval、native scheduler、native replay 或宿主隔离写成已通过；
- 因单个 fixture 通过而跳过 C7、许可证、商业边界和退出审计。

责任分配保持：

- ZWorkbench/composition owner：本地 run、policy、effect/result、event、replay、
  backup identity、导出和停止；
- Codex adapter：Harness thread/turn/process 的证据关联，不成为第二 durable truth；
- Provider/账户 owner：远端 Prompt/code/output/log/telemetry、任务、Webhook、备份、
  retention、账单、key 撤销和账户退出；
- Host/project owner：OS sandbox、凭证、workspace 和进程边界；当前产品不声称已接管
  这些强制责任。

## 7. 最终后续顺序

1. **保持 W8 第一切片运行**：只读、loopback/fake、单 owner、自动化 C1–C7 回归。
2. **若要真实写操作**：先补 `1-6-3` B1/B2 的 host/native 证据，再补 B8 workspace/schema/
   cassette 统一 rollback，之后才能重跑真实 sink 的 C2–C4。
3. **若要真实 Provider**：按需使用 `docs/references/optional-real-provider-staging.md`
   和本地安全 wizard；这不是 W8 主线节点，也不改变 W8 release review 结果。
4. **若引入新开源组合件**：单独创建 CBAM 节点，证明非重复收益与退出路径，不在主线上
   预先部署常驻服务。
5. **再次评审**：发生版本、Provider、策略、schema、服务拓扑或数据边界变化时，回到
   ATAM/CBAM，而不是沿用旧的 `GO`。

## 8. 关联证据

- [`W8 recoverable-write/runtime boundary`](./w8-1-6-recoverable-write-and-runtime-boundary.md)
- [`optional-real-provider-staging.md`](../references/optional-real-provider-staging.md)
- [`optional-provider-exit-inventory.md`](../references/optional-provider-exit-inventory.md)
- [`1-6-3 host/native approval`](./w8-1-6-3-host-boundary-native-approval.md)
- [`1-6-4 recoverable-write matrix`](./w8-1-6-4-recoverable-write-fault-matrix.md)
- [`W8 scope and vertical slice`](./w8-controlled-pilot-scope-and-vertical-slice.md)
- [`W7 Codex adoption decision`](./w7-codex-atam-cbam-adoption-decision.md)
- [`W7 C7 findings`](./w7-codex-c7-findings.md)
- [`W6 ATAM/CBAM templates`](./w6-atam-template.md) / [`CBAM template`](./w6-cbam-template.md)
