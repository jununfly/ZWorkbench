import { useEffect, useState } from 'react';
import { getJSON } from '../api';

interface Figure { name: string; school: string; tenet: string; insight: string; }
interface Library { as_of: string; source: string; fallback: boolean; figures: Figure[]; }

const RED = '#cf1322';

export function MasteryTab() {
  const [data, setData] = useState<Library | null>(null);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    getJSON('/api/mastery')
      .then((d: Library) => setData(d))
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <pre style={{ color: RED }}>{err}</pre>;
  if (!data) return <p>加载游资心法…</p>;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>游资心法与 AI Copilot</h2>
        <span style={{ fontSize: 12, color: '#888' }}>
          来源 {data.source}{data.fallback && <span style={{ color: '#d46b08' }}>（回退）</span>}{' · '}{data.as_of}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
        {data.figures.map((f) => (
          <div key={f.name} style={{ border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <b>{f.name}</b>
              <span style={{ background: '#fff7e6', color: '#d46b08', fontSize: 12, padding: '2px 8px', borderRadius: 10 }}>{f.school}</span>
            </div>
            <div style={{ marginTop: 8, fontSize: 13 }}><b>心法：</b>{f.tenet}</div>
            <div style={{ marginTop: 4, fontSize: 13, color: '#555' }}><b>解读：</b>{f.insight}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
