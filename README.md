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
该路线图包含历史评测与当前决策记录；目标混合架构尚未完整实现，Codex-only 仍是回退基线。
H1–H5 的受控 owner-backed seam 已有本地验证，其中 H5 仅证明组合式 evidence/replay 边界，
不代表 DSH 原生、真实 Codex replay 或真实远程 Provider compatibility 已通过。
真实 Provider 的账户、凭证、远端数据和退出责任是路线外、按需的人工验证；核心开发不等待它们。
当前 Ark 已有授权只读 HTTP staging 的 5/5 证据，以及一次真实 Codex `0.139.0` + Ark
case-local 只读 staging 通过证据；完整兼容性仍 HOLD。需要验证 HTTP
边界时，只在本机运行
[`scripts/optional-real-provider-staging.sh`](scripts/optional-real-provider-staging.sh)，
先完成 S1–S6 人工门；API Key 通过隐藏输入传给本地 helper，不进入聊天、仓库、日志或 Agent 输出。
需要验证真实 Codex runtime 时，使用独立的
[`scripts/optional-real-codex-provider-staging.sh`](scripts/optional-real-codex-provider-staging.sh)
及其 [runbook](docs/references/optional-real-codex-provider-staging.md)；它只执行一个
case-local、只读、无插件/无工具的 Codex app-server turn。
Codex HOME 仅存在于 evidence 目录外的私有临时目录，结束后清理。
需要验证真实 Ark 的受控 route fallback 时，使用
[`scripts/optional-real-ark-failover.sh`](scripts/optional-real-ark-failover.sh)；它以一个
明确无效 model 作为 primary 负向控制，再以 `ark-code-latest` 完成第二次合成请求，
不代表独立第二 Provider 或自然故障恢复。需要盘点 Provider-side exit 时，使用
[`scripts/optional-provider-exit.sh`](scripts/optional-provider-exit.sh)；它只生成脱敏
receipt，不执行远端删除、停用或注销。
