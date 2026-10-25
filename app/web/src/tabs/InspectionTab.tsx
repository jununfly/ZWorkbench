import { useEffect, useState } from 'react';
import { getJSON } from '../api';
import { SourceStatusBanner } from '../SourceStatusBanner';

interface Holding { code: string; name: string; weight: number; cost: number; price: number; pnl_pct: number; }
interface Dimension { name: string; weight: number; score: number; basis: string; }
interface Report { as_of: string; source: string; fallback: boolean; status?: string; reason?: string; total_assets: number; cash: number; pnl: number; risk_level: string; score: number; dimensions: Dimension[]; holdings: Holding[]; }

const RED = '#cf1322';
const GREEN = '#3f8600';
function pctColor(p: number): string { return p > 0 ? RED : p < 0 ? GREEN : '#888'; }
function fmtPct(p: number): string { return (p > 0 ? '+' : '') + p.toFixed(2) + '%'; }
function money(n: number): string { return '¥' + n.toLocaleString('zh-CN'); }

export function InspectionTab() {
  const [data, setData] = useState<Report | null>(null);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    getJSON('/api/portfolio/inspection')
      .then((d: Report) => setData(d))
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <pre style={{ color: RED }}>{err}</pre>;
  if (!data) return <p>加载持仓AI巡检…</p>;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <SourceStatusBanner source={data.source} fallback={data.fallback} status={data.status} reason={data.reason} asOf={data.as_of} />
      </div>

      <section style={{ marginTop: 16, display: 'flex', gap: 20, fontSize: 14, border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
        <span>总资产 <b>{money(data.total_assets)}</b></span>
        <span>现金 <b>{money(data.cash)}</b></span>
        <span>盈亏 <b style={{ color: pctColor(data.pnl) }}>{money(data.pnl)}</b></span>
        <span>综合评分 <b style={{ color: '#2f54eb' }}>{data.score}</b></span>
        <span>风险 <b>{data.risk_level}</b></span>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>四维评分</h3>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#888' }}>
              <th style={{ padding: '4px 6px' }}>维度</th><th style={{ padding: '4px 6px' }}>权重</th><th style={{ padding: '4px 6px' }}>评分</th><th style={{ padding: '4px 6px' }}>依据</th>
            </tr>
          </thead>
          <tbody>
            {data.dimensions.map((d) => (
              <tr key={d.name} style={{ borderTop: '1px solid #f0f0f0' }}>
                <td style={{ padding: '4px 6px' }}>{d.name}</td>
                <td style={{ padding: '4px 6px' }}>{d.weight}%</td>
                <td style={{ padding: '4px 6px' }}><b>{d.score}</b></td>
                <td style={{ padding: '4px 6px', color: '#888' }}>{d.basis}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>持仓明细</h3>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#888' }}>
              <th style={{ padding: '4px 6px' }}>名称</th><th style={{ padding: '4px 6px' }}>仓位</th><th style={{ padding: '4px 6px' }}>成本</th><th style={{ padding: '4px 6px' }}>现价</th><th style={{ padding: '4px 6px' }}>盈亏</th>
            </tr>
          </thead>
          <tbody>
            {data.holdings.map((h) => (
              <tr key={h.code} style={{ borderTop: '1px solid #f0f0f0' }}>
                <td style={{ padding: '4px 6px' }}>{h.name} <span style={{ color: '#aaa' }}>{h.code}</span></td>
                <td style={{ padding: '4px 6px' }}>{h.weight}%</td>
                <td style={{ padding: '4px 6px' }}>{h.cost.toFixed(2)}</td>
                <td style={{ padding: '4px 6px' }}>{h.price.toFixed(2)}</td>
                <td style={{ padding: '4px 6px', color: pctColor(h.pnl_pct), fontWeight: 600 }}>{fmtPct(h.pnl_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
