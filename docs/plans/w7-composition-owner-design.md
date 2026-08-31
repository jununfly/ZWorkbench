# ZWorkbench composition owner 第一切片

状态：`1-8-1`–`1-8-4` 已完成 · `1-8-5` 待接入 · 产品实现路线

## 目标

建立一个真实的、可重新打开的 composition state owner，关闭此前 C7 中
“真实 composition state 不存在”的阻断。它不是 evaluation fixture，也不是
Codex `CODEX_HOME`、thread/turn 文件的别名。

第一版是单进程本地模块，使用一个 SQLite 文件作为唯一 durable source of truth。
它不执行模型、shell 或外部副作用；Codex app-server 接入会通过后续 adapter
接入，不能绕过 owner 的 claim/reconcile 语义。

## 外部接口与不变量

`zworkbench.composition.CompositionOwner` 提供少量但有深度的接口：

- run：`create_run`、`start_run`、`complete_run`、`fail_run`、`safe_stop_run`；
- approval/effect：`request_approval`、`approve`、`deny_approval`、`claim_effect`、
  `complete_effect`；
- 中断恢复：`mark_effect_uncertain`、`reconcile_effect`；
- 证据和可迁移性：`record_replay_metadata`、`events`、`snapshot`、`state_digest`、`export_state`、
  `backup`、`restore`。

必须保持的语义：

1. `read-only` / `idempotent` 是无审批 token 可 claim 的已知 class；未知 class
   直接 deny 并 safe-stop。
2. `approval-required` 必须有精确匹配 operation、action、resource、
   idempotency key 的一次性 token；token 只存 hash。
3. 同一 operation/idempotency key 的已完成 effect 永远返回
   `already_completed`，不产生第二次物理副作用。
4. 外部结果不确定时只能 `reconcile`；`not-applied` 最多允许 owner 预算内的
   一次 retry，`applied` 记为已完成，`unknown` 只能 safe-stop。
5. replay mode 必须显式记录为 `recorded_view`、`simulated_replay` 或 `live_replay`；
   owner 只记录 metadata，不执行 replay。
6. `complete_run` 会拒绝任何未决 effect；因此状态丢失不会静默变成成功。
7. backup 同时保存自校验的 SQLite copy、JSON state view 和 manifest；restore
   默认拒绝覆盖已有目标，必须显式 `replace=True`。

## 运行方式

不需要额外常驻服务。开发期可直接使用标准库测试：

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

查看或导出真实 owner state：

```bash
PYTHONPATH=src python -m zworkbench.composition_cli --db .zworkbench/composition.sqlite3 snapshot
PYTHONPATH=src python -m zworkbench.composition_cli --db .zworkbench/composition.sqlite3 backup .zworkbench/backups/run-1
```

## 明确不在本切片内

- Codex app-server JSON-RPC adapter；
- scheduler/cron、Provider router、模型 fallback；
- 生产凭证、生产项目和 live replay；
- 远端备份、加密密钥托管、跨版本迁移和法律/NOTICE 签核；
- 多进程高可用或常驻数据库服务。

后续接入 Codex 时，必须将 `thread_id`、`turn_id`、Provider identity 和 canonical
event metadata 作为 owner 的 adapter result/event 写入，而不是把 Codex 内部状态
提升为 composition truth。

当前状态的重要边界：owner 模块已经真实存在并能创建、重开、备份和恢复 SQLite
state，但在 Codex app-server adapter 接入前，还没有“由真实工作台任务流产生的
composition state”。因此 C7 Gate C 仍不能签核；`1-8-5` 完成一次受控真实
Codex→owner flow 后，才重新执行 C7 backup/restore 和退出审计。
