import { useEffect, useState } from 'react';
import { getJSON } from '../api';
import { SourceStatusBanner } from '../SourceStatusBanner';

interface LimitUpStock { code: string; name: string; price: number; change_pct: number; reason: string; }
interface Tier { days: number; stocks: LimitUpStock[]; }
interface Theme { name: string; limit_up_count: number; strength: number; leading: string; }
interface Sentiment { stage: string; max_board: number; limit_up: number; limit_down: number; }
interface Board {
  as_of: string; source: string; fallback: boolean;
  status?: string; reason?: string; // roadmap 1-2-5 语义状态
  tiers: Tier[]; themes: Theme[]; sentiment: Sentiment;
}

// 中国股市约定：涨=红，跌=绿。
function pctColor(p: number): string {
  if (p > 0) return '#cf1322';
  if (p < 0) return '#3f8600';
  return '#888';
}
function fmtPct(p: number): string { return (p > 0 ? '+' : '') + p.toFixed(2) + '%'; }
const RED = '#cf1322';
const GREEN = '#3f8600';

export function LimitUpTab() {
  const [data, setData] = useState<Board | null>(null);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    getJSON('/api/stock/limitup')
      .then((d: Board) => setData(d))
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <pre style={{ color: RED }}>{err}</pre>;
  if (!data) return <p>加载连板看板…</p>;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>超短连板 / 题材 / 情绪</h2>
        <SourceStatusBanner source={data.source} fallback={data.fallback} status={data.status} reason={data.reason} asOf={data.as_of} />
      </div>

      {/* 情绪周期条 */}
      <section style={{ marginTop: 16, border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
        <h3 style={{ marginTop: 0 }}>情绪周期</h3>
        <div style={{ display: 'flex', gap: 20, fontSize: 14 }}>
          <span>阶段 <b>{data.sentiment.stage}</b></span>
          <span>最高板 <b style={{ color: RED }}>{data.sentiment.max_board} 板</b></span>
          <span>涨停 <b style={{ color: RED }}>{data.sentiment.limit_up}</b></span>
          <span>跌停 <b style={{ color: GREEN }}>{data.sentiment.limit_down}</b></span>
        </div>
      </section>

      {/* 连板梯队 */}
      <section style={{ marginTop: 16 }}>
        <h3>连板梯队</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {data.tiers.map((t) => (
            <div key={t.days} style={{ border: '1px solid #eee', borderRadius: 8, padding: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                {t.days === 1 ? '首板' : t.days + ' 板'} <span style={{ color: '#aaa', fontSize: 12 }}>({t.stocks.length})</span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {t.stocks.map((s) => (
                  <div key={s.code} style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: '6px 10px', minWidth: 150 }}>
                    <div style={{ fontSize: 13 }}>
                      <b>{s.name}</b> <span style={{ color: '#aaa' }}>{s.code}</span>
                    </div>
                    <div style={{ fontSize: 13, color: pctColor(s.change_pct), fontWeight: 600 }}>{fmtPct(s.change_pct)}</div>
                    <div style={{ fontSize: 12, color: '#888' }}>题材：{s.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 题材雷达 */}
      <section style={{ marginTop: 16 }}>
        <h3>题材雷达</h3>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#888' }}>
              <th style={{ padding: '4px 6px' }}>题材</th>
              <th style={{ padding: '4px 6px' }}>涨停数</th>
              <th style={{ padding: '4px 6px' }}>强度</th>
              <th style={{ padding: '4px 6px' }}>龙头</th>
            </tr>
          </thead>
          <tbody>
            {data.themes.map((th) => (
              <tr key={th.name} style={{ borderTop: '1px solid #f0f0f0' }}>
                <td style={{ padding: '4px 6px' }}>{th.name}</td>
                <td style={{ padding: '4px 6px' }}>{th.limit_up_count}</td>
                <td style={{ padding: '4px 6px' }}>
                  <span style={{ color: pctColor(th.strength - 60), fontWeight: 600 }}>{th.strength.toFixed(1)}</span>
                </td>
                <td style={{ padding: '4px 6px' }}>{th.leading}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
