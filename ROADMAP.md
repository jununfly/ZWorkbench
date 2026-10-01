<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap.json` | 最后更新: 2026-10-01 21:41:02

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
├── [ ][X+] 1-4. identity↔transport 绑定（#39 · S1 前置闸门）
│   ├── [ ][X+] 1-4-1. 建 identity↔transport 单一来源绑定
│   ├── [ ][X+] 1-4-2. 删 setdefault 反向回填
│   └── [ ][X+] 1-4-3. 补 4 条 fail-closed 测试
├── [ ][X+] 1-5. S0 host-enforcement spike（最长板）
│   ├── [ ][X+] 1-5-1. 技术选型（seatbelt/容器/VM/bwrap）
│   └── [ ][X+] 1-5-2. fail-closed 三判据可测试断言
├── [!][X+] 1-6. S1 单 Provider 产品化（无 failover）
├── [!][X+] 1-7. S2 写 seam 产品化（隔离 worktree + apply + local commit）
├── [!][X+] 1-8. S3 dogfood N=10 闸门（含价值基线正式出数）
├── [!][X+] 1-9. S4 Git push 单独门
└── [ ][X+] 1-10. U5 v1 验收 checklist（codex identity UNKNOWN）
<details><summary>阻塞链：4 个节点被阻塞</summary>

- 1-6. S1 单 Provider 产品化（无 failover） ← e2: 1-4. identity↔transport 绑定（#39 · S1 前置闸门） [ ]
- 1-7. S2 写 seam 产品化（隔离 worktree + apply + local commit） ← e3: 1-5. S0 host-enforcement spike（最长板） [ ], e5: 1-6. S1 单 Provider 产品化（无 failover） [ ]
- 1-8. S3 dogfood N=10 闸门（含价值基线正式出数） ← e6: 1-7. S2 写 seam 产品化（隔离 worktree + apply + local commit） [ ]
- 1-9. S4 Git push 单独门 ← e7: 1-8. S3 dogfood N=10 闸门（含价值基线正式出数） [ ]

</details>


### 下一步可开工（ready 前 3）

- 1-10. U5 v1 验收 checklist（codex identity UNKNOWN） [ ]
- 1-2-1. 选项A：v1 维持 Codex-only 只读回退基线 [ ]
- 1-4. identity↔transport 绑定（#39 · S1 前置闸门） [ ]
<!-- ROADMAP_SECTION_END -->
