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

// ---- 身份链（1-4-4）：run → attempt → effect → approval ----
interface ChainAttempt {
  attempt_id: number;
  effect_id: string;
  attempt: number;
  status: string;
  started_at: string;
  finished_at?: string;
}
interface ChainApproval {
  approval_id: string;
  operation_id: string;
  action: string;
  resource: string;
  status: string;
}
interface ChainEffect {
  effect_id: string;
  operation_id: string;
  effect_class: string;
  action: string;
  resource: string;
  status: string;
  attempt: number;
  max_attempts: number;
  physical_effect_count: number;
  approval_id?: string;
  approval_link: string; // linked | unlinked | dangling
  approval?: ChainApproval;
  attempts: ChainAttempt[];
}
interface IdentityChain {
  run_id: string;
  entry: { kind: string; id: string; detail?: string };
  effects: ChainEffect[];
  approvals: ChainApproval[];
  counts: {
    effects: number;
    attempts: number;
    approvals: number;
    physical_effects: number;
    dangling_links: number;
  };
}

const LINK_COLOR: Record<string, string> = {
  linked: '#389e0d',
  unlinked: '#595959',
  dangling: RED,
};

interface EvViolation {
  kind: string;
  run_id: string;
  ref_table: string;
  ref_id: string;
  detail: string;
}

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
  const [chain, setChain] = useState<IdentityChain | null>(null);
  const [chainErr, setChainErr] = useState<string>('');
  const [violations, setViolations] = useState<EvViolation[]>([]);
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
      setViolations(Array.isArray(v) ? v : []);
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
    // 身份链独立取数：链查询失败不该把整个详情面板打黑（但必须显出来，不能静默空白）。
    try {
      const c = await getJSON(
        `/api/evidence/identity-chain?run_id=${encodeURIComponent(id)}`
      );
      setChain(c);
      setChainErr('');
    } catch (e) {
      setChain(null);
      setChainErr(String(e));
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

  // 1-4-5：扫身份图，有未解析引用才 safe-stop（健康 run 不动）。
  const safeStopOnViolation = () =>
    act(() =>
      reqJSON('POST', `/api/evidence/runs/${encodeURIComponent(selected)}/safe-stop-on-violation`, {})
    );

  // 1-4-5：身份收口决策（safe_stopped 是终态，收口成功也不复活）。
  const reconcileIdentity = () =>
    act(() =>
      reqJSON('POST', `/api/evidence/runs/${encodeURIComponent(selected)}/reconcile-identity`, {})
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
            background: violations.length > 0 ? RED : '#f0f0f0',
            color: violations.length > 0 ? '#fff' : '#888',
          }}
        >
          identity violations: {violations.length}
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
              <button
                onClick={() => void safeStopOnViolation()}
                disabled={busy || !selected}
                title="扫身份图：有未解析引用才 safe-stop，健康 run 不动"
              >
                safe-stop on violation
              </button>
              <button
                onClick={() => void reconcileIdentity()}
                disabled={busy || !selected}
                title="记录身份收口决策；safe_stopped 是终态，收口成功也不复活"
              >
                reconcile identity
              </button>
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
        <h3 style={{ marginBottom: 6 }}>
          身份链 <span style={{ fontSize: 12, color: '#888' }}>run → attempt → effect → approval</span>
        </h3>
        {!selected && <p style={{ color: '#888', fontSize: 13 }}>选中左侧 run 查看其身份链。</p>}
        {chainErr && <pre style={{ color: RED, fontSize: 12 }}>{chainErr}</pre>}
        {chain && (
          <>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
              <code>{chain.run_id}</code> · entry={chain.entry.kind} · effects={chain.counts.effects}
              {' · '}attempts={chain.counts.attempts} · approvals={chain.counts.approvals}
              {' · '}physical={chain.counts.physical_effects}
              {chain.counts.dangling_links > 0 && (
                <span style={{ color: RED }}>
                  {' '}
                  · dangling={chain.counts.dangling_links}
                </span>
              )}
            </div>

            {chain.effects.length === 0 && (
              <p style={{ color: '#888', fontSize: 13 }}>
                该 run 尚无 effect（链上只有 run 本身）。
              </p>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {chain.effects.map((fx) => (
                <div
                  key={fx.effect_id}
                  style={{
                    border: '1px solid #f0f0f0',
                    borderRadius: 6,
                    padding: '8px 10px',
                    fontSize: 12,
                  }}
                >
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <code>{fx.effect_id}</code>
                    {badge(fx.status)}
                    <span style={{ color: '#888' }}>
                      {fx.effect_class} · {fx.action} {fx.resource}
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        padding: '2px 8px',
                        borderRadius: 10,
                        background: '#fafafa',
                        color: LINK_COLOR[fx.approval_link] ?? '#595959',
                      }}
                    >
                      approval: {fx.approval_link}
                    </span>
                  </div>

                  <div style={{ marginTop: 6, color: '#555' }}>
                    attempts {fx.attempt}/{fx.max_attempts} · physical={fx.physical_effect_count}
                  </div>

                  <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {fx.attempts.map((a) => (
                      <div key={a.attempt_id} style={{ fontFamily: 'ui-monospace, monospace' }}>
                        #{a.attempt} <b>{a.status}</b>{' '}
                        <span style={{ color: '#aaa' }}>
                          {a.started_at}
                          {a.finished_at ? ` → ${a.finished_at}` : ''}
                        </span>
                      </div>
                    ))}
                  </div>

                  {fx.approval && (
                    <div style={{ marginTop: 4, color: '#555' }}>
                      approval <code>{fx.approval.approval_id}</code> {badge(fx.approval.status)} op=
                      {fx.approval.operation_id}
                    </div>
                  )}
                  {fx.approval_link === 'dangling' && (
                    <div style={{ marginTop: 4, color: RED }}>
                      断链：approval_id={fx.approval_id} 在 owner 里不存在（不自动补洞）
                    </div>
                  )}
                </div>
              ))}
            </div>

            {chain.approvals.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 12, color: '#888' }}>run 级审批（含未被 effect 认领的）</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                  {chain.approvals.map((a) => (
                    <span key={a.approval_id} style={{ fontSize: 11 }}>
                      <code>{a.approval_id.slice(0, 8)}</code> {badge(a.status)}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </section>

      <section style={{ marginTop: 20 }}>
        <h3 style={{ marginBottom: 6 }}>
          身份违例{' '}
          <span style={{ fontSize: 12, color: '#888' }}>owner 全量审计 · {violations.length} 条</span>
        </h3>
        {violations.length === 0 ? (
          <p style={{ color: '#888', fontSize: 13 }}>身份图无未解析引用。</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {violations.map((v, i) => (
              <div
                key={`${v.kind}-${v.ref_id}-${i}`}
                style={{
                  borderLeft: '3px solid ' + RED,
                  paddingLeft: 8,
                  fontSize: 12,
                  fontFamily: 'ui-monospace, monospace',
                }}
              >
                <b>{v.kind}</b>{' '}
                <span style={{ color: '#aaa' }}>
                  {v.ref_table} · {v.ref_id}
                  {v.run_id && v.run_id !== v.ref_id ? ` · run=${v.run_id}` : ''}
                </span>
                <div style={{ color: '#555' }}>{v.detail}</div>
              </div>
            ))}
          </div>
        )}
      </section>

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
