# `dsh-config-migrate` dynamic-plugin adapter fixture

这是 acceptance/evaluation fixture，不是 ZWorkbench 产品运行时。它为
`dsh-config-migrate@1.0.0` 的 `dsh.plugin.host/client` 合同定义一个
outer-composed、fail-closed adapter 边界。

本轮 E1/E2 runner 只读取固定 source checkout 的 commit 内容，使用 Node
`new Function()` 做函数体语法解析，不执行 host/client，也不启动 DeepSeek
Harness、不安装 npm 包、不访问网络、不读取真实凭据、不创建 composition owner
数据库。

输入根目录复用 W8 DeepSeek bundle fixture 的隔离根，至少包含：

```text
dsh-config-migrate/
home-full/profiles/headless/package.json
```

运行：

```bash
python evaluation/runner/run_deepseek_config_migrate_adapter.py \
  --bundle-root /path/to/isolated-bundle-root \
  --output evaluation/evidence/w8-deepseek-config-migrate-adapter-e1-e2-YYYYMMDD
```

E1/E2 通过只代表 adapter 可以进入下一轮 plugin-aware 设计。之后仍需以同一
case-local owner 和相同门槛重开 E3–E6；不得把本 fixture 的静态解析结果当成
动态插件已安全运行或四插件组合已通过。
