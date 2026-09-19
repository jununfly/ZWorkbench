# dsh-web 能力拟合 PoC 设计规格

**状态**：规格已闭合（research 路线产物）。本文件**不写入 ZWorkbench 产品代码**；§4 的六步验证描述的是"待执行的 PoC 实现范围"，需另开 **product-execution scope gate** 落地代码与测试。

**日期**：2026-09-19
**承接**：`2026-09-19-conclusion-report.md`（选项 C + 并行 D）、`2026-09-19-sealed-ledger.json`（证据锚点 `2629c3f` / v0.3.22）
**路线图节点**：1-4（PoC 规划与验证）；本文件闭合 1-4-1 / 1-4-2 / 1-4-3 / 1-4-4。

---

## 0. 关键事实更新（2026-09-19，相对 2026-09-15）

推进本规格时核对了 ZWorkbench 当前源码，发现结论报告的两处陈述已被代码演进超越，在此以事实校正（不影响方向性结论 C + 并行 D）：

1. **Host Capability Facade 已落地。** `src/zworkbench/ui_view_model.py` 的模块 docstring 即声明 *"The control-plane facade: durable owner state to redacted view models"*；`owner_view_source(owner)`（L635-664）已将 owner 适配为 host 期待的 `route -> redacted model` 函数，host 看不到 owner 存在。结论报告 §2 / §7 说的"until the control-plane facade lands"已不成立——这是 PoC 接缝的**现成落点**，不是待建项。
2. **DSH 会话身份引用已被对等投影。** `ui_view_model._project_execution_identity`（L86-155）已把 `dsh_session_id` / `dsh_turn_id` / `worker_run_id` / `codex_thread_id` 等作为执行身份链字段投影到 task-detail 视图。即 ZWorkbench **已经具备 dsh-session-id 包的"展示 session 引用身份"能力**，只是尚未作为独立可定位（带 `data-ui-ref`）的只读 surface 暴露。

⇒ PoC 不需要从零造 facade，也不需要引入 dsh 运行时；只需在现有 `ui_view_model` + `ui_host.ROUTES` 接缝上**新增一个最小只读 surface**，把已投影的 DSH 身份引用以"可声明、可定位、可 review"的形态呈现。这正是选项 C（选择性复用模式，不引入运行时）+ 并行 D（用现有 facade 而非 React/Cordis）的最直接落地。

---

## 1. 目标与 scope gate

### 1.1 research 路线（本文件）
- 产出：PoC 设计规格（surface 选择、宿主接缝改造点、六步验证设计、交付对比）。
- 不修改 ZWorkbench 产品代码，不提交 product 改动。

### 1.2 product-execution 路线（待独立 scope gate，非本文件范围）
- 实现 §3 的 surface + Presenter + 测试；跑 §4 六步验证并留存证据。
- 进入前需再次确认：本次仍属"无副作用只读 surface"增量，不触发 acceptance/evaluation 与 product execution 的范围混淆（按 AGENTS.md Step 1 scope gate 拆分）。

### 1.3 硬约束（引结论报告 §2，全程适用）
`independent-plugin` / `owner-boundary` / `runtime-compatibility` / `local-first-security` / `license-lifecycle` / `experience-version`。PoC 是 experience-version 的最小纵向切片 + 预定义阈值 + 明确止损线。

---

## 2. 1-4-1 选定 surface：`/session-references`

### 2.1 选择依据
dsh-session-id 包的核心价值 = 在一个独立 UI unit 里**只读展示"当前实体持有的 session 引用身份"**（manifest / slot / 语义属性 / disposer / 包级测试）。映射到 ZWorkbench 的对等级单元 = 一个只读展示**"当前 run 持有的 DSH 执行身份引用"**的 surface。

选型优先级（满足 independent-plugin + owner-boundary + 零运行时）：

| 候选 surface | 判定 | 原因 |
|---|---|---|
| 复用 task-detail 内联身份块 | 拒绝（作为独立 surface） | 已存在但不可独立定位；dsh-session-id 模式的价值在于**独立可声明可 review 的 unit** |
| **`/session-references`（新独立只读 surface）** | **选定** | 复用 `_project_execution_identity` 已投影字段；独立 `data-ui-ref`、独立 manifest、独立 renderer、可 disable/remove 不波及三视图 |
| 引入 dsh-session-id 运行时 / React 组件 | 拒绝 | 违反 runtime-compatibility（需 Cordis + DSH client + slot host），触发 §5 止损线 |

### 2.2 surface 语义契约
- **只读**：仅展示已投影身份引用，无任何写操作入口。
- **可定位**：每个身份字段带 `data-ui-ref="session-references.<field>"`，可被 review deep-link 定位（复用 `ui_token` / `ui_runtime.ReviewSession`）。
- **会话身份来源**：复用 `ui_runtime.ReviewSession`（随机 handle、内存态、不源自 run 身份、请求结束即弃）——证明"session-id 同等级"语义由 ZWorkbench facade **原生满足**，无需 `dsh.client` 注入。
- **失败态**：owner 缺字段 → 该字段值 `unknown`（复用 `ui_view_model.UNKNOWN`），surface 不崩、不报 error。

### 2.3 暴露字段（DTO，来自 `_project_execution_identity` 白名单投影）
`dsh_session_id`、`dsh_turn_id`、`worker_run_id`、`codex_thread_id`、`codex_turn_id`、`run_id`、`attempt_id`、`provider`、`model`、`endpoint`、`transport`。
字段以**白名单**方式从 facade 取值（与 `ui_view_model` 一致），任何未命名字段默认 absent，杜绝 owner 新列泄露。

---

## 3. 1-4-2 重写宿主接缝（规格）

> "重写宿主接缝"指**在现有接缝上新增 surface**，不是把 dsh-web 原包塞进 ZWorkbench。

### 3.1 接缝落点（全部已存在，仅扩展）
- 宿主：`src/zworkbench/ui_host.py` 的 `ROUTES` 字典 + `render_document` + `serve_workbench(view_source, bind, review)`。
- Facade：`src/zworkbench/ui_view_model.py` 的 `owner_view_source(owner)` + `_ROUTES` + `_project_execution_identity`（已投影 DSH 身份）。
- 引用/身份：`ui_ref`（声明）、`ui_runtime.ReviewSession`（会话实例身份）、`ui_token`（deep-link）、`ui_build.build_receipt`（build 身份，ADR 0006）。

### 3.2 新增单元（product 路线实现）
| 单元 | 形态 | 职责 |
|---|---|---|
| `session_references_manifest(build)` | 函数 | 产出该 surface 的 manifest（`ui_map` / `build` / `refs` 列表，每字段一个 `ref`） |
| `render_session_references(view, manifest)` | 函数 | server-render 只读 HTML，每字段带 `data-ui-ref` |
| `session_references_view_model(owner, run_id)` | 函数 | 调 `_project_execution_identity` 取身份链，透传 `display_text` 脱敏，缺字段置 `unknown` |
| `ROUTES["/session-references"]` | 注册项 | `(title, session_references_manifest, render_session_references)` |
| `ui_view_model._ROUTES` 增补 | 注册项 | `/session-references`: `lambda owner: session_references_view_model(owner, _latest_run_id(owner))` |

### 3.3 硬禁止项（落地时写入测试断言，fail-closed）
1. **不读 owner 原始存储**：surface 只能通过 `ui_view_model` facade / `owner_view_source` 的投影方法取值；禁止直接 `owner.snapshot()` 之外的字段直读或 SQLite 直连。
2. **不读 DSH session 文件 / 不调用 `dsh.client`**：PoC 不引入任何 dsh-* 依赖。
3. **不写 effect / approval / run**：host 请求不得创建任何 durable 状态（沿用 `ui_host` ADR 0003 不变）。
4. **零网络请求**：surface 纯本地；禁止任何 outbound socket / telemetry / remote API。
5. **不持久化 session 状态**：`ReviewSession` 内存态，响应结束即弃，不落地。

### 3.4 复用而非新建的部分
- 脱敏：`ui_view_model.display_text`（`_SECRET_VALUE` / `_LOCAL_PATH` 正则）直接复用，value-level 二次脱敏。
- 定位/审计：`ui_runtime.audit_rendered_html` 复用验证 manifest↔DOM 一致。
- 构建身份：`ui_build.build_receipt` 复用，保证 served token 与存储 receipt 对齐（ADR 0006）。

---

## 4. 1-4-3 六步验证 + 止损线

> 以下每步对应一个具体测试文件/断言，作为 product 路线的验收契约；本规格不实现，仅规定。

1. **固定源码锚点**：新建 `docs/plans/research/dsh-web-capability-fit/poc-source-pin.json` 记录 dsh-web `@2629c3f` + 选中 surface 的 source path；PoC 实现须以 `build_receipt` 产出 build 身份并写入 manifest，断言 `ui_map`/`build` 与 `poc-source-pin` 一致。
2. **Facade 脱敏 DTO**：`tests/test_poc_session_references_facade.py` — 用 mock owner 注入，断言 `session_references_view_model` 仅调用 facade 投影方法、**不**触达 owner 原始表；断言缺字段返回 `unknown` 而非异常。
3. **零网络请求**：`tests/test_poc_session_references_zero_network.py` — 用 socket 计数 / 本地代理断言 surface 渲染与 host 生命周期内 outbound 连接数 = 0（尤其确认未引入 dsh telemetry）。
4. **enable/disable/dispose 归零**：`tests/test_poc_session_references_dispose.py` — 启 host → 渲染 → `WorkbenchHost.close()` + `ReviewSession.close()` 后，断言 DOM 无残留引用节点、无存活 timer/listener、无 PendingNetwork（复用 `test_ui_review_lifecycle` 的可复现请求检测法）。
5. **失败返回 unknown/HOLD**：`tests/test_poc_session_references_failure.py` — facade 抛错 / owner 缺 run 时，view model 整体仍可渲染，host 返回 200，状态字段为 `unknown`，不影响现有三视图 SSR host。
6. **交付对比**：见 §5，产出对比文档。

### 4.1 止损线（任一触发即升级为 D 或停止，不再称"薄 adapter"）
- 需要引入 DSH Web client runtime / 动态 loader / profile patch / 远端 API。
- adapter 开始拥有业务状态（store / scheduler / execution）。
- 出现第二 durable owner 倾向（任何跨 Run canonical state 落点偏移）。
- 网络请求数 > 0 且无法归因到本地 host 自身。

---

## 5. 1-4-4 交付对比（自建 vs 吸纳）

> 估算基于现有代码事实，非实测；实测待 product 路线落 §4.6。

| 维度 | 路径 C + 并行 D（自建，本 PoC） | 路径 B1（薄 adapter 接入 dsh-session-id 运行时） |
|---|---|---|
| 新增产品代码 | ~1 view + ~1 Presenter + manifest/renderer 注册；预估 < 200 行 | 需引入 Cordis client SDK + DSH plugin loader + slot/settings host + dsh.client 注入；预估 > 2000 行 |
| 新增依赖 | 0（纯复用现有 `ui_view_model`/`ui_runtime`/`ui_token`） | dsh-web 聚合依赖树（含其 telemetry/remote 组件，需逐一 NOTICE 闭合 + 隔离） |
| 测试量 | 5 个聚焦测试文件（§4.1–4.5），复用既有 review/overlay/audit 框架 | 需对 DSH profile 联调 + dispose 资源归零 + 网络隔离做完整验证（§6.2–6.4 unknown 全转 known） |
| 生命周期责任 | 独立 route，可 disable/remove 不波及三视图；disposer = host close | 依赖 DSH profile 的 enable/disable/dispose 链，ZWorkbench 当前无该 profile |
| 许可证风险 | 仅复用本项目 Apache-2.0 自有代码 | 需对实际选用 dsh-* 依赖闭合 NOTICE/license、pin 版本、验证回滚 |
| 预估交付时间 | 1 个纵向切片（单 dev，含测试） | 需先建缺失的 DSH Web profile/loader 基础设施，量级不可比 |

**结论**：在 ZWorkbench 当前仅 H1 artifact bootstrap、无完整 DSH Web profile 的前提下，路径 C + 并行 D 的交付成本显著低于 B1，且已具备 dsh-session-id 同等级能力（§0.2）。B1 维持 future unknown，待 ZWorkbench 出现稳定 DSH Web profile/client loader 后再重评。

---

## 6. 证据锚点与 unknown（诚实声明）

- **已闭合证据**：dsh-web `@2629c3f` / v0.3.22（sealed-ledger EV-002/003）；ZWorkbench facade 已落地 + DSH 身份已投影（本规格 §0，源码实证）。
- **本规格未覆盖的 unknown（留待 product 路线，不静默闭合）**：
  1. PoC 实现的六步验证尚未实际跑（§4 为设计，非结果）。
  2. §5 交付对比为估算，非实测；实测待 §4.6。
  3. ZWorkbench-specific DSH profile 联调（结论报告 §6.2）仍 `unknown`——本 PoC 不依赖它，但若未来走 B1 则必须先闭合。
  4. 本地未在 clean dependency install 下跑 dsh-web package build/test（结论报告 §6.3）——本 PoC 不引入 dsh 依赖，故不适用。
  5. dispose 资源归零仅在 ZWorkbench 自有 review 框架验证（复用 `test_ui_review_lifecycle`），未验证 DSH Cordis dispose（结论报告 §6.4）——与 B1 无关。

---

*本规格比 `2026-09-19-conclusion-report.md` 更进一步，把选项 C + 并行 D 收敛为可执行的 surface 设计与验收契约；并纠正了结论报告两处已过时陈述（facade 已落地、DSH 身份已投影）。原始结论报告与 sealed-ledger 保留为证据底稿。*
