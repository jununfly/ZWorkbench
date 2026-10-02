# ZWorkbench 全量代码评审（root `4810fbc` → HEAD）

- 日期：2026-10-02
- 范围：全量代码库审计（工作区干净，无未提交改动）
- 对比基线：`4810fbc`（根提交，整库相对 root 均为新增）
- 代码范围（已排除 `evaluation/` 11366 个生成物/证据 与 `*.pyc`）：`src/`(33 .py) + `packages/`(TS) + `scripts/` + 根配置 = **61 文件 / 19185 行新增**
- 标准源：`AGENTS.md`（仓库无 `CODING_STANDARDS`/`CONTRIBUTING`）
- 规范源：全量审计无单一 issue；Spec 轴以 `AGENTS.md` 目标架构 + 长期硬约束作为设计契约校验

---

## Standards

Diff scope 审查了 61 文件 / 19185 行新增。代码库**整体高度符合标准**——无"不确定状态却静默 success"、无猴子补丁、无非法全局注册、失败语义 fail-closed。发现按严重度排序：

### HARD / 强标准违反

**§4 DSH plugin 规则——插件贡献缺少 disposer。** `packages/dsh-zworkbench-bootstrap/src/index.ts:99`
```ts
export function apply(ctx: Context): void {
  ...
  const session = sessions.create(SessionId(identity.dsh_session_id), { meta: { cwd: process.cwd() } })
```
`apply` 创建了一个 durable DSH Session 并注册，但返回 `void`，因此**未保留 disposer**。AGENTS §4 要求"所有贡献须经显式 registration/effect **并带 disposer**"，且"dispose 后所有已注册 … listeners/后台任务必须归零或有明确残留 owner"。对照 `invariant.ts:27` 正确返回 `() => void`。该 session effect 未被 dispose。*(HARD——与原文逐字对应)*

### JUDGEMENT calls（标准层）

**§1 Ownership——DSH Session 可能成为第二 owner 面。** `index.ts:113-122` 将 session 持久化到 `DSH_HOME`（`sessions.flush`），运行时只把 `dsh_session_id` 作为 evidence 记录（`dsh_runtime.py:558-560`）。仅当该 session store 永不被当作 source of truth 查询时才合规。建议加一条显式测试，断言 CompositionOwner 是 run/event/effect 状态的唯一 canonical owner。

**§4 plugin manifest——capability/permission 未自声明。** `packages/dsh-zworkbench-bootstrap/package.json` 仅含 `name`/`version`/`main`；无可机读的 capability/permission/dependency/lifecycle。gate 存在于 runtime-manifest 层（`dsh_runtime.py:130-262`），但插件自身的声明缝未钉死。值得加一条 host 侧断言。

### Baseline smells（恒为 judgement）

**Duplicated Code——3× 子进程 JSONL 监督器。** 相同形状出现在 `dsh_runtime.py:464-756`、`codex_adapter.py:133,494,501`、`worker_bridge.py:684-848,1158-1218`：`selectors.DefaultSelector` 读循环 + `killpg(SIGTERM→SIGKILL)` 拆除 + `MAX_*_LINE_BYTES` 上限。另有重复 helper：`_sha256_json`（`dsh_runtime.py:836` 与 `worker_bridge.py:1252`）、`_canonical_json`（`dsh_runtime.py:832`、`composition.py`）、`_file_digest`（`dsh_runtime.py:824`）。→ 抽出一个 `subprocess_supervisor` + 共享 digest 模块。

**Data Clumps / Primitive Obsession——`provider_identity`、`policy_identity`、`profile_identity` 为松散 dict。** 重复的 `{provider,model,endpoint,transport,metadata}` 形状贯穿 `provider_facade.py:82-101`、`dsh_runtime.py:339-355,468-480`。→ 收敛为一个小 `ProviderIdentity` 类型，单一 `to_dict`。

**Speculative Generality——`internals` stdout/stderr 间接层**（`index.ts:46-52`）仅为尚无产品集成的测试缝而存在；可接受，但若长期不用应删。

净：1 个 HARD §4 违反（缺 disposer）；其余为 judgement/软项。未发现 baseline smell 被某文档标准覆盖的情况。

---

## Spec

Spec 轴审计完成。证据来自 `git diff`（19k 行新增）、`AGENTS.md`、`roadmap.json`、`README.md`，并直接读取了 `composition.py` / `local_run.py` / `dsh_runtime.py` / `worker_bridge.py` / `cli.py` / `provider_facade.py`。

### (a) 目标要求但缺失 / 部分实现

1. **DSH 主 Harness** — `target/unknown`。README:3 写明"DSH 主 Harness 仍属 `target/unknown`"；`dsh_runtime.py` docstring（L6-12）为"H1 runtime seam… 未实现 DSH agent loop"。`cli.py`/`local_run.py` 未导入。顶层 loop 是 `LocalReadOnlyRunOrchestrator`（`cli.py:427`），非 DSH Harness。

2. **Codex 进程外 Worker bridge** — 模块存在，`unknown`（未接线）。`worker_bridge.py`（H2 handshake）在场，但 `grep` 显示 `cli.py`/`local_run.py` 均未使用；产品路径直接调 `codex_adapter`。AGENTS §1"首期以进程外 Worker 接入"未满足。

3. **Identity chain 可查询性** — `PARTIAL`/`unknown`。AGENTS §4："run_id → parent/child run → dsh session/turn → worker run → codex thread/turn → event/effect/artifact 可查询"。`composition.py` schema（L1069-1152）：`runs` 仅含 `run_id`；`events`（L1145）仅 `{event_id,run_id,type,payload}`；`effects/results/replays` 以 `run_id` 为键。无 `dsh_session/worker_run/codex_thread` 列。parent/child 仅作为 `runs.metadata_json`（L721）中的自由 JSON，非可查询 FK。深层 chain = `unknown`。

4. **插件经 Host Capability Facade** — `N/A`/`unknown`。Facade 已用于 Provider（`local_run.py:190` `adapter_factory=HostCapabilityFacade.acquire_provider`；roadmap 1-6-5 completed）。但 DSH 插件被禁用（`local_run.py:32` `REQUIRED_DISABLED_FEATURES={"plugins","apps"}`），故无插件组合/路由。Facade-for-plugins 路径未被执行。

### (b) 与设计矛盾

无静默矛盾。仓库如实标注 v1 为 Codex-only 回退（README/AGENTS）。一处范围注记：`approval_policy="never"`（`local_run.py:30`）与只读回退一致，不违反 AGENTS §4 审批规则。

### (c) 看似实现但错误

1. **Provider identity↔transport 偏差**（已知残留）。roadmap 1-6-3：`codex_adapter.py:126` 忽略 `profile.model_provider`，从 `identity['provider']='ark-test'` 派生 `model_provider`；CLI 用 `profile.name` 作 provider 字段——若 `authorized_provider` 设为 `custom` 会破坏 preflight。违反 AGENTS §4"Provider identity 不能静默替换" / #39 单一来源绑定。标记 `wrong-implemented/known`。

   **→ 已解决（2026-10-02）**：`codex_adapter.py` 改为 `model_provider` 优先取 `provider_identity["model_provider"]`（单一来源），缺失时取显式构造参数（facade 传入的 `profile.model_provider`），**不再**静默取 `identity["provider"]`；`cli.py` 两分支把 `model_provider` 写入 `provider_identity`；`provider_facade.py` 仍显式传 `model_provider`，与 identity 一致。对应测试 `test_codex_adapter.py`、`test_s1_ark_readonly_egress.py`、`test_real_provider_cli.py` 中固化该 bug 的断言已改。违反点消除。

2. **Facade 未推进 identity chain。** `HostCapabilityFacade.acquire_provider` 产出 adapter，但记录的 `events` 仍仅带 `run_id`（无 worker_run/codex_thread）。Facade 已接线，identity 契约未推进。

3. **Shelf 模块被误读为架构。** `dsh_runtime.py`+`worker_bridge.py` 是文档化的 seam，但不在运行路径上——有被误认为在线系统的风险。

**小结：** v1 = 如实的 Codex-only 回退。DSH Harness、Worker bridge 接线、完整 identity chain、plugin-Facade 路由均为 `target`/`unknown`，非 `implemented`。CompositionOwner 是唯一 canonical owner（`implemented`），但仅到 `run_id` 粒度。

---

## 汇总

- **Standards 轴**：4 项发现（1 HARD + 2 judgement + 1 软 smell 之外共 3 类基线 smell）。最严重 = §4 违反：`packages/dsh-zworkbench-bootstrap/src/index.ts:99` 的 `apply()` 注册 DSH Session 却不返回 disposer。
- **Spec 轴**：7 项发现（4 缺失/部分 + 0 矛盾 + 3 看似实现但错误）。最严重 = DSH 主 Harness / 进程外 Worker bridge / 完整 identity chain / plugin-Facade 路由整体仍为 `target/unknown`（v1 仅 Codex-only 回退，目标架构未落地），且 `codex_adapter.py:126` 存在已知 provider identity 静默替换偏差。

> 两轴独立、未合并重排。Standards 最严重项为缺 disposer 的 HARD 违反；Spec 最严重项为"目标混合架构 v1 尚未落地 + 已知 provider identity 替换偏差"，二者性质不同，不跨轴选单一冠军。

---

## 已解决项（2026-10-02，用户要求 ①+②+③ 全部解决）

用户确认后一次性落地三处可行动修复：

- **① TS 插件缺 disposer（§4 HARD）**：`packages/dsh-zworkbench-bootstrap/src/index.ts` 的 `apply(ctx)` 改为返回 disposer；Session 持久化进 DSH_HOME 后由外部 ZWorkbench runtime 持有（residual owner），disposer 不删 durable Session。`tests/bootstrap.spec.ts` 新增回归断言。
- **② 抽取共享子进程监督器**：新建 `src/zworkbench/_digest.py`（canonical_json/sha256_json/file_digest）与 `src/zworkbench/subprocess_supervisor.py`（`terminate_process` fail-closed 拆除 + `LineStreamSupervisor` 行流监督）；`dsh_runtime.py`/`worker_bridge.py`/`codex_adapter.py` 三处内联 killpg 与重复 digest helper 全部收敛到共享模块，移除死属性 `self.selector` 与失效 `import signal`/`import selectors`。
- **③ provider identity 静默替换（#39）**：见上方 (c).1 行内解决说明。

验证：`tests/test_dsh_runtime.py tests/test_worker_bridge.py tests/test_codex_adapter.py` = 19 passed + 9 subtests；扩展后端套件 `test_codex_adapter.py tests/test_s1_ark_readonly_egress.py tests/test_real_provider_cli.py tests/test_provider_facade.py tests/test_local_run.py tests/test_dsh_runtime.py tests/test_worker_bridge.py` = 49 passed + 9 subtests。完整 `tests/` 跑批 921 passed / 1072 subtests passed，17 个 `test_ui_*` 真实引擎渲染快照测试失败为预存/环境性（与本次后端改动无关）。

**未解决 / 仍 open**：DSH 主 Harness、进程外 Worker bridge 接线、完整 identity chain（run_id → worker_run/codex_thread）、plugin-Facade 路由仍为 `target/unknown`；Facade 未推进 identity chain（events 仅带 run_id）；preflight 的 `authorized_provider` 仍按 `profile.name` 绑定（#39 的"若 authorized_provider 设为 custom"场景需在 1-6-3 单独立项，未随本次一并改）。

