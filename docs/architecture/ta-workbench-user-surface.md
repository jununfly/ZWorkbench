---
doc-kind: architecture-user-surface
authority: supporting
authority-id: architecture.user-surface.workbench
---

# 工作台用户界面

## Question

ZWorkbench 如何让用户在不夸大当前能力、不复制 durable state 的前提下，快速理解正在做的工作、
其运行边界、证据与下一步？

## Scope

本页定义工作台的稳定信息结构和读模型边界，不定义视觉皮肤、具体 Web 路由或前端技术栈。
工作台展示 CompositionOwner 保存的事实，及明确标注的草稿或目标能力；它不成为 Run、approval、
effect 或 replay 的第二个 owner。

当前可证明的运行入口是 `local_read_only_run`。DSH 主 Harness、Codex Worker 和可恢复写入是
目标架构中的能力，界面必须以 `target` 或 `unknown` 呈现，直到 owner-backed 证据存在。

## Information architecture

工作台由三个互补的视图组成：

1. **工作台首页**：用于恢复上下文。左栏提供工作记录选择，中间呈现当前记录的意图、对话、
   计划和产物，右栏呈现运行事实与证据。
2. **任务详情**：用于推进单项工作。它以“意图 → 准入 → 运行 → 结果/停止”的路径组织信息，
   展示每一阶段的证据与缺失项。
3. **记录视图**：用于回顾，显示已经保存的事件、结果和 replay metadata。它是 recorded view，
   不是 live replay。

~~~text
工作台首页
┌──────────────────────────────────────────────────────────────────────┐
│ workspace context · mode / boundary · implementation status          │
├────────────────┬────────────────────────────────┬────────────────────┤
│ 工作记录        │ 当前工作                        │ 运行事实           │
│ - 标题          │ - 意图 / 对话 / 计划            │ - Run / child ID   │
│ - 状态          │ - 产物与下一步                  │ - policy / scope   │
│ - 最后活动时间  │                                │ - effect / approval│
│                │                                │ - evidence         │
└────────────────┴────────────────────────────────┴────────────────────┘

任务详情
intent → preflight → run / child run → result | failed | safe-stopped
            │              │                         │
         policy         event trail              evidence / reconcile
~~~

## Read-model boundary

“工作记录”是界面中的上下文容器，不是新的 canonical entity。

- 已经执行的记录以 `run_id` 为 identity，运行状态、时间、parent/child 关系、event、result、
  effect、approval 与 replay metadata 只从 CompositionOwner 读取。
- 尚未提交的工作只能标为本地草稿；它没有 `run_id`，不能伪装为 owner-backed Run，也不能承诺
  跨重启恢复。把草稿变为 durable 工作对象需要单独的 owner 合同。
- DSH/Codex session、Provider 日志和前端缓存只能补充展示 identity 或 evidence；它们不能生成
  工作记录的运行状态，不能填补缺失的 identity。
- 界面适配层可以把 Owner snapshot、`LocalReadOnlyRunResult` 与脱敏 artifact metadata 投影为
  只读 DTO，但不得向 SQLite 直接写入、不得自行推断成功或状态迁移。

## Home surface contract

| 区域 | 必须显示 | 权威来源 | 缺失或未知时的行为 |
|---|---|---|---|
| 全局上下文 | workspace 范围、run mode、`implemented` / `target` 标记 | 入口 config、Owner metadata | 显示 `unknown`；不默认展示为可写工作区 |
| 工作记录列表 | 标题或脱敏输入摘要、`run_id`、状态、最后活动时间 | Owner runs / events | 没有 owner identity 的项目标为“本地草稿” |
| 当前工作 | 用户意图、已记录的 agent 文本、计划、可访问产物 | Owner input / events / results / artifact metadata | 不能取得的内容显示“未记录”，不从 session 补猜 |
| 运行事实 | status、parent/child run、Provider 与环境/事件 digest、workspace digest | Owner snapshot、run result | identity 缺失即 `unknown` / safe-stop，而非 completed |
| effect 与 approval | effect class/status、精确 approval 决定、reconcile 状态 | Owner effects / approvals | read-only 运行显示“不适用”；未知不显示为“无副作用” |
| Evidence | event、result、artifact、replay metadata 的摘要与 identity | Owner events / results / replays | recorded view 只能查看已保存内容 |

## Task-detail contract

详情页强调一项工作是否能继续，而非聊天内容的长度。

| 阶段 | 显示内容 | 当前安全语义 |
|---|---|---|
| Intent | 输入摘要、task type、关联记录 | 脱敏；没有 Run 的草稿不声明已提交 |
| Admission | preflight status、checks、violations、policy digest | deny 表示未启动，不创建“运行中”外观 |
| Execution | parent/child identity、attempt、Worker/Provider identity、事件时间线 | 缺失或不能关联的消息停止解释，标为 unknown |
| Result | semantic result、error class、artifact metadata、exit evidence | Worker 文本完成不等于 parent Run completed |
| Effect | request、decision、claim、receipt 或 reconcile | 不确定外部结果显示 safe-stop；不自动 retry |
| Replay | `recorded_view` / `simulated_replay` / `live_replay` 模式 | live replay 默认拒绝，不能与查看记录共用操作入口 |

## Status language

状态必须是可读文本加来源，不只依赖颜色。界面使用以下词汇：

- `created`、`running`、`recovering`、`completed`、`failed` 与 `safe-stopped`：Owner Run 的状态。
- `denied`：preflight 未准入，尚未执行。
- `unknown`：身份、effect、外部结果或必要 evidence 不足；它不是失败的同义词，也不是成功。
- `implemented`：当前入口能够以代码、测试或 owner-backed run 证明的能力。
- `target`：目标架构中的能力，尚未被本界面当作可执行功能。

颜色仅作辅助：常规文本使用高对比暖灰；鼠尾草绿表示已验证/当前进行，赭石表示需要注意，
砖红表示 safe-stop 或失败。每种状态都必须保留文本标签与非颜色线索。

## Minimum interactive surface

初始工作台只允许不产生副作用的交互：选择工作记录、展开详情、筛选已保存事件、打开 artifact
metadata，以及切换 recorded view。没有 owner-backed 合同的操作应当不出现或明确禁用并说明原因。

以下操作不能由界面外观暗示为已可用：启动真实写入、apply diff、approval、自动 retry、Provider
切换、Git push、部署和 live replay。它们各自需要 owner policy、approval/effect、receipt 与
reconcile 的独立实现。

## Interface reference and review boundary

界面语义元素拥有稳定的机器引用，使 Human 与 AI 能指向同一个元素而不依赖“左边卡片”这类描述。
引用由代码声明，构建派生出 UI Reference Manifest；manifest 是代码的派生产物，不是第二份手工
维护的映射表，也不是 CompositionOwner 之外的第二个 owner。

**身份稳定性。** 映射版本 `ui_map` 只摘要引用语义：引用名、中文语义名、元素类型、视图归属、
父级与生命周期元数据。源码快照、构建 receipt 与无障碍名称都被排除在摘要之外——它们随文案和
重构漂移，若进入摘要，一次注释改动就会作废所有已复制的反馈。视觉重排不改引用；语义改变必须
新建引用。

**生命周期。** 改名是同一身份，声明为 alias，解析结果为 `migrated`。语义替换是不同身份，声明
为退役加替代目标，解析结果为 `retired`，且不得表述为同一身份。别名自指、别名与在用引用冲突、
两个声明争夺同一旧名、替代目标缺失或成环，都在构建期拒绝。

**版本兼容窗口。** 当前映射版本只保留对紧邻上一版本的显式迁移。跨越更早版本返回
`incompatible`。窗口内解析必须出示旧 manifest 实物核对，拿不到就是 `incompatible`——当前
manifest 永不静默替代它所不能证明的历史版本。

**实例与结构分离。** 结构引用定位声明，实例定位当前挂载的元素。实例句柄在评审会话内随机分配，
只在内存关联，不从 Run ID、标题、列表位置或其哈希派生，不是凭证也不是 durable entity。卸载为
`unavailable`，跨会话为 `expired`，无句柄的重复结构为 `ambiguous`——不默认取首项。

**反馈通道边界。** 反馈 token 只携带白名单字段，不接受自由格式上下文，不抽取页面文本推断语境。
prompt、运行标题、完整 Run ID、原始事件、Owner snapshot、凭证与本机绝对路径都不得进入 token、
overlay 或链接。token 是定位符，不是执行或授权入口；展示状态不是 Owner 状态的恢复指令。深链接
只做界面导航，不恢复 Run、不触发预检或 apply。

**评审模式边界。** 评审模式默认关闭，仅本地显式开启。它选择而不代劳：面板内锁定目标，绝不向
业务元素派发点击；高亮层不接收指针事件，普通点击与键盘激活保留原有业务行为。Escape 仅在面板
持有焦点且无业务弹窗时消费。复制由用户发起，失败可见且不自动重试。关闭或卸载释放 overlay、
监听器与后台资源。

**覆盖度量。** 语义覆盖矩阵是独立于 manifest 的验收规格。分母来自规格而非已有声明，否则未实现
的单元会从报告中消失而非显示为缺口。“选择不展示”需要写明理由且仍留在分母，与“已验证”是两种
不同主张，不合并计数。结构覆盖满格不等于验收通过：依赖真实浏览器的交互面在宿主落地前保持
`unknown`，不得标注为不适用。

## Usability threshold

在首页，用户应能不离开当前视图地回答：

1. 上一次工作是什么，当前是否已有 owner-backed Run？
2. 当前状态是继续、已完成、已拒绝、失败，还是必须 safe-stop？
3. 哪个证据支持该判断，下一步需要什么输入或 reconcile？

如果任一答案只能靠猜测 DSH/Codex session、颜色或模型文本，界面必须降级为 `unknown`，而不是
给出确定结论。

## Related authority

- [系统概览](README.md)
- [CompositionOwner](ta-composition-owner.md)
- [本地只读运行流](ta-local-read-only-flow.md)
