import { useCallback, useEffect, useState } from 'react';
import { getJSON, reqJSON } from '../api';

interface EvEvent {
  seq: number;
  event_id: string;
  run_id: string;
  type: string;
  payload?: Record<string, any>;
  evidence_source?: string;
  created_at: string;
}
interface EvRun {
  run_id: string;
  task_type: string;
  status: string;
  created_at: string;
  updated_at: string;
  events?: EvEvent[];
}

const RED = '#cf1322';

// 生命周期 7 状态的语义配色：终态可辨、safe_stopped 最醒目（C28 是差异化核心）。
const STATUS_COLOR: Record<string, string> = {
  created: '#595959',
  running: '#2f54eb',
  waiting_approval: '#d46b08',
  recovering: '#722ed1',
  completed: '#389e0d',
  failed: RED,
  safe_stopped: '#d4380d',
};

const ACTIONS = ['start', 'complete', 'fail', 'safe_stop', 'recover'];

const badge = (status: string) => (
  <span
    style={{
      fontSize: 11,
      padding: '2px 8px',
      borderRadius: 10,
      color: '#fff',
      background: STATUS_COLOR[status] ?? '#595959',
    }}
  >
    {status}
  </span>
);

export function CodingEvidenceTab() {
  const [runs, setRuns] = useState<EvRun[]>([]);
  const [stream, setStream] = useState<EvEvent[]>([]);
  const [detail, setDetail] = useState<EvRun | null>(null);
  const [violations, setViolations] = useState<number>(0);
  const [selected, setSelected] = useState<string>('');
  const [err, setErr] = useState<string>('');
  const [busy, setBusy] = useState<boolean>(false);

  const load = useCallback(async () => {
    try {
      const [r, s, v] = await Promise.all([
        getJSON('/api/evidence/runs'),
        getJSON('/api/evidence/events?type=run.safe_stopped&limit=50'),
        getJSON('/api/evidence/violations'),
      ]);
      setRuns(r ?? []);
      setStream(s ?? []);
      setViolations(Array.isArray(v) ? v.length : 0);
      setErr('');
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  const selectRun = useCallback(async (id: string) => {
    setSelected(id);
    try {
      const d = await getJSON(`/api/evidence/runs/${encodeURIComponent(id)}`);
      setDetail(d);
      setErr('');
    } catch (e) {
      setErr(String(e));
      setDetail(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 选中项随刷新更新投影，避免停留在过期快照上。
  useEffect(() => {
    if (selected) void selectRun(selected);
  }, [runs, selected, selectRun]);

  const act = async (fn: () => Promise<any>) => {
    setBusy(true);
    try {
      await fn();
      await load();
      if (selected) await selectRun(selected);
      setErr('');
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const createRun = () =>
    act(() => reqJSON('POST', '/api/evidence/runs', { task_type: 'manual-ui' }));

  const transition = (action: string) =>
    act(() =>
      reqJSON('POST', `/api/evidence/runs/${encodeURIComponent(selected)}/transition`, {
        action,
        reason: action === 'safe_stop' || action === 'recover' ? `ui-${action}` : undefined,
      })
    );

  if (err && runs.length === 0 && !detail) {
    return <pre style={{ color: RED }}>{err}</pre>;
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>编码证据</h2>
        <span style={{ fontSize: 12, color: '#888' }}>
          CompositionOwner 生命周期 · {runs.length} 个 run
        </span>
        <span
          style={{
            fontSize: 11,
            padding: '2px 8px',
            borderRadius: 10,
            background: violations > 0 ? RED : '#f0f0f0',
            color: violations > 0 ? '#fff' : '#888',
          }}
        >
          identity violations: {violations}
        </span>
        <button onClick={() => void load()} disabled={busy}>
          刷新
        </button>
        <button onClick={() => void createRun()} disabled={busy}>
          新建 run
        </button>
      </div>

      {err && <pre style={{ color: RED, marginTop: 8 }}>{err}</pre>}

      <div style={{ display: 'flex', gap: 16, marginTop: 16, alignItems: 'flex-start' }}>
        <section style={{ width: 320, flexShrink: 0 }}>
          <h3 style={{ marginTop: 0 }}>Runs</h3>
          {runs.length === 0 && (
            <p style={{ color: '#888', fontSize: 13 }}>
              暂无 run（默认内存库，重启即空）。点「新建 run」造一条看生命周期。
            </p>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {runs.map((r) => (
              <div
                key={r.run_id}
                onClick={() => void selectRun(r.run_id)}
                style={{
                  border: '1px solid ' + (selected === r.run_id ? '#2f54eb' : '#f0f0f0'),
                  borderRadius: 6,
                  padding: '8px 10px',
                  cursor: 'pointer',
                  background: selected === r.run_id ? '#f5f8ff' : '#fff',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <code style={{ fontSize: 12 }}>{r.run_id}</code>
                  {badge(r.status)}
                </div>
                <div style={{ fontSize: 11, color: '#aaa', marginTop: 4 }}>
                  {r.task_type} · {r.created_at}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ marginTop: 0 }}>
            事件流 {detail ? <code style={{ fontSize: 13 }}>{detail.run_id}</code> : '（未选中）'}
          </h3>
          {detail && (
            <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
              {ACTIONS.map((a) => (
                <button key={a} onClick={() => void transition(a)} disabled={busy || !selected}>
                  {a}
                </button>
              ))}
            </div>
          )}
          {!detail && <p style={{ color: '#888', fontSize: 13 }}>选中左侧 run 查看其事件流。</p>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {(detail?.events ?? []).map((e) => (
              <div
                key={e.event_id}
                style={{
                  borderLeft:
                    '3px solid ' + (e.type === 'run.safe_stopped' ? '#d4380d' : '#ddd'),
                  paddingLeft: 8,
                  fontSize: 12,
                  fontFamily: 'ui-monospace, monospace',
                }}
              >
                <b>{e.type}</b>{' '}
                <span style={{ color: '#aaa' }}>
                  #{e.seq} · {e.created_at}
                  {e.evidence_source ? ` · ${e.evidence_source}` : ''}
                </span>
                {e.payload && Object.keys(e.payload).length > 0 && (
                  <div style={{ color: '#555' }}>{JSON.stringify(e.payload)}</div>
                )}
              </div>
            ))}
          </div>
        </section>
      </div>

      <section style={{ marginTop: 20 }}>
        <h3>全局 safe-stop 事件流（C28）</h3>
        {stream.length === 0 ? (
          <p style={{ color: '#888', fontSize: 13 }}>暂无安全停止事件。</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {stream.map((e) => (
              <div
                key={e.event_id}
                style={{
                  borderLeft: '3px solid #d4380d',
                  paddingLeft: 8,
                  fontSize: 12,
                  fontFamily: 'ui-monospace, monospace',
                }}
              >
                <code>{e.run_id}</code>{' '}
                <span style={{ color: '#aaa' }}>
                  #{e.seq} · {e.created_at}
                </span>
                {e.payload && <div style={{ color: '#555' }}>{JSON.stringify(e.payload)}</div>}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
