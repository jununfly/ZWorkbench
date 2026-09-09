---
doc-kind: reference
authority: supporting
---

# ZWorkbench 外部 References

这里放置可执行的外部合同、账户 owner 边界和受控 runbook。它们不修改默认产品配置，不携带
API key、cookie、原始账户标识、Prompt 或响应正文。

- [真实 Provider 只读 staging](optional-real-provider-staging.md)：账户 owner 的一次性、受控 HTTP
  staging 与 fallback 边界。
- [真实 Codex + Provider 只读 staging](optional-real-codex-provider-staging.md)：受监督的 app-server
  合成 turn。
- [Provider inventory](optional-provider-exit-inventory.md)：只读脱敏 receipt 的字段与责任边界。
- [Provider 一手来源](optional-provider-exit-primary-sources.md)：外部合同、数据处理与退出资料。

所有真实网络请求、账户盘点或退出操作都要求账户 owner 在本机明确授权；本目录不提供远端删除、
停用、注销或 secret 交接能力。
