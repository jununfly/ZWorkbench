# W8 受控个人试点：产品边界与最小纵向切片

状态：`design-baseline` · 路线类型：`Product execution` · 本轮不实现代码

本文件将 W7 的候选评估结论转换成 ZWorkbench 的第一阶段产品边界。它不是
Codex 的生产采用批准，也不是把 W7 fixture 的通过结果升级成产品能力证明。

## 1. 试点目标

ZWorkbench 第一阶段服务于一个个人开发者，或一个很小的内部团队，解决一件
可复核的事情：输入一个本地项目任务，安全地启动一次固定版本 Codex 运行，
留下可关联、可查看、可导出的结果和事件证据，并能从本地 composition state
备份中恢复。

第一阶段的产品基线固定为：

- 一个主 Harness：Codex `0.139.0`；
- 一个本地 SQLite composition owner；
- 一个本地、case-local 的运行目录和 `CODEX_HOME`；
- loopback/fake Provider；
- read-only workspace；
- 单一操作者、手动触发、可恢复和可删除。

“受控”意味着任何不能确认边界的动作都停止，而不是继续执行后再依赖日志
追责。第一阶段不是 SaaS、多租户平台或团队协作产品。

## 2. 产品边界和责任地图

| 边界对象 | W8 中负责什么 | 明确不负责什么 |
|---|---|---|
| ZWorkbench control plane | 接收任务、生成 `run_id`、执行 preflight、绑定 workspace/config/provider identity、展示状态、导出和停止 | 不复制 Codex agent loop，不把文本结果当作唯一事实 |
| SQLite composition owner | 唯一持有 run、approval、effect、result、event、replay metadata、backup identity 和 state digest | 不执行 shell、模型请求或外部副作用；不接受第二个 truth owner |
| Codex app-server adapter | 以显式 argv/env 启动固定 Codex，关联 `thread_id`、`turn_id`、事件和结果 | 不绕过 owner，不把 Codex 内部数据库提升为 ZWorkbench composition truth |
| Provider | 负责推理服务、服务端数据处理、任务/Webhook/备份/retention 和账户责任 | ZWorkbench 不创建、管理或承诺清理 Provider 侧资源 |
| Host / project workspace | 提供本地文件、进程、凭证注入和 OS 隔离边界 | W8 不宣称已经获得宿主级强制隔离；未签核路径必须 safe-stop |

当前火山方舟信息只用于说明真实 Provider 的数据边界：endpoint、API key、
账户和远端资源不会写入 owner ledger。第一切片不访问该真实 endpoint；未来
接入时必须按 Provider 单独确认数据、retention、账单和退出责任。

## 3. 第一阶段允许和禁止的事情

### 允许

- 手动提交一个本地项目的只读分析/代码理解任务；
- 在 case-local 目录中启动固定 Codex app-server；
- 使用 loopback/fake Provider 完成一次确定性运行；
- 保存完整的 run/thread/turn/provider/environment/event/result 关联；
- 查看 `recorded_view`，导出脱敏的 owner state，创建并恢复本地 backup；
- 运行失败时保留证据并进入 `failed` 或 `safe_stopped`。

### 禁止或延后

- 真实火山方舟请求、生产凭证、生产项目和真实远端数据；
- 写文件、Git push、部署、发送消息、创建任务或其他不可逆副作用；
- `live_replay`；未有显式授权时只允许 recorded view 或 simulated replay；
- 常驻 scheduler/cron、自动 retry、Provider gateway 或第二 Harness；
- 多租户、账户共享、对外 SaaS、团队权限模型和远端资源管理；
- 以 C2 scripted pass 代替宿主级强制边界或 Codex native approval 签核；
- 为了解决未验证的需求引入 Temporal、LangGraph、LiteLLM、独立观测平台。

自动任务、多 Provider 和真实写操作仍是产品目标，但不是第一切片的放行条件。
它们必须在单独节点中添加状态、权限、迁移、备份和退出成本，而不是隐式塞入
第一条路径。

## 4. 最小纵向切片：`local_read_only_run`

### 用户可见流程

```text
本地任务输入
    ↓
policy preflight
    ↓
创建并启动 owner run
    ↓
固定 Codex app-server / thread / turn
    ↓
事件、Provider、环境和结果写入 owner
    ↓
完成 run
    ↓
recorded view + snapshot/export + backup
```

建议的产品入口契约（命令名和参数可在实现节点细化）是：

```text
zworkbench run
  --mode local-read-only
  --workspace <case-local-workspace>
  --prompt <task>
  --codex <fixed-executable>
  --db <case-local-composition.sqlite3>
```

这只是第一条垂直切片的接口草案，不代表现在已经存在该 CLI。

### `1-5-1` 已落地的准入接口

当前已实现并从 `zworkbench` 顶层导出的接口为：

```python
config = LocalReadOnlyRunConfig(
    case_root=..., workspace=..., database=..., code_home=...,
    codex_executable=..., event_log=...,
    provider_identity={"provider": ..., "model": ..., "endpoint": ...},
)
result = preflight(config)
```

`PreflightResult` 只包含 `status`、`mode`、`config_digest`、布尔 `checks`、
`allowed` 和结构化 `violations`，可通过 `to_dict()` JSON 序列化。它不会返回
配置原文或凭证值。当前稳定的拒绝代码包括：
`mode_not_local_read_only`、`sandbox_not_read_only`、`workspace_outside_case_root`、
`state_outside_case_root`、`code_home_outside_case_root`、`event_log_outside_case_root`、
`provider_not_loopback`、`provider_endpoint_invalid`、`provider_endpoint_scheme_not_supported`、
`provider_credentials_present`、`provider_identity_not_json_serializable` 和
`required_features_not_disabled`。

该接口只做静态本地检查：不会创建 `state`、`CODEX_HOME` 或 event-log 目录，
不会启动 Codex，也不会发起网络请求。它证明的是第一切片的配置合同，不是
宿主级隔离或 Codex native approval 已签核。

### `1-5-2` 已落地的编排 seam

`LocalReadOnlyRunOrchestrator(config).run(run_id, prompt)` 已成为第一切片的
唯一编排入口：

1. 先调用 `preflight`；拒绝时返回 `LocalReadOnlyRunResult(status="denied")`，
   不打开 SQLite、不创建运行目录、不调用 adapter factory；
2. 通过后打开一个 `CompositionOwner`，用默认 factory 构造真实
   `CodexAppServerAdapter`，并把 `run_mode` 与脱敏 `preflight` 结果写入
   `adapter.execute` 的 metadata；
3. 从同一个 owner 读取 `state_digest`，返回 `completed`、`CodexExecution`、
   preflight 和 digest，并在所有路径关闭 adapter；
4. adapter 抛出异常时不吞掉原异常、不伪造成功，保留 owner 现场供后续失败/诊断
   节点处理。

adapter factory 是测试和未来替换的内部 seam，不是第二 Harness；当前默认实现仍
只有 Codex adapter。该编排层不执行 shell、工具 effect、scheduler、retry、live
replay 或 Provider 请求。

### 每一步的完成条件

1. **输入与 preflight**：校验 workspace 是允许的本地目录，数据库和 `CODEX_HOME`
   是 case-local 路径，Provider identity 是显式且非空的 loopback/fake identity；
   key 值不进入输入、owner state 或 event log。
2. **创建运行**：owner 创建唯一 `run_id`，写入任务类型、规范化输入摘要、
   config/fixture identity 和开始事件。
3. **启动执行**：adapter 以无 shell 的显式 argv/env 启动 Codex app-server，
   使用固定版本、read-only workspace 和 loopback Provider；不继承未声明的
   生产凭证或全局状态。
4. **关联身份**：成功的 `thread/start`、`turn/start`、事件流和 Provider identity
   必须与同一个 `run_id` 关联；缺少任一关键 identity 时停止并留下故障事件。
5. **完成结果**：只在 owner 能确认没有未决 effect、事件和结果字段完整时写入
   semantic result 并完成 run；模型返回文本本身不能绕过 owner 的完成条件。
6. **查看和退出**：默认提供 recorded view、snapshot、脱敏 export、backup；
   backup/restore 后 state digest 必须一致。退出动作只清理本地 case-local 资产，
   不声称清理 Provider 侧资源。

## 5. 不变量和 fail-closed 规则

- owner 是唯一 durable source of truth；Codex 内部状态是 adapter evidence；
- `run_id → thread_id → turn_id → event/result` 关系必须可查询；
- 未知工具类别、未知副作用、approval 不可见、凭证/网络/路径边界不满足时，
  结果必须是 deny/safe-stop；
- 第一切片不存在可执行 effect；未来出现 effect 时，必须先 claim，再执行，再
  记录 complete 或 uncertain，不能由成功文本代替；
- `live_replay` 默认拒绝，任何 replay 都必须带显式 mode、环境 identity 和
  Provider/tool identity；
- 不能安全判断外部动作是否发生时，保留 `unknown` 并停止，不自动重试；
- 日志、snapshot、export 和 replay metadata 必须脱敏，不能保存 API key 原文；
- 任一 identity 漂移、schema 不匹配或状态无法恢复，都停止新的触发。

## 6. 第一切片验收门

实现节点完成时，需要在隔离 fixture 中提供可复核证据。下面是硬门，不做平均分：

| 门 | 通过条件 |
|---|---|
| 运行闭环 | 至少一条 `local_read_only_run` 从输入到 completed，且 owner state 可重新打开 |
| 身份关联 | `run_id`、`thread_id`、`turn_id`、Provider identity、环境 identity、event digest 和 result 均可关联 |
| 安全边界 | 外部网络为 0、真实凭证为 0、写/部署/Git/远端副作用为 0；未知请求全部 deny/safe-stop |
| 事实完整性 | recorded view、snapshot、export 可读取；backup/restore 后 state digest 一致 |
| 脱敏 | 对输入、事件、结果和导出做 secret-pattern 检查，API key 原文出现次数为 0 |
| 回放边界 | 第一阶段只允许 recorded view；任何 live replay 尝试默认拒绝并留下证据 |
| 可退出 | 删除 case-local 目录后无产品自有常驻服务或未声明本地状态残留 |

任何一门为 `unknown` 都不能称为第一切片通过；应输出 `unknown/stop`，保留
run 和故障证据。通过这些门只表示 W8 第一切片在隔离环境成立，不表示 C7、
Codex native approval、真实 Provider 或商业/许可证审查已经签核。

## 7. 实施顺序（下一节点）

下一执行节点是 `1-5 实现并验证 local_read_only_run`，按以下顺序落地：

1. 定义入口配置和 preflight 结果结构；
2. 复用现有 composition owner 与 Codex adapter，补齐第一切片 orchestration seam；
3. 增加一条完整成功 fixture 和未知请求/边界失败 fixture；
4. 增加身份关联、脱敏、网络零访问、backup/restore 和默认拒绝测试；
5. 生成 run summary、操作说明和可复核证据，再决定是否开放下一节点。

实现期间继续遵守：不接真实火山方舟、不读取全局 `CODEX_HOME`、不使用真实
API key、不执行真实写操作、不引入第二 Harness 或常驻服务。

## 8. 后续放行门

只有第一切片稳定后，才分别评估：

- `1-6`：真实 Provider 接入的数据/retention/退出责任；
- 自动触发与 retry 的 C3/C4 产品化，而不是直接启用 cron；
- 可恢复的本地写操作及 C2 宿主级边界；
- 多 Provider capability/fallback，而不是默认添加 gateway；
- simulated/live replay 的显式授权流程；
- 从个人试点进入日常使用、团队共享或分发前的 C7/法律/商业签核。

每个后续放行都必须证明新增收益大于新增的状态、运维、备份、排障、许可证和
退出成本；否则维持当前最小组合。
