import { useEffect, useState } from 'react';
import { getJSON } from '../api';
import { SourceStatusBanner } from '../SourceStatusBanner';

interface AuthorView { name: string; view: string; date: string; }
interface Review { as_of: string; source: string; fallback: boolean; status?: string; reason?: string; consensus: string; divergence: string; facts: string; next_verify: string; authors: AuthorView[]; }

const RED = '#cf1322';

export function ReviewTab() {
  const [data, setData] = useState<Review | null>(null);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    getJSON('/api/stock/review')
      .then((d: Review) => setData(d))
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <pre style={{ color: RED }}>{err}</pre>;
  if (!data) return <p>加载大V自动复盘…</p>;

  const block = (title: string, body: string, color?: string) => (
    <section style={{ marginTop: 16, border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      <div style={{ fontSize: 13, lineHeight: 1.7, color: color || '#333', whiteSpace: 'pre-wrap' }}>{body}</div>
    </section>
  );

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <SourceStatusBanner source={data.source} fallback={data.fallback} status={data.status} reason={data.reason} asOf={data.as_of} />
      </div>

      {block('今日观点共识', data.consensus)}
      {block('主要分歧', data.divergence, '#d46b08')}
      {block('盘面事实', data.facts)}
      {block('次日验证条件', data.next_verify, '#2f54eb')}

      <section style={{ marginTop: 16 }}>
        <h3>作者观点</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {data.authors.map((a) => (
            <div key={a.name} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: '8px 10px' }}>
              <div style={{ fontSize: 13 }}><b>{a.name}</b> <span style={{ color: '#aaa' }}>{a.date}</span></div>
              <div style={{ fontSize: 13, color: '#555', marginTop: 4 }}>{a.view}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
