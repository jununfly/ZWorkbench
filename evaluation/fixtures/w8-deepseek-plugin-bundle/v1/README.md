# W8 DeepSeek plugin-composed bundle fixture

这是 acceptance/evaluation fixture，不是 ZWorkbench 产品运行时。它固定
DeepSeek Harness Alpha.4 与四个生态插件的 source commit、package version、
本地 package artifact 和 `dsh` contract，验证插件组合是否能进入下一轮
C2–C7 评估。

## 运行

隔离输入根目录应包含：

```text
core-alpha4/
dsh-context/
dsh-routing-suite/
dsh-memoir/
dsh-config-migrate/
home-full/
home-core-only/
npm-packs/
npm-packs2/
```

执行：

```bash
python evaluation/runner/run_deepseek_plugin_bundle.py \
  --bundle-root /path/to/isolated-bundle-root \
  --output evaluation/evidence/w8-deepseek-plugin-bundle-e1-e6-YYYYMMDD
```

runner 只做本地 metadata/provenance 检查与 `--dump-config` 启动检查，
不会从 registry 安装、访问真实 Provider、读取真实凭据或执行外部副作用。

`dsh-context`、`dsh-routing-suite`、`dsh-memoir` 必须声明 `dsh.bundle`；
`dsh-config-migrate` 当前声明的是 `dsh.plugin.host/client`，所以完整四件
套的 E1 必须 fail-closed。前三件套的标准装配观察结果单独记录，不能继承
Codex 或 ZWorkbench composition owner 的 E3–E6 证据。
