<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap-zw-go-1to100.json` | 最后更新: 2026-10-16 17:29:04

[~][X+] 1. ZW Go/Electron 工作台 1→100 收尾
├── [x][X+] 1-1. 工程守卫与回归门禁
│   ├── [x][X+] 1-1-1. Go 侧零依赖守卫（go.mod 断言无 cgo 外部依赖 + CGO_ENABLED=0 可编译 + electron 仅 devDependency）
│   ├── [x][X+] 1-1-2. 前端生产构建门禁（npm ci + tsc --noEmit + vite build；dist 不入库）
│   ├── [x][X+] 1-1-3. Go 测试门禁（go test ./... 限时全绿；现仅 evidence/api/webstatic 三包有测试）
│   ├── [x][X+] 1-1-4. 打包脚本回归（unsigned 路径出 dmg + mtime 证据，不回归）
│   └── [x][X+] 1-1-5. 补齐 12 个无测试包的单测（cmd/server + agent/config/data/domain/inspection/limitup/market/mastery/optimization/research/review）
├── [x][X+] 1-2. 真实数据源接入（C36 远程侧现为 RemoteStubSource）
│   ├── [x][X+] 1-2-1. 统一 RemoteSource 契约与配置开关（7 个包各自 stub 固定失败）
│   ├── [x][X+] 1-2-2. 行情/研究/连板（market/research/limitup）接真实 A 股数据源
│   ├── [x][X+] 1-2-3. 复盘/心法（review/mastery）接真实源或本地可导入数据集
│   ├── [x][X+] 1-2-4. 持仓巡检/优化（inspection/optimization）接真实持仓输入
│   └── [x][X+] 1-2-5. fallback 语义收敛：区分未配置 / 源失败 / 陈旧快照，不当作成功
├── [x][X+] 1-3. LLM Provider 真实化
│   ├── [x][X+] 1-3-1. OpenAI/DeepSeek 真实端点联调（chat + 复盘/优化依赖）
│   ├── [x][X+] 1-3-2. key 存储与掩码回写安全复核（router.go:217）
│   └── [x][X+] 1-3-3. Settings 页连通性自检与错误直显
├── [ ][X+] 1-4. 证据核心 B2 补齐（对齐 Python CompositionOwner 能力面）
│   ├── [ ][X+] 1-4-1. reconcile / uncertain 恢复路径
│   ├── [ ][X+] 1-4-2. backup / restore
│   ├── [ ][X+] 1-4-3. exit ledger（Python 侧 provider_exit_ledger；Go 侧未见）
│   ├── [ ][X+] 1-4-4. identity chain 可查询（run → attempt → effect → approval）
│   └── [ ][X+] 1-4-5. safe-stop（C28）
├── [ ][X+] 1-5. 分发与安装
│   ├── [ ][X+] 1-5-1. Developer ID + 公证真跑（NOTARIZE 门控已在，只差证书）
│   ├── [ ][X+] 1-5-2. Windows 打包（win + CGO_ENABLED=0 交叉编译）
│   ├── [ ][X+] 1-5-3. 自动更新（README 明示不在本切片，待定）
│   └── [ ][X+] 1-5-4. Gatekeeper / XProtect 用户体验兜底（自用启动说明已入 README）
├── [ ][X+] 1-6. 文档治理收尾
│   ├── [ ][X+] 1-6-1. docs/plans 退役态处置（计划草稿 + 旧 roadmap 删 / 留，需 zj 拍板）
│   ├── [ ][X+] 1-6-2. 结论沉淀核对（ADR 0015/0016 + designs 三篇覆盖度）
│   └── [ ][X+] 1-6-3. app/README 陈旧表述订正（LLM stub / Python sidecar / MemStore）
└── [ ][X+] 1-7. 产品定位复核（R4 风险：ES 内容是否稀释 ZW 编码证据核心）

### 下一步可开工（ready 前 3）

- 1-4. 证据核心 B2 补齐（对齐 Python CompositionOwner 能力面） [ ]
- 1-4-1. reconcile / uncertain 恢复路径 [ ]
- 1-4-2. backup / restore [ ]
<!-- ROADMAP_SECTION_END -->
