# ZWorkbench

ZWorkbench 面向个人开发者或小团队，当前主线是受控的本地运行闭环：Codex `0.139.0`、一个 SQLite
composition owner、case-local workspace、loopback/fake Provider，以及可记录、导出、回放和恢复的
`local_read_only_run`。

路线图事实源是 [`docs/plans/personal-workbench-w8-roadmap.json`](docs/plans/personal-workbench-w8-roadmap.json)，
渲染视图是 [`docs/plans/personal-workbench-w8-roadmap.md`](docs/plans/personal-workbench-w8-roadmap.md)。
真实 Provider 的账户、凭证、远端数据和退出责任是路线外、按需的人工验证；核心开发不等待它们。需要
验证时，只在本机运行 [`scripts/optional-real-provider-staging.sh`](scripts/optional-real-provider-staging.sh)，
API Key 通过隐藏输入传给本地 helper，不进入聊天、仓库、日志或 Agent 输出。
