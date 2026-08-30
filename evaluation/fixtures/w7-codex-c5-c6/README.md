# W7 Codex C5/C6 隔离 composition fixture

这是 `acceptance/evaluation` 资产，不是 ZWorkbench 产品代码。它固定 Codex
CLI/app-server `0.139.0`，只在 case-local workspace 和 `CODEX_HOME` 中运行；
Provider backend 和 router 均为 loopback fake service，不接触真实 Provider、
凭证、外网或外部副作用。

`provider-router.py` 是 C5 的唯一 Provider composition owner。Codex 只访问
`localhost:11434/v1/responses`；router 显式记录 provider capability、attempt、
timeout/半截流、fallback/degradation、最终 Provider 和语义结果。它不复制
Codex agent loop、权限模型或观测后端。

C6 从真实 Codex app-server JSON-RPC event stream 生成版本化 canonical event
ledger、environment manifest 和 replay cassette，然后分别运行：

- `recorded_view`：只读 event ledger，不重新执行；
- `simulated_replay`：只读取 cassette 和 expected output，不启动 Provider/tool/network；
- `live_replay`：无显式批准时 default deny，不启动 Provider/tool/network。

运行：

```sh
python3 evaluation/runner/run_codex_c5_c6.py --smoke
python3 evaluation/runner/run_codex_c5_c6.py --c5
python3 evaluation/runner/run_codex_c5_c6.py --c6
```

C5 使用正常 A/B、B timeout、B stream interruption 和 structured-output 缺失；
C6 使用 5 次真实 Codex event capture 加上三种 replay mode 各 5 次。任何
provider/model/endpoint、event、mode label、cassette/environment identity、
执行计数或副作用证据缺失都保持 `unknown/stop`。
