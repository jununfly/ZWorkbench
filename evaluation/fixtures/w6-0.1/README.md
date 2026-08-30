# W6-0.1 隔离评估 Fixture

这是候选 Harness 首轮比较使用的无真实副作用 fixture。它只允许访问本地临时目录和 loopback 假服务，不使用真实凭证、生产项目、外部消息或不可逆部署。

## 组成

- `code-project/`：带一个明确缺陷、现有测试和项目说明的小型 Python 项目；
- `fake-provider-a.json` / `fake-provider-b.json`：确定性 Provider 契约和故障注入说明；
- `fake-provider.py`：仅监听 loopback 的 OpenAI-compatible 最小假服务；
- `fake-sink.py`：只写调用者指定的临时日志文件；
- `policy/policy.json`：五类危险动作的评估策略；
- `manifests/fixture-manifest.json`：fixture 版本与 hash 入口。

`dummy-remote.git`、假凭证和运行时快照由 runner 在临时目录中生成，不提交到 fixture 源目录。

运行统一 fixture self-test：

```sh
python3 evaluation/runner/run_baseline.py --self-test
```

候选 preflight 只执行 `--version`/`--help`，不启动 Agent、不请求模型、不访问网络；完整 C1–C7 只有在候选有明确的本地 fake Provider 和安全 adapter 后才会被标记为实测。

