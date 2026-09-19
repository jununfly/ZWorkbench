# dsh-web 能力拟合结论报告

**状态**：方向性结论已收敛（sealed-style draft）。**非** fresh sealed-ledger 发布门禁通过件——因 GitHub API rate limit，`fresh sealed ledger` 未生成，证据缺口见 §6。本报告仅基于固定 commit `2629c3f` 的源码事实、包级说明与 ZWorkbench 当前代码做架构判断。

**日期**：2026-09-19（增量收敛自 2026-09-15 的 working analysis：`2026-09-15-analysis-refresh.md`）
**目标仓库**：<https://github.com/zhu1090093659/dsh-web>

---

## 1. 证据锚点（固定，不可漂移）

- 仓库：`zhu1090093659/dsh-web`
- 固定 commit：`2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5`
- 固定 tag：`v0.3.22`
- 本地快照工作树：clean
- 可复核的 pinned 源码链接（见 `2026-09-15-analysis-refresh.md`）：`dsh-session-id/package.json` 与 `src/client/*`、`dsh-web-all/src/client/mount-children.ts`、`dsh-plugin-manager/src/host/gateway.ts`、`dsh-remote-web-ui/src/index.ts`、`docs/telemetry.md`。

> 所有结论只用固定 commit 的源码、包级说明与 ZWorkbench 当前代码推导，**不依赖 stars、README 宣称或旧 ledger**；quota 阻塞只保留元数据的证据缺口，不夸大能力结论。

## 2. 研究范围与硬约束（引 `2026-09-15-technical-decision-brief.json`）

**非目标（nonGoals）**：不把 dsh-web 整包 / 桌面客户端 / 创意工坊 / 远程访问平台迁入 ZWorkbench；不修改 DSH 源码、不复制 DSH Agent loop、不建立第二 CompositionOwner 或第二套跨 Run canonical state；不启用真实远程 Provider、第三方遥测、Cloudflare tunnel、Git push、部署或生产工作区写入；不宣称 ZWorkbench-specific profile 联调已完成。

**硬约束（constraints）**：

| id | 约束 |
|---|---|
| independent-plugin | 吸纳单元须保留 source/version/commit/digest、manifest、capability、permission、依赖、生命周期与 disposer，可独立禁用或移除 |
| owner-boundary | CompositionOwner 仍是 run/attempt/event/effect/result/approval/replay/backup-restore 唯一 durable owner；外部 UI 插件只能通过显式 Host Capability Facade 读写允许的投影 |
| runtime-compatibility | ZWorkbench 已证明的是 artifact-mode H1 bootstrap，不是完整 DSH Web profile / Cordis client slots / settings API / plugin loader；未验证能力不计入有效供给 |
| local-first-security | 首个切片必须 case-local，默认零远端请求、零遥测、零真实凭证，未知网络/子进程/写入边界 fail-closed |
| license-lifecycle | 仅考虑许可证与依赖来源可核验、版本可 pin、升级/回滚/退出责任可接受的复用 |
| experience-version | 当前处于 experience-version：可丢弃最小纵向切片 + 预定义成功阈值 + 明确止损线 |

## 3. 关键语义修正

"独立插件"必须拆成两个独立问题：

1. **独立发布形态——已证实。** `dsh-session-id` 有独立 package、版本、Apache-2.0 license、`dsh.bundle.patch`、`dsh.client` 注入声明、host/client 两半区与包级测试。
2. **脱离 DSH Web runtime 的嵌入能力——未证实且当前不成立。** 该包的 `apply()` 仍要求 `slots`/`locale`/`sessions` 并依赖 DSH client SDK；它只是 host half 无行为，不是 runtime 无关。

⇒ `dsh-web` 能提供的是 **DSH Web 内的独立 plugin unit / reference implementation**，不是可直接塞入 ZWorkbench 当前 Python SSR host 的通用 React 组件。

## 4. R×O 矩阵（需求 × 固定源码观察 × 有效供给 × 判断）

| 需求 | 固定源码观察 | 对 ZWorkbench 有效供给 | 判断 |
|---|---|---|---|
| 缩短 UI 0→1 | `dsh-session-id` 展示完整纵向切片（manifest/slot/locale/React surface/disposer/测试）；`scripts/dsh-plugin-new` 提供同形态脚手架 | 可复用设计模式与部分 source-level unit；不能直接复用运行时 | `adapted`（有效但非 native） |
| 独立安装/禁用/生命周期 | 每包可经 patch/profile 挂载；Cordis effect/slot 有释放路径；聚合包有 child isolation/degraded ledger | ZWorkbench 无 DSH profile/loader/slot host，无法仅凭包声明完成 enable/disable/dispose | DSH 内 `native`；ZWorkbench `unknown` |
| 当前 UI 宿主兼容 | ZWorkbench 是 `ui_host.py` 驱动的 loopback SSR HTML；`dsh_runtime.py` 仅实现 H1 artifact bootstrap 且要求空 `headless-bootstrap` profile | 无完整 DSH Web client runtime / browser slot / settings / remote API seam | 直接 drop-in `absent`；profile adapter 为 future `unknown` |
| 本地优先、零默认外发 | `dsh-session-id` UI 读会话写 clipboard，但 `apply()` 默认调用共享匿名 heartbeat；telemetry endpoint = `https://dsh-market.com/api/telemetry/event` | 需删/禁用遥测并以测试证明零请求；不能原样计入零网络 PoC | 当前 `absent`；改造后 `adapted` |
| 不引入第二 durable owner | `dsh-session-id` 只读 `ctx.sessions.list`；但 task-board 有 task store/scheduler/execution，plugin-manager 有 profile/plugin state，remote-web-ui 有 pairing/device/tunnel state | 仅最小只读 UI unit 可能保持在 owner 边界外；整包或业务插件会冲突 | session-id `adapted`；其余多 `incompatible` |
| 可复现构建/验证 | 含 Vitest/TypeScript/build scripts 与 UI 行为测试；根 workspace 有 lockfile 与统一构建约定 | 未安装快照依赖、未在本地跑其 build/test；与 ZWorkbench profile 联调无证据 | source evidence `partial` |
| 许可证/退出 | 根仓库与候选包声明 Apache-2.0；包可被 profile 移除，源码可固定 commit | 仍需对实际选用依赖闭合 NOTICE/license、锁版本与回滚验证 | `partial` |

## 5. 选项评估与决策

按"开源能力拟合决策模型"评估 4 个候选路径：

- **A 整套 dsh-web / `dsh-web-all` → D（拒绝）**：是聚合载具非单一 UI unit；自身嵌套加载多子插件并维护 degraded/active-row 状态，依赖完整 DSH Web profile；接入会把 DSH Web 变成第二套 UI/runtime/control boundary。
- **B 选择性复用独立 UI plugin 模式 → C（当前推荐）**：选无业务执行、无持久化、无远端请求的最小只读 surface，复用其 composition pattern、测试结构、语义属性约定；ZWorkbench 自己仍拥有 renderer、view model、owner 与生命周期。
- **C 薄 adapter/sidecar 接入真实 DSH plugin → B1（未来重评）**：前提是已存在稳定的 DSH Web profile、client loader、slot/settings contract 与退出验证；当前 ZWorkbench 仅 H1 artifact bootstrap，不满足该前提。
- **D 继续自建 ZWorkbench UI、同时借鉴 dsh-web 模式 → 与 C 并行且风险最低**：对现有 SSR host，优先把成熟模式转译为本项目的 UI facade，而非引入 React/Cordis runtime。

**决策（C + 并行 D）**：

> `dsh-web` 适合作为 ZWorkbench 的**外部能力源与插件设计参考**；当前**不适合**作为可直接安装的 ZWorkbench UI 插件依赖。最现实的收益来自选择性抽取其插件契约、slot/settings 组合思想、生命周期与测试方法，而不是复用其运行时或聚合包。

## 6. 证据缺口与 unknown（不静默闭合）

1. ~~fresh sealed ledger 的 GitHub 元数据与 Evidence ID 未生成——受 GitHub API rate limit 阻塞（2026-09-15 观测，anonymous 剩余 34/60）。~~ **已闭合（2026-09-19）**：`2026-09-19-sealed-ledger.json` 用 `gh api`（已认证，非原 zj-research-cli 二进制）拉取真实 GitHub 元数据，确认 tag v0.3.22 → commit `2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5` 锚点、仓库 public/Apache-2.0/TypeScript 等，EV-001/002/003 三条 Evidence + 整体 sha256 密封（ledgerHash `8f8ddca2…5ee8`）。该 ledger 仅闭合 GitHub 元数据缝隙，不覆盖 §6.2–§6.5 的 unknown。
2. ZWorkbench-specific profile 联调仍是 deferred / `unknown`。
3. 未在 clean dependency install 下执行 dsh-web package 的 build/test。
4. 未在真实运行时观察 Cordis `dispose` 后所有资源（DOM/监听器/timer/子进程/网络）归零。
5. 实际选用依赖树的完整许可证 / NOTICE、版本 pin、升级与回滚尚未闭合。

这些 unknown **不改变**方向性判断（整包不适合、选择性模式值得 PoC），但**阻止**把 PoC 或 `dsh-session-id` 的 DSH 内测试通过写成 ZWorkbench 已组合通过。

## 7. 后续 PoC 路径（含止损线）

首个 PoC 选 `session-id` 同等级的**只读 UI surface**，用 ZWorkbench 的 DTO + SSR / 现有 UI facade 重写宿主接缝，**不把原包直接装进 ZWorkbench**；六步验证：

1. 固定源码 commit、依赖 lock、构建 receipt 与 profile identity；
2. 用显式 Host Capability Facade 提供脱敏 DTO，禁止插件读取 SQLite、Run event/effect/result 或 DSH session 文件；
3. 证明默认网络请求数为 0，尤其移除/隔离 dsh-web telemetry；
4. 证明 enable/disable/dispose 后 DOM、监听器、timer、子进程与网络请求归零；
5. 证明失败返回 `unknown/HOLD`，不影响 CompositionOwner 与现有 SSR host；
6. 对比"自建同一 surface"的交付时间、代码量、测试量与后续升级成本。

**止损线**：若 PoC 需要引入 DSH Web client runtime、动态 loader、profile patch、远端 API、独立 store/scheduler，或 adapter 开始拥有业务状态，则立即把该路线升级为 D 或停止投入，不再称为"薄 adapter"。

## 8. 决策记录索引

关键方向性决策已落盘于路线图（`docs/plans/research/dsh-web-capability-fit/roadmap.json`）：

- 证据锚点（节点 1-1-3）
- 脱离 DSH runtime 嵌入不可行（节点 1-2-1）
- 采纳路径 C + 并行 D（节点 1-2-3）
- 报告形态与证据缺口边界（节点 1-3-2）

---

*本报告比 `2026-09-15-analysis-refresh.md` 更正式地收敛了结论，并显式承担证据缺口的诚实声明；原始 working-analysis 文件保留为增补底稿。*
