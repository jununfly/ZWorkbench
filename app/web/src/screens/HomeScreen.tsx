// 首页：个人综合工作台总入口（本轮为概览占位，后续填真实 dashboard）。
export function HomeScreen() {
  const cards = [
    { title: '工作台', desc: '对话 + 编码证据（非交易自治能力）' },
    { title: 'A股投研', desc: '行情 / 研究 / 连板 / 复盘 / 持仓 / 优化 / 心法' },
    { title: '设置', desc: '通用 + LLM Provider 配置' },
  ];
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 500, margin: '0 0 8px' }}>首页</h1>
      <p className="zw-muted" style={{ marginBottom: 24 }}>
        个人综合工作台总入口（本轮占位）
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
        {cards.map((c) => (
          <div key={c.title} className="zw-card">
            <h3>{c.title}</h3>
            <p className="zw-muted" style={{ margin: 0 }}>
              {c.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
