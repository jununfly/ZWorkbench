# W7-1 候选固定版本与可复现执行包

状态：`in_progress` · `acceptance/evaluation` · 不进入 ZWorkbench 产品实现

本节点的目标是把 W7 的首个候选验证变成可复核的实验包。它只冻结候选身份、
运行入口、评估合同和回滚目标，不代表候选已采用，也不代表 C2–C7 或产品安全
已经通过。

## 1. 验证顺序决策

W7 先验证 Codex Harness（`openai/codex`），保留 DeepSeek Harness
（`deepseek-ai/deepseek-harness`）作为对照候选。

这是验证顺序，不是最终选型：

- ATAM 先处理 C2 安全边界、C4 状态恢复和 C6 回放边界等高风险未知；Codex 的
  本地 sandbox、approval surface、app-server 和 rollout 证据提供了可归因的
  候选入口，适合先做边界验证。
- CBAM 先复用已有 Codex C1 adapter 和同一 W6 fixture，减少并行维护多个
  Harness 的一次性集成、持续升级和排障成本。
- 如果 Codex 的 release 身份、真实工具入口或安全边界无法绑定，立即暂停，
  不把 adapter 扩展到组合件，并切换 DeepSeek；切换仍须通过同一 manifest 和
  C1–C7 合同。

## 2. Codex 固定身份

结构化 manifest：[w7-codex-candidate-manifest.json](./w7-codex-candidate-manifest.json)

| 项目 | 当前证据 | 状态/边界 |
|---|---|---|
| canonical repository | `https://github.com/openai/codex` | 已固定 |
| release | `rust-v0.139.0` | 已固定 |
| release dereferenced commit | `a7dff904308535e965aee87680c1fc5ef1d19eec` | 已由 `git ls-remote` 解析 |
| 实际 CLI | `/opt/homebrew/bin/codex` | 已核验 |
| CLI version | `codex-cli 0.139.0` | 与 npm package version 匹配 |
| platform package | `@openai/codex` `0.139.0-darwin-arm64` | 已核验 |
| vendor binary | Mach-O arm64，SHA-256 `c6ede9ef…d83915` | 已固定 |
| package/binary build provenance | npm `gitHead=null`；无构建 attestation | `unknown`，不能称为可复现构建 |
| license | Apache-2.0 | 已记录，商业/再分发边界仍需 W7-5 审计 |
| app-server surface | `codex app-server --help` 成功 | 只证明入口存在，不证明协议嵌入契约 |

身份层结论是 `identity-pinned-release-level`：release、版本、路径和 digest
足以固定当前实验 artifact；缺少构建来源证明，因此后续报告必须保留
`source_to_binary_verified=false`。

## 3. 评估合同

本次 C1 smoke 使用当前 W6-0.1 fixture 和 runner，不访问真实 Provider 或外部
系统：

| 合同项 | 固定值 |
|---|---|
| fixture manifest | `5149f9a7d336f7b11ce895cc239fa9764043da4c0793255c651d1af14a5dd6af` |
| fixture source | `81cf7f9b62f6706d7b23de6d71915ae372617e5ceab3cef3d6e396f07de67b52` |
| Provider | `fake-a` / `fake-b`，loopback-only |
| Prompt schema | `c9f2fefb…7814e6b` |
| Tool schema | `b29fe0c8…29b9a5e` |
| sandbox | `workspace-write` |
| approval | W6 C1 runner 当前为 `never`；不能外推 C2，C2 必须改用 fail-closed adapter |
| evaluator | `run_baseline.py` SHA-256 `5e53f7a4…bec2b4f` |

特别注意：C1 的 `approval_policy=never` 只用于隔离的 C1 代码任务和 loopback
fake Provider；它不是 W7 的安全策略。下一节点必须经过 C2 adapter，任何真实
凭证、外网、Git push、部署或不可逆副作用均保持禁止。

## 4. Smoke 结果

运行证据：
`evaluation/runs/w6-0.1-baseline-20260830T144245-541564Z/summary.json`。

- fixture self-test：`7/7 pass`；
- Codex fake-a：`5/5 pass`；
- Codex fake-b：`5/5 pass`；
- 成功运行测试通过率：`100%`；
- 越界修改：`0`；
- Codex 候选总体：仍为 `unknown`，因为 C2–C7 未执行。

这次运行满足“固定包可启动并复用 C1 adapter”的 smoke 目的，但不重写 W6 的
候选证据等级：C1 通过只能支持代码闭环起点，不能抵消 source provenance、C2–C7
和 C7 真人时间的未知项。

## 5. DeepSeek 对照候选

| 项目 | 当前证据 | 状态 |
|---|---|---|
| repository | `https://github.com/deepseek-ai/deepseek-harness` | 研究对象已固定 |
| source commit | `cd5ef8148158c3a752a658978873241fdf8e2bbc` | 沿用 W2 固定引用 |
| observed version | `0.1.2-alpha.1` | W6 历史 C1 运行记录 |
| 当前可执行入口 | 本机未发现 `dsh`/`deepseek-harness` | 未冻结 |
| 当前 package/binary digest | 无 | `unknown` |
| W7 资格 | 仅作为对照，不进入 C2–C7 | pending |

历史 DeepSeek C1 运行中的 `/private/tmp/...` entrypoint 不再作为当前执行入口；
临时路径不可作为 W7 固定 artifact。若 Codex 绑定失败，下一次切换必须重新取得
DeepSeek 固定 checkout/package，生成同 schema manifest，并重跑 C1 smoke。

## 6. W7-1 放行判断

| 门 | 结果 | 处理 |
|---|---|---|
| release/source identity | Codex release-level pass；DeepSeek pending | Codex 可进入 C2 adapter 设计；DeepSeek 不宣称可运行 |
| artifact digest | Codex pass | 每次升级必须重新生成 digest |
| C1 smoke | Codex pass | 仅保留为 C1 evidence |
| reproducible build | unknown | 不能把 npm artifact 说成 source-built |
| C2–C7 | unknown | 必须逐节点实测，未知 fail-closed |
| C7 真人 stopwatch | unknown | 不得用机器墙钟替代 |

因此 `1-1` 暂保持 `in_progress`：Codex 已具备进入下一节点的固定 release-level
执行包，但 DeepSeek 对照入口和 Codex 的构建来源证明仍未完成。下一节点可以开始
设计/运行 Codex C2 fail-closed adapter，但不得同时引入第二 Harness 或组合件。

## 7. 证据索引

- [W7 采用姿态交接包](./w7-adoption-posture-handoff.md)
- [W6 首轮候选基线](./w6-baseline-candidate-findings.md)
- [W6 C2 adapter 合同](./w6-c2-adapter-findings.md)
- [W7 candidate manifest](./w7-codex-candidate-manifest.json)
