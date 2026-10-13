# 工作台「日常可用」体验差距 — 暂存 Plan

> **状态**：transient staging（过程文档）
> **创建**：2026-10-13
> **来源**：用户体感评审（基于 v1 Codex-only fallback 回退基线）
> **处置约定**：本文件为 docs-ontology 下的暂存 plan，待各结论沉淀为 `docs/designs/*` 或 `docs/zj-adr/*` 后应移除，不长期留存。

## 背景

v1 实际是「受控只读运行 + 审计台账」回退基线，不是面向日常使用的工作台应用。用户从使用体感提出 5 项体验问题，经代码核查，部分属「设计如此」（安全/审计优先硬约束），部分属「真缺口」。本 plan 仅**捕获这 5 项待办**，不展开改造方案（改造方案见后续 design/ADR）。

## TODO 清单

### [ ] 1. 启动收口（启动复杂）
- **现象**：安装需构建 wheel；UI 真实入口 `ui` 必带 `--db --case-root --workspace --codex --provider-profile --real-provider-gate` 一长串 flag；`ui-host` 为纯只读宿主，不接 DB/provider。无持久化用户配置、无一键 `serve`、无首次运行引导。
- **证据**：`README.md:25-32`（构建安装）；`cli.py:427-466`（`ui` flag 集）、`cli.py:355-387`（`ui-host` 只读）、`cli.py:1507`（`execution_enabled` 判定）。
- **目标**：持久化 config + 一键 `zworkbench serve` + 首次 `doctor` 自检引导，去掉构建 wheel 与长 flag。

### [ ] 2. 界面从半成品到可用
- **现象**：满屏 `aria-disabled` 只读占位（新建工作记录、预检运行、composer/run-rail 全 disabled）；A/B/C 三变体仅 A 真渲染，B/C 留 product gate(1-2)；`task-detail`/`record-view` 仅只读投影。
- **证据**：`ui_home.py:334-340`、`ui_home.py:1183`、`ui_home.py:651-663`、`ui_home.py:1086-1128`。
- **目标**：把 aria-disabled 占位与 B/C 变体从 product-gate 落地为可操作工作面。

### [ ] 3. chat→provider 过程可见 + 调用稳定
- **现象**：
  - 过程不可见：composer POST → 后台 daemon 跑一次 `LocalReadOnlyRunOrchestrator`，UI 仅 2s 轮询刷新最终文本；adapter 已采集 `item/agentMessage/delta` 与完整 event 流，但 UI 不呈现中间步骤/工具调用。
  - 调用不稳：S1 单 Provider 无 failover，`classify_provider_failure` 将 network/rate_limit/turn_wait 全部判 terminal+safe-stop；默认 `fake-loopback`/`fake-model`/`http://127.0.0.1:11434`，开箱不连真模型；依赖外部 `codex` 二进制 + config 拷贝，任一缺失即 fail-closed；超时策略保守。
- **证据**：`ui_run.py:134-149,166-177`、`ui_host.py:78-81`、`ui_home.py:584-588`；`codex_adapter.py:92-157`、`codex_adapter.py:338-365`、`codex_adapter.py:683-700`；`cli.py:109-111`（默认 fake）。
- **目标**：实时推送 event 流（SSE/轮询 `/api/events`）逐条显示；默认接真实 model 或首次引导选 provider；加单 Provider 内超时/重试退避。

### [ ] 4. Context / Memory 数据层（架构级缺失）
- **现象**：composition schema 仅 run/event/approval/provider 记账表，无任何 memory/context/conversation/workspace/project 表；每次 composer 发送都是新建独立 run，无跨 run 上下文拼接、无长期记忆、无检索/embedding；首页「会话流」只是已记录 run 的日志投影。
- **证据**：`composition.py:2705-2965`（表清单无领域表）；`ui_run.py:83`（`run_id = "run-" + uuid` 每次新建）；`ui_home.py:551-621`（会话即日志）。grep 全仓 `memory/context` 命中均注释/`contextlib`/UI 文案，无实现子系统。
- **目标**：新建领域表（会话、长期记忆、项目/工作区），让 composer 带上下文、可跨 run 续聊。

### [ ] 5. 数据库作为工作台数据中心（当前仅审计 ledger）
- **现象**：单 SQLite `composition.sqlite3` 为追加式审计台账（JSON blob 落库），无面向工作台领域的内容表（任务/笔记/文件/项目/偏好/索引）；无全文检索、无内容存储、无关系建模、无跨实体查询；snapshot/export/backup 仅整库序列化。
- **证据**：`composition.py:255`（JSON blob 落库）、`cli.py`（snapshot/export 整库序列化）。
- **目标**：新建领域数据层（与 owner 分离或在其上扩展），承载工作台各方面信息与数据的完善处理。

## 优先级建议（待用户拍板）

按「最能直接改善今日体感」排序：
1. **启动收口**（#1）— 降低日常启动成本。
2. **过程可见**（#3 前半）— 已采集事件流仅缺 UI 接线，性价比最高。
3. 其余按 #3 稳定性 → #4 Context/Memory → #2 UI → #5 DB 领域层推进。

## 下一步

用户确认后，针对某一层出「具体改造方案 + 文件级改动清单」，按 TDD/小切片拆为可验证切片。
