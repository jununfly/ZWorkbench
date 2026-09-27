---
doc-kind: discussion-policy
authority: temporary
---

# 临时讨论文档（co-work）政策

本目录存放 H6–H8 scope 等多 Agent 协同讨论的临时文档。遵循**一事一议**：单一议题对应单一文档。

## 目的

形成"单个 Human + 多个 Agent"的协同讨论形式：

1. Human 与主力 AI 先开会讨论，尽量收敛；
2. 讨论不清楚的问题，落成本目录下的临时文档（一议题一文档）；
3. Human 拉另一个 Agent 阅读该文档，把它的观点写入 `## Agent viewpoints` 段；
4. 据文档中的讨论过程（Human+AI 第一遍 + 各 Agent 观点）合成结论。

## 规则

- 单一议题 = 单一文档；命名 `h6-h8-<topic>.md` 或 `<topic>.md`。
- 文档生命周期：
  - `draft`：Human + 主力 AI 第一遍（上下文 + 第一遍 scope 草案 + 待讨论问题）。
  - `agent-view`：另一 Agent 读后写入观点。
  - `conclusion`：据讨论过程生成结论（通常指向 PRD/ADR 条款）。
  - `delete`：结论沉淀为权威页（docs/prds、docs/zj-adr）后，删除本临时文档。
- 临时文档**不是长期 wiki**；不在此放实施过程、评测结论或路线图状态，只放：待讨论问题 + 上下文 + Agent 观点 + 结论草稿。
- 沿用 `docs/plans/` 退役纪律：结论沉淀后本目录对应文件必须删除，不长期留存。
- 文档内所有未实现 / 无 owner-backed 证据的能力标 `target` / `unknown`，不把评测脚手架当产品能力。

## 独立性与防耦合硬规则

两个 Agent 会话在 WorkBuddy 内是运行期隔离的（独立 context window、token 不共享），但共享磁盘文件与项目系统提示（AGENTS.md / SOUL.md），存在程序性耦合风险。以下两条为硬规则，违反即破坏"多视角独立"的前提：

1. **另一 Agent 必须 `Read` 讨论文件本身**：另一 Agent（会话 B）须用 Read 工具直接读取本目录下的讨论文件，禁止由 Human 把主力 AI（会话 A）的结论转述/粘贴为 B 的输入前提。B 面对的应是 artifact（议题 + 上下文原文），不是 A 的口径。否则退化为回声室。
2. **给另一 Agent 指派结构不同的角色**：B 的角色须与 A 立场差异驱动（例如 A = 产品实用主义，B = 怀疑过度设计的资深基础设施架构师），让分歧来自视角差异，而非"请反驳 A"。禁止用对抗式指令（"请你反驳 A"）迫使 B 为反对而反对。

违反上述任一条，讨论结论不得作为独立多视角证据进入 PRD/ADR；须重做 agent-view 阶段。

## 操作实录：一次真实跑通的流程（作为示例，非结论）

> 以下基于 H6–H8 scope 协同讨论的真实跑通整理，是本政策的**流程示例**而非结论沉淀。讨论最终结论已沉淀进 `docs/prds/r3-real-usability-roadmap.md` 与 `docs/zj-adr/0008-host-enforcement-*.md`，临时文档 `docs/discussions/h6-h8-scope-kickoff.md` 已按本政策删除。读本节看"机制怎么落地"，不要把它当结论来源。

### 生命周期的实际推进

- `draft`：Human(zj) + 主力 AI 先开会，把议题的 scope 草案 + 待讨论问题落进临时文档（一事一议、一议题一文档）。
- `agent-view`：zj 拉**多个** Agent 各自 `Read` 同一 artifact，按结构不同角色写入观点（见下方角色错位矩阵）。本例实际走了三轮独立视角：
  - Agent B — 资深技术经理 / 可落地视角
  - Agent C — 行业级产品专家 / 市场·品类·采纳视角（首轮为同会话角色扮演，见下方"已验证的坑"）
  - Agent A — 资深技术架构师 / 架构约束视角，独立 grep 核验 B 的证据并修正其表述
- zj 逐轮对 Agent 观点拍板（新增 `## Human 对 Agent X 的拍板` 表），标"非 conclusion、允许主力 AI 凭证据 challenge"，不静默吞技术偏差。
- `conclusion`：据 draft + 各 agent-view 合成 conclusion 段，重写终态与切片顺序。
- 沉淀 + `delete`：conclusion 落地为 PRD/ADR 条款，随后 `git rm` 删临时文档；`_POLICY.md` 本身保留复用。

### 角色错位矩阵（可复用模板）

| 视角 | 角色 | 与主力 AI 的差异锚点 |
|---|---|---|
| 主力 AI | 产品实用主义 / 架构视角 | 基线，先收敛 |
| Agent B | 资深技术经理 / 可落地 | 逼出实现边界与切片顺序 |
| Agent C | 行业级产品专家 / 市场视角 | 逼出品类定位、护城河、scope creep 风险 |
| Agent A | 资深技术架构师 / 约束视角 | 逼出架构负约束与 fail-closed 判据 |

规则：视角覆盖 执行 / 产品 / 市场 / 架构 后即停。本例到 A 即收敛——C 已预警"三视角已覆盖，应停加视角直接合成 conclusion"，多视角是手段不是目的。

### 防耦合硬规则的实际落地

- **Read 原文**：每个 Agent 均直接 `Read` 临时文档，未由 zj 转述主力 AI 口径。Agent A 还独立 grep 源码核验 B 的证据，发现 B 的"grep 0 命中"表述不准（实为英文词 "silently" 命中、零 failover 语义实现），沉淀时改为"无 failover 语义实现"——证明独立核验有效，而非回声。
- **结构不同角色**：B/C/A 的立场差异驱动分歧，非对抗式"请反驳 A"。C 与 B 在 H7/H8 上产生实质分歧（B=定义但不建 vs C=deferred-until-demand），zj 采纳 C 修正而非取中间值。

### 已验证的坑

- **同会话角色扮演 ≠ 真正独立**：Agent C 首轮为同会话内角色扮演，未跨 provider 会话，严格说不满足"运行期隔离"。真正独立需另开 provider 会话让另一 Agent 读文件。内容虽按硬规则写法落地，但**独立性的程序性保证只在跨会话成立**；同会话角色扮演仅作轻量预演，结论权重应低于跨会话独立视角。
- **回声室退化风险真实存在**：若 zj 把 A 的结论作为 B 的输入前提，B 退化为 A 的回声。本政策硬规则 1 即为此设防；实际跑通中每个 Agent 只面对 artifact 原文，未被前置口径污染。

### 收敛判定（何时停加视角、何时合成 conclusion）

- 视角覆盖关键分歧维度（执行/产品/市场/架构）后，停止引入新视角，直接合成 conclusion。
- zj 拍板以"采纳修正 + 标 pending 待补"形式留痕，关键技术偏差不得静默归为"已接受"。
- conclusion 必须给出**可执行的沉淀指令**（改哪些 PRD/ADR、删哪个临时文档），否则讨论未闭环。
