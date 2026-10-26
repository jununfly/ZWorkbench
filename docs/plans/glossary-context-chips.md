# Glossary — 编码证据上下文维度（与 ADR 0019 配套）

> grill 过程中沉淀的术语片段，待 ADR 转正时并入 docs/zj-adr/ 或 ZJ-CONTEXT.md。

## 术语

- **被管理仓库 (Managed Repo)**：ZW 配置中登记、编码证据 run 可关联的 git 仓库。由 `RepoSpec{Name, Path, Environments}` 描述；同一 ZW 实例可登记多个。
- **上下文 chips (Context Chips)**：Codex 借用的 UI 范式——在 composer 上方用独立可点胶囊展示「仓库 / 环境 / 分支」等执行语境。ZW 落地为编码证据新建 run 表单的 repo/branch/environment 选择控件（后续前端节点）。
- **current_branch**：被管理仓库当前的 git 分支（由 `git symbolic-ref --short -q HEAD` 读取，unborn 分支也能正确返回；早期用 `rev-parse --abbrev-ref` 在 unborn 时误返 `"HEAD"`，已弃用）；非 git 仓或 git 不可用时回退 `"unknown"`（fail-closed）。
- **environment（执行环境）**：run 声明运行的宿主环境。名字按约定编码种类：`local`（本地，恒存在）/ `container`（或 `docker`）/ `remote:<endpoint>`（如 `remote:tcp://host:port`）；其余名字归一化为 `unknown`。**声明字段**，ZW 尚无起容器/连远程的执行器。
- **run 上下文维度 (Run Context Dimensions)**：runs 表新增的 `repo` / `branch` / `environment` 三列，使每个 CompositionOwner run 携带其产生语境。
- **后端先行节点 (Backend-First Slice)**：本次 grill 收敛出的交付切片——先落地配置 + `/api/context` + run 字段 + 单测，前端 chips 表单延后。
- **授权 (Authorization) vs 可达性 (Reachability)**：ADR 0019 Follow-up ② 拆出的两条互不耦合路径。**授权**＝environment 是否在该仓库白名单内，由后端 `POST /api/evidence/runs` 强制，违反即 400（硬约束、fail-closed）；**可达性**＝该环境此刻能否连上，由 `internal/envprobe` 只读探测，仅在 `/api/context.environment_status` 与前端提示中体现（软约束、不阻断记账）。
- **envprobe**：环境可达性只读探针包（`internal/envprobe`）。纯标准库（`os/exec`、`net`），不引 docker/container SDK，以过零依赖守卫；单环境探测上限 `ProbeTimeout=2s`。
- **resolvedRepos**：`api` 层的「生效仓库列表」解析函数——显式配置优先，为空则把 cwd 的 git 仓自动登记为默认仓。`/api/context` 与白名单校验**共用**它，保证前后端口径不漂移。
- **NormalizedEnvironments**：`RepoSpec` 的环境枚举归一化（去空白、去空串、保序去重，为空回退 `["local"]`），是白名单校验与 `/api/context` 输出的唯一口径来源。

## 不变量

- **单一 durable owner**：run 上下文字段归 evidence Owner 唯一拥有。
- **fail-closed git 探测**：git 探测失败一律 unknown，不 500。
- **向后兼容 CreateRun**：原签名保留，新增 `CreateRunWithContext` 供 router 调用。
- **白名单 fail-closed**：声称未授权环境即 400，且被拒请求不得落库（不留半成品 run）。
- **授权与可达性不耦合**：可达性失败不影响记账；白名单通过也不代表环境可用。
