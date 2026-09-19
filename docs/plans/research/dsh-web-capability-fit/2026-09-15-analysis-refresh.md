# dsh-web 能力拟合结论增补

状态：working analysis；不是 fresh sealed-ledger report，也不是发布门禁通过的正式技术报告。

## 证据基线

- 源码仓库：<https://github.com/zhu1090093659/dsh-web>
- 固定 ref：`main`
- 固定 commit：`2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5`
- 固定 tag：`v0.3.22`
- 本地源码快照工作树：clean
- fresh GitHub sealed ledger：仍未生成。`research_cli.py --check` 通过，但 collect 的 compiler 阶段仍返回 `GITHUB_RATE_LIMITED`；本文件不使用 stars、topicMatch 或旧 ledger 推导能力结论。

本增补只使用固定 commit 的源码、包级说明和 ZWorkbench 当前代码做架构判断。源码事实可从以下 pinned 链接复核：

- [`dsh-session-id/package.json`](https://github.com/zhu1090093659/dsh-web/blob/2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5/packages/dsh-session-id/package.json)
- [`dsh-session-id/src/client/index.ts`](https://github.com/zhu1090093659/dsh-web/blob/2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5/packages/dsh-session-id/src/client/index.ts)
- [`dsh-session-id/src/client/SessionIdPanel.tsx`](https://github.com/zhu1090093659/dsh-web/blob/2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5/packages/dsh-session-id/src/client/SessionIdPanel.tsx)
- [`dsh-web-all/package.json`](https://github.com/zhu1090093659/dsh-web/blob/2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5/packages/dsh-web-all/package.json)
- [`dsh-web-all/src/client/mount-children.ts`](https://github.com/zhu1090093659/dsh-web/blob/2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5/packages/dsh-web-all/src/client/mount-children.ts)
- [`dsh-plugin-manager/src/host/gateway.ts`](https://github.com/zhu1090093659/dsh-web/blob/2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5/packages/dsh-plugin-manager/src/host/gateway.ts)
- [`dsh-remote-web-ui/src/index.ts`](https://github.com/zhu1090093659/dsh-web/blob/2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5/packages/dsh-remote-web-ui/src/index.ts)
- [`docs/telemetry.md`](https://github.com/zhu1090093659/dsh-web/blob/2629c3f55847c77549cdb251c0fe0e7f0d3d6cd5/docs/telemetry.md)

## 关键语义修正

“独立插件”必须拆成两个问题：

1. **独立发布形态：已证实。** `dsh-session-id` 有独立 package、版本、Apache-2.0 license、`dsh.bundle.patch`、`dsh.client` 注入声明、host/client 两半区和包级测试。
2. **脱离 DSH Web runtime 的嵌入能力：未证实且当前不成立。** 该包的 `apply()` 仍要求 `slots`、`locale`、`sessions`，并依赖 DSH client SDK；它只是 host half 无行为，不是 runtime 无关。

因此，dsh-web 能提供的是 **DSH Web 内的独立 plugin unit/reference implementation**，不是可直接塞入 ZWorkbench 当前 Python SSR host 的通用 React 组件。

## R × O 增补矩阵

| 需求 | 固定源码观察 | 对 ZWorkbench 的有效供给 | 判断 |
| --- | --- | --- | --- |
| 缩短 UI 从 0 到 1 | `dsh-session-id` 展示了 manifest、slot registration、locale、React surface、disposer 和测试的完整纵向切片；`scripts/dsh-plugin-new` 提供同形态脚手架 | 可复用设计模式和部分 source-level unit；不能直接复用运行时 | `adapted`，有效但不是 native |
| 独立安装/禁用/生命周期 | 每个包可通过 patch/profile 挂载；Cordis effect/slot registration 有释放路径；聚合包另有 child isolation/degraded ledger | ZWorkbench 没有 DSH profile/loader/slot host，故无法仅凭包声明完成 enable/disable/dispose | DSH 内 `native`；ZWorkbench `unknown` |
| 当前 UI 宿主兼容 | ZWorkbench 是 `ui_host.py` 驱动的 loopback、server-rendered HTML；`dsh_runtime.py` 只实现 artifact-mode H1 bootstrap，且要求空的 `headless-bootstrap` profile | 没有完整 DSH Web client runtime、browser slot、settings 或 remote API seam | `absent` for direct drop-in；profile adapter 是 future `unknown` |
| 本地优先、零默认外发 | `dsh-session-id` 的 UI 读会话并写 clipboard，但 `apply()` 默认调用共享匿名 heartbeat；telemetry endpoint 是 `https://dsh-market.com/api/telemetry/event` | 需要删/禁用遥测并以测试证明无请求；不能把原包原样计入零网络 PoC | 当前 `absent`；改造后 `adapted` |
| 不引入第二 durable owner | `dsh-session-id` 本身只读 `ctx.sessions.list`；但 task-board 有任务 store/scheduler/execution，plugin-manager 有 profile/plugin state，remote-web-ui 有 pairing/device/tunnel state | 只有最小只读 UI unit 有机会保持在 owner 边界外；整包或业务插件会引入语义冲突 | session-id `adapted`；其余多为 `incompatible` |
| 可复现构建和验证 | 包含 Vitest/TypeScript/build scripts 和针对 UI 行为的测试；根 workspace 有 lockfile和统一构建约定 | 未安装快照依赖，尚未在当前环境执行其 build/test；与 ZWorkbench 的 profile 联调没有证据 | source evidence `partial` |
| 许可证和退出 | 根仓库与候选包声明 Apache-2.0；包可被 profile 移除，源码可固定 commit | 仍需对实际选用的依赖闭合 NOTICE/license、锁版本和回滚验证 | `partial` |

## 选项重判

按《开源能力拟合决策模型》：

- **整套 dsh-web / `dsh-web-all`：D（继续搜索或拒绝该路径）**。它是聚合载具，不是单一 UI unit；自身会嵌套加载多个子插件并维护 degraded/active-row 状态，且依赖完整 DSH Web profile。把它接入 ZWorkbench 会把 DSH Web 变成第二套 UI/runtime/control boundary。
- **选择性复用独立 UI plugin 的模式：C（当前推荐）**。选一个无业务执行、无持久化、无远端请求的最小只读 surface，复用其 composition pattern、测试结构和语义属性约定；ZWorkbench 自己仍拥有 renderer、view model、owner 和生命周期。
- **通过薄 adapter/sidecar 接入真实 DSH plugin：当前不是 B1，未来可重新评估为 B1**。B1 的前提是已存在稳定的 DSH Web profile、client loader、slot/settings contract 和退出验证；当前 ZWorkbench 只有 H1 artifact bootstrap，不满足该前提。
- **继续自建 ZWorkbench UI，同时借鉴 dsh-web 模式：与 C 并行且风险最低**。对于现有 SSR host，应优先把成熟模式转译成本项目的 UI facade，而不是引入 React/Cordis runtime。

## 更新后的判断

总体判断保持“有价值，但不能整包吸纳”，但应比之前更精确：

> `dsh-web` 适合作为 ZWorkbench 的外部能力源和插件设计参考；当前不适合作为可直接安装的 ZWorkbench UI 插件依赖。最现实的收益来自选择性抽取其插件契约、slot/settings 组合思想、生命周期和测试方法，而不是复用其运行时或聚合包。

该判断不依赖 stars、README 宣称或旧 ledger，因此不会因 GitHub quota 阻塞而被夸大；quota 阻塞只保留了仓库元数据和正式 sealed-ledger publication 的信息缺口。

## 下一步验证与止损线

首个 PoC 应选一个 `session-id` 同等级的“只读 UI surface”，但用 ZWorkbench 的 DTO 和 SSR/现有 UI facade 重写宿主接缝，不把原包直接装进 ZWorkbench：

1. 固定源码 commit、依赖 lock、构建 receipt 和 profile identity；
2. 用显式 Host Capability Facade 提供脱敏 DTO，禁止插件读取 SQLite、Run event/effect/result 或 DSH session 文件；
3. 证明默认网络请求数为 0，尤其移除/隔离 dsh-web telemetry；
4. 证明 enable/disable/dispose 后 DOM、监听器、timer、子进程和网络请求归零；
5. 证明失败返回 `unknown/HOLD`，不影响 CompositionOwner 和现有 SSR host；
6. 对比“自建同一 surface”的交付时间、代码量、测试量和后续升级成本。

若 PoC 需要引入 DSH Web client runtime、动态 loader、profile patch、远端 API、独立 store/scheduler，或 adapter 开始拥有业务状态，则立即把该路线升级为 D 或停止投入，不再称为薄 adapter。

## 仍然保留的 unknown

- fresh sealed ledger 的 GitHub 元数据和 Evidence ID 尚未生成；
- 当前 ZWorkbench-specific profile 联调仍是 deferred/unknown；
- 未在 clean dependency install 下执行 dsh-web package 的 build/test；
- 未在真实运行时观察 Cordis dispose 后所有资源归零；
- 实际选用依赖树的完整许可证/NOTICE、版本 pin、升级和回滚尚未闭合。

这些 unknown 不改变“整包不适合、选择性模式值得 PoC”的方向性判断，但阻止把 PoC 或 `dsh-session-id` 的 DSH 内测试通过写成 ZWorkbench 已组合通过。
