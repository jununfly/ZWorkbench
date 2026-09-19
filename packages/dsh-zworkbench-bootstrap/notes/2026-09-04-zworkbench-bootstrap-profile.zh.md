# Agent Note: ZWorkbench bootstrap profile

Status: implemented

[English](2026-09-04-zworkbench-bootstrap-profile.md) | 中文

## Problem

ZWorkbench 以外部 artifact 启动 DSH，并在引入 Worker 能力前需要一条小型、版本化的进程握手。普通 `dsh-headless` profile 会创建 Agent 并输出任务文本，因此不能将其 stdout 当作全 JSONL bootstrap 流消费。如果把握手记录加入该 profile，就会把 bridge 协议与面向用户的任务表层混在一起。

## Decision

ZDSHarness 以独立的 profile 组合包形式交付 `@deepseek-ai/dsh-zworkbench-bootstrap`，并暴露 `zworkbench-bootstrap` profile 模板。其插件创建一个空的 DSH Session，在 `zworkbench.dsh.bootstrap/v1` 下严格输出 `bootstrap.started` 与 `bootstrap.ready`，等待 Loader 结算并完成 Session flush 后再请求启动器执行有界退出。parent Run 与 profile identity 来自由启动器负责的 `ZWORKBENCH_RUN_ID` 与 `ZWORKBENCH_DSH_PROFILE` 变量。该插件不创建 Agent、不调用 Provider、不输出任务文本，也不写入 ZWorkbench 状态。

## Consequences

外部 adapter 可以消费严格的 JSONL 流，并把一个由 DSH 负责的真实 Session 与 parent Run 关联起来，不必解析任务输出或读取 DSH 存储。普通 headless 行为保持不变。该 profile 会向安装依赖闭包增加一个随发行版交付的组合包，并把 Worker handshake、coding 与 Provider 行为留给后续 bridge。

## Alternatives considered

**向 `dsh-headless` 添加记录。** 否决，因为该 profile 的最终 assistant 输出是普通文本，会违反 bootstrap 流必须全为 JSONL 的约定。

**让 ZWorkbench 包装或检查 DSH Session 文件。** 否决，因为这会让外部 owner 依赖 DSH 存储格式，也不能证明子进程在进程边界输出了 identity。

**为 bootstrap 创建第二个 Agent loop。** 否决，因为 H1 只需要由 DSH 负责的 Session identity 与 profile 结算；在 Worker seam 出现前增加另一套 loop 会复制 durable 行为。

## Testing

组合包单测覆盖精确消息顺序、共享 Session identity、启动器 identity、退出前 flush 与缺少 identity 的拒绝。构建后的 CLI e2e 覆盖随附 profile 只输出两条协议记录并成功退出。
