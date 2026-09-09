# ZWorkbench

ZWorkbench 是面向个人开发者或小团队的本地优先工作台。它以 DSH 作为主 Harness、
Codex 作为进程外 Coding Worker，并由 CompositionOwner 维护唯一的 durable state。

可安装入口是受控的本地只读运行：它在 case-local workspace 中启动固定 Codex executable，
使用 loopback/fake Provider，并输出脱敏的 run、event、result、export 与 backup 证据。

```bash
mkdir -p /tmp/zworkbench-case/workspace
zworkbench run \
  --case-root /tmp/zworkbench-case \
  --workspace /tmp/zworkbench-case/workspace \
  --prompt "inspect the local fixture" \
  --codex /opt/homebrew/bin/codex
```

默认边界：未知工具、越界 workspace、未确认 approval、网络/凭证要求和不可关联事件都会
safe-stop。真实 Provider、真实项目写入、Git push、部署和 live replay 不是该入口的隐含能力。

从 [文档地图](docs/README.md) 开始：领域语言解释对象，方法论解释判定，架构解释责任边界，
ADR 解释长期选择；外部 staging 的受控操作边界见 references。
