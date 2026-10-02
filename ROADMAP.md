<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap.json` | 最后更新: 2026-10-02 18:59:45

[~][X+] 1. ZWorkbench v1 真实可用推进路线图
├── [x][X+] 1-1. 已闭环结论（讨论沉淀 · 参考锚点）
│   ├── [x][X+] 1-1-1. make-it-usable 四子文档全 DONE_WITH_CONCERNS
│   ├── [x][X+] 1-1-2. sub-01 Q3 选边 (i)/(ii) ARK 实测闭合
│   └── [x][X+] 1-1-3. U1/U3 竞品对照实证 + R3 回填完成
├── [x][X+] 1-2. 开放产品决策：v1 写能力出货口径（S0→S2）
│   ├── [ ][X+] 1-2-1. 选项A：v1 维持 Codex-only 只读回退基线
│   └── [x][X+] 1-2-2. 选项B：#40 解后默认开放写（S0/S2 receipt + N=10 控险）
├── [x][X+] 1-3. 产品 CLI 放开真实 Provider（#40）
│   ├── [x][X+] 1-3-1. local_run.py factory 读 provider_identity 替代 ollama 硬编码
│   ├── [x][X+] 1-3-2. preflight 对 remote/custom provider 显式授权放行
│   └── [x][X+] 1-3-3. 回归测试：三 deny 分支 + 配置读取
├── [x][X+] 1-4. identity↔transport 绑定（#39 · S1 前置闸门）
│   ├── [x][X+] 1-4-1. 建 identity↔transport 单一来源绑定
│   ├── [x][X+] 1-4-2. 删 setdefault 反向回填
│   └── [x][X+] 1-4-3. 补 4 条 fail-closed 测试
├── [x][X+] 1-5. S0 host-enforcement spike（最长板）
│   ├── [x][X+] 1-5-1. 技术选型（seatbelt/容器/VM/bwrap）
│   ├── [x][X+] 1-5-2. fail-closed 三判据可测试断言
│   └── [x][X+] 1-5-3. 真机 OS 强制验证（非沙箱宿主 mac Terminal / CI runner）
├── [x][X+] 1-6. S1 单 Provider 产品化（无 failover）
│   ├── [x][X+] 1-6-1. S1 前置 DoD①：preflight 三 deny 分支各一条负路径断言（校验/补齐）
│   ├── [x][X+] 1-6-2. S1 前置 DoD②：唯一词表映射表落 owner 侧作 SSOT + 一致性测试
│   ├── [x][X+] 1-6-3. 已验证 Ark 只读路径从 scripts/ 收进默认入口 zworkbench run（端到端，含 secret 0 落盘/stdin 注入核验）
│   ├── [x][X+] 1-6-4. owner 记录失败分类 / safe-stop（网络/限流/unknown→safe-stop）
│   ├── [x][X+] 1-6-5. Provider 接入经 Host Capability Facade（架构负约束，不直连）
│   └── [x][X+] 1-6-6. Provider-side 退出记账接入默认路径（unknown/delegated 口径）
├── [x][X+] 1-7. S2 写 seam 产品化（隔离 worktree + apply + local commit）
│   ├── [x][X+] 1-7-1. S2-① 隔离 worktree 创建 seam（主工作区零触碰，路径归 owner 记录）
│   ├── [x][X+] 1-7-2. S2-② diff apply（接收 unified diff，非法 patch 拒绝并保留 worktree 干净）
│   ├── [x][X+] 1-7-3. S2-③ local commit（worktree 内 git commit，无 push，reset 可回退）
│   ├── [x][X+] 1-7-4. S2-④ owner-backed receipt（operation/action/resource/idempotency key 绑定 + external_receipt，无第二 owner）
│   ├── [x][X+] 1-7-5. S2-⑤ approval 精确绑定 + 执行级幂等（同 key 两次 apply 仅一次 digest 变化）
│   └── [x][X+] 1-7-6. S2-⑥ Control Plane / CLI 集成（orchestrator 接 write seam，push 默认关）
├── [ ][X+] 1-8. S3 dogfood N=10 闸门（含价值基线正式出数）
├── [!][X+] 1-9. S4 Git push 单独门
└── [ ][X+] 1-10. U5 v1 验收 checklist（codex identity UNKNOWN）
<details><summary>阻塞链：1 个节点被阻塞</summary>

- 1-9. S4 Git push 单独门 ← e7: 1-8. S3 dogfood N=10 闸门（含价值基线正式出数） [ ]

</details>


### 下一步可开工（ready 前 3）

- 1-10. U5 v1 验收 checklist（codex identity UNKNOWN） [ ]
- 1-2-1. 选项A：v1 维持 Codex-only 只读回退基线 [ ]
- 1-8. S3 dogfood N=10 闸门（含价值基线正式出数） [ ]
<!-- ROADMAP_SECTION_END -->
