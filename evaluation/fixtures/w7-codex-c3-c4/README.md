# W7 Codex C3/C4 隔离 composition fixture

这是 acceptance/evaluation 资产，不是 ZWorkbench 产品代码。它只在每个
case-local 临时目录中启动 loopback fake Responses Provider、固定版本 Codex
app-server 和一个受限的本地 effect sink；不使用真实 Provider、真实项目、真实
凭证或外部副作用。

`effect-sink.py` 是 case workspace 中唯一允许的副作用边界。它在文件锁下按
`operation_id` 去重，并分别记录 effect ledger 和 tool-result ledger。外部
adapter 持有 schedule、attempt、状态和最终结果 ledger，并把
`schedule_id`、`idempotency_key`、`run_id`、`thread_id`、`turn_id` 贯穿所有
关键事件。

`fake-provider.py` 只返回固定的 `exec_command` 调用和 `fixture-ok`，并按 case
注入模型响应延迟。Codex 仍通过真实 `initialize`、`thread/start`、`turn/start`、
`thread/resume` 和 `turn/interrupt` JSON-RPC 入口运行；adapter 不复制 Agent
loop、权限模型或观测后端。

运行：

```sh
python3 evaluation/runner/run_codex_c3_c4.py --smoke
python3 evaluation/runner/run_codex_c3_c4.py --c3
python3 evaluation/runner/run_codex_c3_c4.py --c4
```

默认 C3 为五类触发语义各 3 次；C4 为 4 个真实中断/超时/进程故障点 × 3
类工具 × 3 次。每次运行写入 `evaluation/runs/w7-codex-c3-c4-*`。任何
JSON-RPC、关联字段、状态、effect 或结果证据缺失都会保持 `unknown/stop`，
不会被折算为通过。C4 的 `approval-required` 类别还要求固定 Codex 版本实际
发出 `item/commandExecution/requestApproval`；如果 `workspace-write` 下的
case-local 命令没有触发该原生请求，恢复控制仍单独记账，但该样本标记为
`unknown` 并记录 `codex.approval.request.missing`，不能解释为 Codex 原生审批
通过。若以后接入 W6 C2 外部 fail-closed adapter，须另建 composition-owned
审批 fixture，不得回填此处的原生审批证据。
