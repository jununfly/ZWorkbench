import { useEffect, useState } from 'react';
import { getJSON } from '../api';

interface Target { code: string; name: string; action: string; from_weight: number; to_weight: number; reason: string; }
interface Plan { as_of: string; source: string; fallback: boolean; original_score: number; optimized_score: number; improvement: number; targets: Target[]; conditions: string; }

const RED = '#cf1322';
const GREEN = '#3f8600';

function actionColor(a: string): string {
  if (a === '新增') return GREEN;
  if (a === '减持') return RED;
  return '#888';
}

export function OptimizationTab() {
  const [data, setData] = useState<Plan | null>(null);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    getJSON('/api/portfolio/optimization')
      .then((d: Plan) => setData(d))
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <pre style={{ color: RED }}>{err}</pre>;
  if (!data) return <p>加载AI持仓优化…</p>;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>AI持仓优化</h2>
        <span style={{ fontSize: 12, color: '#888' }}>
          来源 {data.source}{data.fallback && <span style={{ color: '#d46b08' }}>（回退）</span>}{' · '}{data.as_of}
        </span>
      </div>

      <section style={{ marginTop: 16, display: 'flex', gap: 20, fontSize: 14, border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
        <span>原评分 <b>{data.original_score}</b></span>
        <span>优化评分 <b style={{ color: '#2f54eb' }}>{data.optimized_score}</b></span>
        <span>改善 <b style={{ color: GREEN }}>+{data.improvement}</b></span>
      </section>

      <section style={{ marginTop: 16 }}>
        <h3>目标组合对照</h3>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: '#888' }}>
              <th style={{ padding: '4px 6px' }}>名称</th><th style={{ padding: '4px 6px' }}>动作</th><th style={{ padding: '4px 6px' }}>原仓位</th><th style={{ padding: '4px 6px' }}>目标仓位</th><th style={{ padding: '4px 6px' }}>理由</th>
            </tr>
          </thead>
          <tbody>
            {data.targets.map((t) => (
              <tr key={t.code} style={{ borderTop: '1px solid #f0f0f0' }}>
                <td style={{ padding: '4px 6px' }}>{t.name} <span style={{ color: '#aaa' }}>{t.code}</span></td>
                <td style={{ padding: '4px 6px' }}><b style={{ color: actionColor(t.action) }}>{t.action}</b></td>
                <td style={{ padding: '4px 6px' }}>{t.from_weight}%</td>
                <td style={{ padding: '4px 6px' }}>{t.to_weight}%</td>
                <td style={{ padding: '4px 6px', color: '#888' }}>{t.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section style={{ marginTop: 16, border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
        <h3 style={{ marginTop: 0 }}>入场 / 退出条件</h3>
        <div style={{ fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap', color: '#2f54eb' }}>{data.conditions}</div>
      </section>
    </div>
  );
}
