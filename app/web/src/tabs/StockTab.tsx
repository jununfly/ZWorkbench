import { useEffect, useState } from 'react';
import { getJSON } from '../api';
import { SourceStatusBanner } from '../SourceStatusBanner';

interface Index { name: string; code: string; value: number; change_pct: number; }
interface StockQuote { code: string; name: string; price: number; change_pct: number; }
interface Sector { name: string; change_pct: number; leading: string; }
interface Breadth { up: number; down: number; flat: number; limit_up: number; limit_down: number; }
interface Overview {
  as_of: string; source: string; fallback: boolean;
  status?: string; reason?: string; // roadmap 1-2-5 语义状态
  indices: Index[]; breadth: Breadth;
  top_gainers: StockQuote[]; top_losers: StockQuote[]; sectors: Sector[];
}

// 中国股市约定：涨=红，跌=绿。
function pctColor(p: number): string {
  if (p > 0) return '#cf1322';
  if (p < 0) return '#3f8600';
  return '#888';
}
function fmtPct(p: number): string { return (p > 0 ? '+' : '') + p.toFixed(2) + '%'; }

export function StockTab() {
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    getJSON('/api/stock/overview')
      .then((d: Overview) => setData(d))
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <pre style={{ color: '#cf1322' }}>{err}</pre>;
  if (!data) return <p>加载行情总览…</p>;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>行情总览</h2>
        <SourceStatusBanner source={data.source} fallback={data.fallback} status={data.status} reason={data.reason} asOf={data.as_of} />
      </div>

      <section style={{ marginTop: 16 }}>
        <h3>指数</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
          {data.indices.map((x) => (
            <div key={x.code} style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
              <div style={{ fontSize: 13, color: '#555' }}>{x.name}</div>
              <div style={{ fontSize: 20, fontWeight: 600 }}>{x.value.toFixed(2)}</div>
              <div style={{ color: pctColor(x.change_pct), fontWeight: 600 }}>{fmtPct(x.change_pct)}</div>
            </div>
          ))}
        </div>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>市场宽度</h3>
        <div style={{ fontSize: 14 }}>
          上涨 <b style={{ color: '#cf1322' }}>{data.breadth.up}</b>
          {' · '}下跌 <b style={{ color: '#3f8600' }}>{data.breadth.down}</b>
          {' · '}平 {data.breadth.flat}
          {' · '}涨停 <b style={{ color: '#cf1322' }}>{data.breadth.limit_up}</b>
          {' · '}跌停 <b style={{ color: '#3f8600' }}>{data.breadth.limit_down}</b>
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        <section>
          <h3>涨幅榜</h3>
          <QuoteTable rows={data.top_gainers} />
        </section>
        <section>
          <h3>跌幅榜</h3>
          <QuoteTable rows={data.top_losers} />
        </section>
      </div>

      <section style={{ marginTop: 16 }}>
        <h3>板块</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {data.sectors.map((s) => (
            <div key={s.name} style={{ border: '1px solid #eee', borderRadius: 16, padding: '6px 12px', fontSize: 13 }}>
              <span>{s.name}</span>
              {' '}<span style={{ color: pctColor(s.change_pct), fontWeight: 600 }}>{fmtPct(s.change_pct)}</span>
              {' '}<span style={{ color: '#aaa' }}>领：{s.leading}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function QuoteTable({ rows }: { rows: StockQuote[] }) {
  return (
    <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ textAlign: 'left', color: '#888' }}>
          <th style={{ padding: '4px 6px' }}>名称</th>
          <th style={{ padding: '4px 6px' }}>价</th>
          <th style={{ padding: '4px 6px' }}>涨跌幅</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.code} style={{ borderTop: '1px solid #f0f0f0' }}>
            <td style={{ padding: '4px 6px' }}>{r.name}</td>
            <td style={{ padding: '4px 6px' }}>{r.price.toFixed(2)}</td>
            <td style={{ padding: '4px 6px', color: pctColor(r.change_pct), fontWeight: 600 }}>{fmtPct(r.change_pct)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
