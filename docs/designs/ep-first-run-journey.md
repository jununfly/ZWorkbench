---
doc-kind: design
authority: supporting
axis: experience-path
status: target
implementation-status: unknown
source: ../prds/r4-onboarding-first-run.md
source-id: prd-r4-onboarding-first-run
authority-id: design.first-run-journey
---

# 体验路径：首跑旅程（默认产品路径）

本页是 R4 的**体验路径实体**，描述验收轨（主语 = zj）从安装到在浏览器看到自己 run 的 recorded view 的端到端路径。

## Question

一条命令、不读 README、零凭证，用户能否完成首跑并在 loopback UI 看到自己的 recorded view？

## Scope（默认路径步骤）

1. 干净环境（仅 python3.9+）`pip install .`。
2. `zworkbench run --prompt "..."`（或 `zworkbench demo`）：自动脚手架 `case-root + workspace + state` 子目录；`--codex` 缺省按 PATH 探测并打印解析路径；Provider 默认 `fake-loopback`（零外部凭证）。
3. 默认路径即 `local_read_only_run`，结束写 `--db`（默认 `case_root/state/composition.sqlite3`）。
4. （可选）`zworkbench run ... --open`：子进程自动拉起 `ui-host`（仍 loopback、仍只读）。
5. stdout 末尾追加 `next_steps` 数组（可复制的 `zworkbench ui-host --review` 或 `zworkbench ui --db <实际 db 路径>`），无需读 README 即可在浏览器打开看到自己 run 的 recorded view。

## 验收线（机械可判定）

- 端到端脚本（用 `fake-loopback`、零外部凭证）可重放，退出码 0 且 `recorded_view_present == true`。
- `doctor` 在零凭证环境全绿可跑，`git status` 无副作用文件。
- 人为制造「目录缺失」「超时」两种失败，输出须含可执行修复动作（fail-closed UX 成本回收）。

## Boundaries

- 真实 Provider 不在默认首跑路径内，仅作显式旁路（staging runbook 引导）。
- 「非作者陌生人 <5 分钟」是 UX 目标轨，非判据，不进本路径验收。

## Status

TARGET / UNKNOWN — 端到端脚本与 `recorded_view_present` 验证仍待 owner-backed 证据（依赖 #40 解后补测）。

## Source map

- `../prds/r4-onboarding-first-run.md` §首跑最小形态、§价值演示缝合、§fail-closed UX 成本回收、§端到端回归脚本验收线。

## Related authority

- 产品设计：[pd-first-run-onboarding](pd-first-run-onboarding.md)
- 路线图：[ps-solo-real-provider](ps-solo-real-provider.md)
