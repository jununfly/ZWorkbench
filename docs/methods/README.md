---
doc-kind: method
authority: primary
authority-id: method.evidence-and-safety
---

# ZWorkbench 方法论

## 证据对象

每个结论都绑定被验证的主体、边界、输入、policy、artifact 与 oracle。证据必须区分：

- `source capability`：源码或文档声明的能力；
- `native`：目标 runtime 自身可观察的行为；
- `plugin-composed`：由 plugin 组合得到的行为；
- `outer-composed`：由外层 adapter、fixture 或 broker 提供的行为；
- `owner-backed`：由 CompositionOwner 持久化和关联的行为。

较弱证据不能升级为较强证据。配置回显、目标未改变、`waitingOnApproval`、单次成功或
schema 存在都不是 native 行为的替代物。

## 失败语义

`unknown` 表示证据不足，既不是失败也不是通过。安全、identity、effect、replay、Provider
或外部结果不确定时，系统必须 safe-stop：不推断成功、不自动重试不可安全的 effect，先
reconcile 可观察的事实。

所有可能产生副作用的行为使用同一语义：

```text
request → policy → decision → claim → execute → complete/reconcile
```

每一步以 operation、resource、attempt、idempotency key 与 receipt 关联；approval 只覆盖精确
操作，不能扩展为全局授权。

## 评测方法

评测使用 case-local workspace、假凭证、loopback/fake Provider 与固定 fixture。真实 Provider、
真实凭证、真实项目和不可逆外部 effect 必须使用独立、显式授权的边界；它们不继承 fixture
的通过结论。

评测覆盖安全、幂等、故障恢复、Provider 路由、replay 与生命周期。阈值必须逐 case 满足；
不得以平均分掩盖未授权 effect、关键状态丢失、事件缺失或外部结果不确定。

## 架构决策方法

ATAM 用于识别质量属性、敏感点、权衡点与风险；CBAM 用于比较可测收益和全生命周期成本。
新增 Harness、Provider 层、插件、常驻服务或 durable state owner 时，必须同时说明其不可重复收益、
权限面、备份/恢复、升级、退出与维护成本。

评测的当前可执行合同由代码、tests 与 versioned fixtures 表达；历史测量和实施过程不构成仓库文档的一部分。
