# ZWorkbench

ZWorkbench 的目标架构是 **DSH 主 Harness + Codex Coding Worker + ZWorkbench CompositionOwner**；
方案准备阶段已经收口，统一入口见 [`docs/README.md`](docs/README.md) 和
[`docs/plans/development-baseline.md`](docs/plans/development-baseline.md)。当前仓库实际主线仍是受控的
Codex-only 本地运行闭环：Codex `0.139.0`、一个 SQLite
composition owner、case-local workspace、loopback/fake Provider，以及可记录、导出、回放和恢复的
`local_read_only_run`。

安装后可通过 `zworkbench run` 执行第一阶段的只读任务。命令要求显式提供 case-local 根目录、
workspace 和固定 Codex executable；默认只接受 loopback/fake Provider：

```bash
mkdir -p /tmp/zworkbench-case/workspace
zworkbench run \
  --case-root /tmp/zworkbench-case \
  --workspace /tmp/zworkbench-case/workspace \
  --prompt "inspect the local fixture" \
  --codex /opt/homebrew/bin/codex
```

CLI 会输出脱敏 JSON，并可用 `--export`、`--backup`、`--summary` 生成 case-local 证据产物。
真实 Provider、写操作、调度和 live replay 不在第一切片中；详见
[`docs/plans/w8-1-7-local-read-only-cli.md`](docs/plans/w8-1-7-local-read-only-cli.md)。

路线图事实源是 [`docs/plans/personal-workbench-w8-roadmap.json`](docs/plans/personal-workbench-w8-roadmap.json)，
渲染视图是 [`docs/plans/personal-workbench-w8-roadmap.md`](docs/plans/personal-workbench-w8-roadmap.md)。
该路线图包含历史评测与当前决策记录；目标混合架构尚未实现，Codex-only 仍是回退基线。
真实 Provider 的账户、凭证、远端数据和退出责任是路线外、按需的人工验证；核心开发不等待它们。需要
验证时，只在本机运行 [`scripts/optional-real-provider-staging.sh`](scripts/optional-real-provider-staging.sh)，
API Key 通过隐藏输入传给本地 helper，不进入聊天、仓库、日志或 Agent 输出。
