// 通用占位屏：项目 / 统计 / 日志 本轮不实现真实内容。
export function PlaceholderScreen({ title, hint }: { title: string; hint: string }) {
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 500, margin: '0 0 8px' }}>{title}</h1>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
          height: '50vh',
          color: 'var(--zw-on-surface-variant)',
        }}
      >
        <div
          style={{ width: 64, height: 64, borderRadius: '50%', border: '3px dashed var(--zw-surface-variant)' }}
        />
        <div className="zw-muted">{hint}</div>
      </div>
    </div>
  );
}
