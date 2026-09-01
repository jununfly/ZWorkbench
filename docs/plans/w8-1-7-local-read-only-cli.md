# W8 `1-7`：`local_read_only_run` 产品入口与可安装运行闭环

状态：`in_progress` · 路线类型：`Product execution`

本节点把 `1-5` 已验证的 Python orchestration seam 暴露为一个最小的用户入口。
它不改变 W8 的运行时组合，也不把隔离 fixture 的通过结果升级为真实 Provider、
宿主级隔离或 Codex native approval 证明。

## 1. 交付边界

用户通过安装后的 `zworkbench run` 提交一次本地、只读任务：

```bash
zworkbench run \
  --case-root <existing-case-root> \
  --workspace <case-root/workspace> \
  --prompt "inspect the local fixture and return fixture-ok" \
  --codex <fixed-codex-executable> \
  --export <case-root/export/owner.json> \
  --backup <case-root/backup> \
  --summary <case-root/run-summary.json>
```

默认 Provider identity 是非敏感的 loopback/fake identity：
`fake-loopback`、`fake-model`、`http://127.0.0.1:11434`。调用方可以修改
Provider、model 和 endpoint 字符串，但 preflight 只接受 loopback endpoint；CLI
没有 API key 参数，也不读取全局凭证。

CLI 只负责：

- 参数解析和 case-local 路径边界检查；
- 调用现有 `preflight` 和 `LocalReadOnlyRunOrchestrator`；
- 输出不含 prompt 原文的结构化运行摘要；
- 在 case-local 路径中按需生成 owner export、backup 和 summary。

Codex agent loop、工具执行、运行状态、事件、结果和 replay metadata 仍由现有
adapter 与 SQLite composition owner 负责。

## 2. 安全与停止语义

- `case_root`、workspace、owner DB、`CODEX_HOME`、event log 和 CLI 产物不得越出
  case root；越界在启动前返回 `denied`。
- Provider endpoint 不是 loopback、模式/沙箱/approval policy 不满足、Codex
  executable 不存在或不可执行时，preflight 返回结构化 `deny`，不创建 owner DB，
  不启动 Codex。
- prompt 命中已知 credential-like pattern 时拒绝记录，避免把疑似凭证写入 owner。
- `run` 固定为 `local_read_only`、read-only sandbox、`approval_policy=never`，
  不提供 write、deploy、Git push、scheduler、live replay 或自动 retry 参数。
- `recorded_view` 由 adapter 写入 owner；CLI 只报告其存在，不重新执行 replay。
- adapter 失败时保留 owner 状态并返回 `failed`；不把部分文本或事件升级为成功。

## 3. 用户可见输出

成功的 `run` 返回 `zworkbench-cli/v1` JSON，包含：

- `status`、`run_id`、`mode` 和脱敏 `preflight`；
- execution 的 thread/turn/status/text/provider/event/environment identity；
- owner 是否存在、run status、state digest、recorded-view 标志和 event count；
- 可选 export、backup 和 summary 的路径/摘要。

`snapshot`、`export`、`backup`、`restore` 子命令复用 composition owner 的既有
生命周期接口，主要用于本地检查和恢复；第一切片的产品运行仍只有 `run`。

## 4. 验证

CLI smoke test 使用临时 fake Codex app-server 走真实 adapter JSON-RPC 入口，
不启动真实 Provider，不读取凭证，不产生网络和外部副作用。覆盖：

1. 成功运行、owner identity、recorded view、export、backup 和 summary；
2. 远端 Provider 在 preflight 前拒绝，owner DB 不创建；
3. case-local 产物越界在 preflight 前拒绝，Codex 不启动。

测试命令：

```bash
PYTHONPATH=src python -m unittest tests.test_cli -v
```

安装入口由 `pyproject.toml` 的 `project.scripts` 声明：
`zworkbench = zworkbench.cli:main`。

## 5. 非目标与后续节点

本节点不处理：

- 真实火山方舟请求、真实凭证、Provider 远端 retention/退出；
- 真实本地写操作、宿主强制边界和 Codex native approval（`1-6-3` 继续 HOLD）；
- 自动任务、定时调度、多 Provider fallback、团队协作或第二 Harness；
- DeepSeek adapter 或主 Harness 重新选择。

`1-7` 稳定后，才建立独立的 DeepSeek acceptance/evaluation 节点，使用相同的
入口、owner、policy、evidence contract 和预先声明的 ATAM/CBAM 阈值，以验证
是否存在足以覆盖适配、维护、许可证和退出成本的非重复收益。
