import { useEffect, useState } from 'react';
import { getJSON } from '../api';

interface ResearchStock { code: string; name: string; price: number; change_pct: number; purpose: string; cycle: string; core: string; support: string; against: string; }
interface Research { as_of: string; source: string; fallback: boolean; stocks: ResearchStock[]; }

const RED = '#cf1322';
const GREEN = '#3f8600';
function pctColor(p: number): string { return p > 0 ? RED : p < 0 ? GREEN : '#888'; }
function fmtPct(p: number): string { return (p > 0 ? '+' : '') + p.toFixed(2) + '%'; }

export function ResearchTab() {
  const [data, setData] = useState<Research | null>(null);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    getJSON('/api/stock/research')
      .then((d: Research) => setData(d))
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <pre style={{ color: RED }}>{err}</pre>;
  if (!data) return <p>加载个股分级研究…</p>;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>个股分级研究</h2>
        <span style={{ fontSize: 12, color: '#888' }}>
          来源 {data.source}{data.fallback && <span style={{ color: '#d46b08' }}>（回退）</span>}{' · '}{data.as_of}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
        {data.stocks.map((s) => (
          <div key={s.code} style={{ border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <b>{s.name}</b><span style={{ color: '#aaa' }}>{s.code}</span>
              <span style={{ color: pctColor(s.change_pct), fontWeight: 600 }}>{fmtPct(s.change_pct)}</span>
              <span style={{ marginLeft: 'auto', fontSize: 12 }}>
                <span style={{ background: '#f0f5ff', color: '#2f54eb', padding: '2px 8px', borderRadius: 10, marginRight: 6 }}>{s.purpose}</span>
                <span style={{ background: '#f6ffed', color: '#389e0d', padding: '2px 8px', borderRadius: 10 }}>{s.cycle}</span>
              </span>
            </div>
            <div style={{ marginTop: 8, fontSize: 13 }}>
              <div><b>核心判断：</b>{s.core}</div>
              <div style={{ color: GREEN, marginTop: 4 }}><b>支持：</b>{s.support}</div>
              <div style={{ color: RED, marginTop: 4 }}><b>反对：</b>{s.against}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
