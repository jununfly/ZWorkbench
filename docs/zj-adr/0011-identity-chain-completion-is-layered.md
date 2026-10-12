---
status: accepted
doc-kind: adr
authority: primary
authority-id: adr.identity-chain.completion-layered
---

# ADR 0011：IdentityChain 的完成性是分层的，Codex 身份只在声明为 Codex Worker 时必填

> 状态 `proposed`：本 ADR 尚未经 Human 确认。确认前不得据此修改产品代码。

## Context

`IdentityChain` 当前把 10 个字段当作同一层，`is_complete()` 要求全部非 `UNKNOWN`
（`worker_contract.py:192`）。其中 `codex_thread_id` / `codex_turn_id` 属于 **Worker
自身**的内部身份，ZWorkbench 无法凭空得知——只有真实 Codex Worker 才会提供。

后果是一个自我强化的错误：bridge 用 `is_complete()` 校验响应，而 fake fixture 并不
拥有 Codex 身份，于是 `evaluation/fixtures/w8_worker_handshake/v1/worker_fixture.py:45-46`
硬编码 `codex_thread_id="codex-thread-1"` / `codex_turn_id="codex-turn-1"` 去"凑齐"
校验；测试反过来断言这两个伪造值（`tests/test_worker_bridge.py:101-102`、
`tests/test_worker_coding.py:126-127`）。即：**校验口径逼着证据链伪造身份**，而
ZWorkbench 的 UNKNOWN 纪律要求"不可知就声明未知，不得编造"。

同时，`codex_adapter` 的真实 Codex 读路径并不经过 bridge handshake（v1 是 Codex-only
回退基线，ADR 0009），所以"何时真的拿得到 Codex 身份"必须由**声明**给出，不能由代码推断。

## Decision

1. **字段分两层。**
   - **Required（恒必填，ZWorkbench 自有）**：`parent_run_id`、`child_run_id`、
     `attempt_id`、`dsh_session_id`、`dsh_turn_id`、`worker_run_id`、`event_id`、
     `artifact_id`。
   - **Conditional（条件必填，Worker 自有）**：`codex_thread_id`、`codex_turn_id`。
     仅当该 Worker 被**声明**为 Codex Worker 时必填；否则其合法值就是显式 `UNKNOWN`。

2. **"是否 Codex Worker"由声明决定，不由推断决定。** 判定依据是请求里已随行的
   `worker_schema_identity.name` 是否命中契约白名单常量（如 `codex-app-server`）。
   pinned fixture 不在白名单内 → 其 Codex 身份必须显式 `UNKNOWN`。
   该判定与 1-7-1 的 `real_worker_mode` **正交**：`real_worker_mode` 说的是"是否是真实
   子进程"，本判定说的是"Worker 是哪一种"；真实但非 Codex 的 Worker 同样应回 `UNKNOWN`。

3. **完成性 API 显式分层。** 新增 `is_complete_for(requires_codex_identity)` 与
   `missing_required_fields()` / `missing_conditional_fields()`；`is_complete()` 保留为
   "全字段齐"的严格语义（上层可选，默认路径不再用它）。bridge 的 handshake / coding
   校验改走 `is_complete_for`，并把结果分类写入 handshake result 的
   `identity_completion` 字段：`complete` 或 `complete_with_declared_unknown`。

4. **禁止伪造，且要被机器拦住。** 声明为非 Codex Worker（fixture）时，响应若携带非
   `UNKNOWN` 的 `codex_thread_id` / `codex_turn_id`，bridge 一律 fail-closed 拒绝，
   错误码 `codex_identity_fabricated`。Fixture 必须回 `UNKNOWN`，不得再补值。

5. **`UNKNOWN` 仍是缺失语义。** 空串、空白串、字段缺失继续按"缺失"处理
   （`worker_contract.py:67` 既有口径）；Conditional 层显式 `UNKNOWN` 属**合法完成**，
   但必须在 owner 侧标为 `complete_with_declared_unknown`，不得冒充 `complete`。

## Consequences

- Fake fixture 停止伪造 Codex 身份：改为回 `UNKNOWN`；相关测试断言随之从"等于
  codex-thread-1"改为"等于 UNKNOWN 且完成性分类为 `complete_with_declared_unknown`"。
- 新增错误码 `codex_identity_fabricated`；原 `handshake_identity_incomplete` /
  `coding_identity_incomplete` 语义收窄为 **Required 层缺失**（Conditional 层缺失在
  声明为 Codex 时才算 incomplete）。
- `ui_view_model.py` 等展示层若透出 Codex 字段，需能显示 `UNKNOWN`，不得因伪造值消失
  而报错或填空。
- 实现范围（待本 ADR accepted 后执行）：`worker_contract.py`（分层 API + 白名单常量）、
  `worker_bridge.py`（校验点 + 结果分类字段）、两个 fixture、上述测试。
- 未解决（不在本 ADR 范围）：真实 Codex app-server 接入后如何取得 thread/turn id
  （属 1-8/真实 Worker 前置）；心跳（已切出为 1-7-5）。
