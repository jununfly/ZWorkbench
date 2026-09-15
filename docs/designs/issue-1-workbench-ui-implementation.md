---
doc-kind: design
authority: supporting
status: target
implementation-status: pending
---

# Issue #1：Workbench UI 实现规格

本文是 Issue #1 的界面实现规格，说明如何把设计原型落成可维护、可验证的工作台界面。
它不替代产品需求、架构 ownership 或安全边界。

- 产品目标、范围和禁用能力见 [Issue #1 PRD](../prds/issue-1-workbench-ui.md)。
- 工作记录、任务详情、recorded view 和读模型边界见
  [工作台用户界面架构](../architecture/ta-workbench-user-surface.md)。
- 工作台宿主继续遵循 [ADR 0003](../zj-adr/0003-workbench-host-is-server-rendered-html-over-loopback.md)。

## Design input

仓库内保存的视觉和信息架构参考是
[Workbench prototype](assets/zworkbench-workbench-prototype.html)。它是 throwaway prototype：
只使用内存示例数据，不连接 CompositionOwner，不创建 Run、Effect 或 Approval。

原型中的三个方向对应三个正式视图：

| 原型方向 | 正式视图 | 主要问题 |
|---|---|---|
| A 会话优先 | `/home` | 恢复上下文，查看当前工作、计划、事实和证据 |
| B 命令画布 | `/task-detail` | 查看 `intent → preflight → run → result / stop` |
| C 项目日记 | `/record-view` | 回看已保存事件、结果和 replay metadata |

底部的方向切换器、场景切换器、`DESIGN PROTOTYPE` 横幅和示例文本属于评审 fixture，
不属于正式产品功能。它们不能让用户误以为能够切换真实 Run 状态或执行副作用。

## Visual system

样式以原型为视觉参考，以语义化 CSS token 统一管理，不让页面 renderer 各自发明颜色和间距。

| Token | Value | 用途 |
|---|---|---|
| `canvas` | `#FAE8C5` | 页面背景 |
| `surface` | `#FFF8EB` | 面板和卡片 |
| `surface-raised` | `#FFFDF7` | 输入框、按钮、抬升层 |
| `surface-strong` | `#F3DEB6` | 选中项、卡片头部 |
| `line` | `#D8C5A2` | 主边框 |
| `line-soft` | `#EAD9B9` | 次级分隔线 |
| `sage` | `#6E6F50` | 已验证、当前进行 |
| `amber` | `#D09C65` | 注意、待处理 |
| `rose` | `#8F6650` | 失败、安全停止 |
| `ink` | `#333333` | 主要文字 |

字体顺序保持对中文和无外部网络的兼容：正文使用 PingFang / Noto Sans / system sans，
运行身份、状态和证据摘要使用等宽字体；项目日记标题可以使用本机 serif fallback。
图标使用同一套 inline SVG 语义图标，不使用 emoji 作为界面图标。

## View contracts

### `/home`：会话优先首页

宽屏结构为 `236px / flexible / 318px` 三栏：

```text
topbar
├── work record navigation
├── current work
│   ├── intent / conversation
│   ├── working plan
│   └── composer（未接入时明确禁用）
└── runtime inspector
    ├── run facts
    ├── effect / approval
    └── evidence
```

首页必须帮助用户判断“现在能否继续”。运行状态、来源和下一步不能只通过颜色表达。
没有 Owner identity 的草稿显示为本地草稿；缺失 identity、effect 或 evidence 时显示
`unknown` / `safe-stopped`，不得从 DSH/Codex session 猜测。

### `/task-detail`：命令画布

主要内容为意图和运行路径，右侧为本次工作的事实 rail：

```text
intent → preflight → run / child run → result | failed | safe-stopped
           │              │                         │
        policy         event trail              evidence / reconcile
```

`denied` 表示未准入，不得渲染出“运行中”的外观。Worker 完成也不能直接推断 parent Run
已完成；关联缺失时停止解释并显示 `unknown`。

### `/record-view`：项目日记

左侧为记录选择和筛选，中央为按时间阅读的 recorded view。结果、Artifact metadata 和
Replay metadata 默认可以放入原生 disclosure 中；打开它们仍然只读已保存事实。
此视图不能显示为 live replay，也不能因为打开页面而恢复 Run 或联系 Provider。

## State fixtures

原型的场景成为测试输入，不成为正式产品的客户端状态机：

| Fixture | 预期表现 |
|---|---|
| `empty` | 明确说明没有工作记录，不创建持久状态 |
| `planning` | 展示意图、计划、当前边界和下一决定 |
| `denied` | 展示 preflight 拒绝和 violations，未创建运行中外观 |
| `approval-required` | 只展示目标概念和待审批事实，不提供真实执行按钮 |
| `safe-stopped` | 展示停止原因、unknown identity/effect 和 reconcile 需要 |
| `recorded-view` | 只读取已保存事件、结果和 replay metadata |

每个 fixture 至少在 `390px` 和 `1280px` CSS viewport 验证。产品默认不提供用于切换这些
fixture 的控制器；如需人工评审，可在独立 review/demo 入口中使用。

## Rendering and data boundary

渲染保持纯函数，调用链固定为：

```text
CompositionOwner
        ↓
Control Plane façade
        ↓  脱敏、白名单投影
view model
        ↓
server-rendered HTML
        ↓
http://127.0.0.1:<port>
```

推荐的展示区域为 `context`、`records`、`current_work`、`plan`、`run_facts`、`effects`、
`approvals`、`evidence` 和 `replay`。缺失值应携带明确的显示状态和来源，而不是由 renderer
自行推断。

当前实现对应的代码边界是：

- `src/zworkbench/ui_style.py`：token、结构样式和响应式分支。
- `src/zworkbench/ui_home.py`：首页 HTML 和 `home_manifest`。
- `src/zworkbench/ui_task_detail.py`：任务详情 HTML 和 manifest。
- `src/zworkbench/ui_record_view.py`：记录视图 HTML 和 manifest。
- `src/zworkbench/ui_view_model.py`：Owner 到脱敏 view model 的唯一展示入口。
- `src/zworkbench/ui_host.py`：loopback HTTP host、路由、viewport meta 和 review 资源。

UI 不直接写 SQLite，不在浏览器持久化 Owner snapshot、prompt、凭证、approval token 或
event payload。原型里的 `owner-backed` 只有在数据确实来自 Owner façade 时才可使用；
fixture 应标为 `prototype` 或 `fixture`。

## Responsive rules

- `1280px`：首页三栏；命令画布主内容加 `274px` rail；日记保留 `270px` index。
- `1100px` 以下：首页隐藏 inspector，命令画布 rail 改为横向统计区域。
- `760px` 以下：首页和日记转为单栏并隐藏侧栏；命令画布上下排列；日记条目改为单列。
- 所有页面必须避免横向滚动，保留可读状态文字，并提供可见的键盘 focus。
- hover 只改变颜色、边框或阴影，不改变布局；动画遵循 `prefers-reduced-motion`。

同一语义单元在不同视口只改变布局，不改变 `data-ui-ref`。样式选择器不得依赖
`data-ui-ref`，引用 manifest 也不得成为视觉样式的第二个来源。

## Allowed interactions

首期只实现无副作用交互：选择工作记录、展开详情、筛选已保存事件、打开 Artifact metadata、
切换 recorded view，以及显式开启的本地 review mode。

以下动作必须隐藏或明确禁用，不能由视觉外观暗示为已可用：真实写入、apply diff、Approval
执行、自动 retry、Provider 切换、Git push、部署、Webhook 和 live replay。

评审模式只选择和标注元素，不向业务元素派发点击；overlay 不拦截指针；token 只携带白名单
定位信息；关闭评审模式后监听器、overlay 和后台资源归零。

## Verification loop

实现顺序固定为：

1. 以 `/home` 的 `planning` fixture 和 `1280px` 完成静态视觉壳。
2. 在真实浏览器中验证三栏尺寸、字体层级、间距、边框、阴影和溢出。
3. 增加 `empty`、`unknown`、`denied` 和 `safe-stopped` 负向状态。
4. 在 `390px` 验证单栏布局、无横向滚动、焦点和可读状态。
5. 接入 `ui_view_model.py` 的 Owner-backed 脱敏数据。
6. 依次完成 `/task-detail` 和 `/record-view`。
7. 最后开放已在 PRD 中允许的只读交互。

验收证据至少包括：

- 真实浏览器在 `390px` / `1280px` 的布局和计算样式结果。
- 空、拒绝、失败、unknown、safe-stopped 和 recorded view fixture。
- UI manifest 与实际 DOM 引用一致，且样式没有引用选择器。
- 键盘 focus、非颜色状态线索、reduced motion 和无横向滚动检查。
- `ui_host.py` 的 loopback、viewport meta、生命周期和 review-mode 边界测试。

截图和大型机器生成 evidence 默认只保存在本地，不作为长期文档内容或批量提交物。

## Non-goals

本文不引入前端框架、桌面外壳、浏览器 durable state、新 Agent loop、第二个 durable owner、
真实 Provider、主工作区写入、云同步或多用户协作。
