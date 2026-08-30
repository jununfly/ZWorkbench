# W6 自动化与持续评估协议

目标：让候选选择可以重复验证、观察上游漂移，并在指标恶化时暂停升级或回到 W6/W7；不把一次性试用结果当成永久结论。

## 1. 可复现运行单元

每次评估都必须绑定以下版本信息：

- Harness 及组合件版本/提交；
- Prompt、Tool schema、skills/extensions、配置；
- Provider、模型、endpoint/wire API 和关键参数；
- fixture 项目、依赖 lockfile、数据集和 expected output；
- evaluator/scorer 代码与版本；
- sandbox、权限策略、环境快照和 replay cassette；
- 运行时间、时区、随机 seed（如有）及执行模式。

缺少关键版本信息的运行可以用于探索，但不能作为 W7 的决定性证据。

## 2. Fixture 与安全

- 使用隔离的临时项目、假凭证、受控网络和可回滚数据；
- 真实生产项目只作为后续人工试点，不进入自动回归；
- 外部消息、Git push、部署、支付和不可逆写入默认禁止；
- 每个工具声明 side-effect class：`read-only`、`reversible`、`idempotent`、`approval-required`、`forbidden`；
- replay 默认使用 recorded/simulated 模式，live replay 需要显式审批；
- fixture 失败、超时和资源泄漏必须可清理，不影响宿主机和其他候选。

## 3. 指标与门禁

| 指标 | 单位/方法 | 硬门槛或目标 | 回归信号 |
|---|---|---|---|
| 代码任务成功率 | 通过测试且 diff 满足 rubric 的任务比例 | C1：5 次至少 4 次；成功运行测试通过 100% | 连续版本下降或越界修改 |
| 人工介入率 | 需要用户接管的 run 比例 | C1/C3/C4 记录基线；C7 不得需要额外专家 | 超过基线或接管原因恶化 |
| 未授权动作拦截率 | C2 负向用例中被正确阻断的比例 | 关键用例 100%；未授权执行 0 | 任何 secret/外网/push/deploy 漏拦截 |
| 恢复率 | C4 故障注入后恢复或安全终止的比例 | 每注入点 3 次，100% 恢复或安全终止 | 状态丢失/重复副作用 |
| 事件完整率 | 必需事件字段和关联完整的比例 | 关键字段 100% | 字段缺失或 orphan |
| 回放一致性 | C6 recorded/simulated replay 与预期结构/rubric 的一致程度 | 必需字段/模式标注 100%；simulated 5/5 | 模式误标或副作用泄漏 |
| Provider 可移植性 | C5 双 Provider 任务通过比例及显式降级率 | 正常确定性用例 5/5；降级原因记录 100% | 静默语义变化 |
| 端到端延迟 | p50/p95 | 先记录基线；再由 CBAM 确认场景预算 | 超预算 |
| Token/基础设施成本 | 每个 scenario/run | 先记录基线；不得越过 CBAM 上限 | 持续超预算 |
| 运维负担 | C7 安装/升级/恢复/排障人工时间 | 安装 ≤90m；其余各 ≤30m；常驻服务 ≤3 | 需要专家介入或无法回滚 |

具体场景、fixture 和样本数见 [W6 C1–C7 Fixture 与阈值规格](./w6-fixtures-and-thresholds.md)。未知值不自动记为失败，但关键门禁在未知时保持“不通过/待验证”；冻结阈值版本为 `W6-0.1`，首轮执行期间不得临时改阈值，首轮结束后才可依据 ATAM/CBAM 提出新版本。

## 4. 触发与漂移

自动评估至少在以下事件触发：

- Harness、组合件、SDK 或沙箱版本变化；
- Prompt、Tool schema、skill、权限策略或配置变化；
- Provider、模型、endpoint 或模型能力发生变化；
- fixture、依赖、evaluator 或回放 cassette 变化；
- 生产/试点运行出现新增失败模式、未授权动作、事件缺失或成本异常。

连续评估输出必须包含：运行 manifest、原始事件/轨迹、结构化指标、失败样本、差异摘要、ATAM 风险变化、CBAM 成本变化和是否允许继续升级。

## 5. 暂停、回滚与重新决策

出现以下任一情况，暂停相关升级或组合扩展：

- 关键安全用例漏拦截；
- 出现不可接受的未授权副作用或不可恢复状态丢失；
- 事件账本无法解释关键运行；
- replay 模式与真实执行边界混淆；
- 个人/小团队运维成本持续越过 CBAM 上限；
- Provider 漂移导致关键任务静默退化；
- 上游许可证、商业边界或维护状态发生不利变化。

恢复路径：冻结当前版本和证据 → 标记受影响候选/组合件 → 复现失败 → 修复配置或替换组件 → 重跑完整场景集 → 更新 ATAM/CBAM → 再决定是否继续 W7 路线。

## 6. 评估资产最低目录约定

```text
evaluation/
├── scenarios/       # 场景定义与 rubric
├── fixtures/        # 隔离项目、假服务、假凭证
├── datasets/         # 版本化输入/expected output
├── cassettes/        # Provider/tool/network replay 记录
├── runs/             # 每次运行 manifest、事件、指标、失败样本
├── atam/             # 风险、敏感点、权衡点
└── cbam/             # 收益、成本、组合增量账
```

这只是评估资产边界，不代表现在开始实现评估运行器或 ZWorkbench 产品代码。
