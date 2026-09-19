# `@deepseek-ai/dsh-zworkbench-bootstrap`

[English](README.md) | 中文

ZWorkbench bootstrap 组合包。[`cordis.patch.yml`](cordis.patch.yml) 在 [`dsh-base`](../base/README.md) 之上挂载一条进程级插件。该插件创建一个空的 DSH Session，在 `zworkbench.dsh.bootstrap/v1` 下以 JSONL 记录发出 `bootstrap.started` 与 `bootstrap.ready`，并在完整 Loader 配置树结算后请求启动器执行有界退出。`ZWORKBENCH_RUN_ID` 与 `ZWORKBENCH_DSH_PROFILE` 是由启动器负责提供的身份输入；缺失或空值会在输出部分握手前失败。该组合包不创建 Agent、不发送 Provider 请求，也不输出任务文本，因此它是独立的外部运行时握手，不是 [`dsh-headless`](../headless/README.md) 的变体。

随附的 `zworkbench-bootstrap` profile 位于 [`apps/cli`](../../../apps/cli/README.md)，由 `dsh-base` 与本组合包组成。该 profile 供 ZWorkbench artifact adapter 使用；adapter 负责校验生成的 JSONL 并拥有 parent Run。DSH Session 仍由 DSH 负责；该组合包不写入 ZWorkbench 状态，也不解释 owner 数据库。

## 模型体验

无，因为这条进程级握手不会创建模型请求或模型可见内容。

#### KV Cache 影响

无直接影响；该组合包不会组装模型请求。

## 已知限制与暂缓事项

- **该握手不是 Worker 协议**——Worker 版本、能力、进程树与 Codex identity 交换属于后续 ZWorkbench H2 bridge。
- **该 profile 不是任务运行器**——需要 Agent 与最终任务文本的调用方必须使用 `dsh-headless` 或其他明确组合的 profile。
- **该 Session 为空**——这个 H1 Session 证明 DSH ownership 与 identity correlation，但不代表 coding task 已完成。
