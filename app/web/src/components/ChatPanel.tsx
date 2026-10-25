import { useState } from 'react';
import { reqJSON } from '../api';

interface Turn {
  role: string;
  content: string;
}
interface Conversation {
  id: string;
  title: string;
  archived: boolean;
  messages: Turn[];
}

// 会话种子（内存态，刷新即重置；发送接真实 /api/agent/chat）。
const SEED: Conversation[] = [
  {
    id: 'c1',
    title: 'ZW 重构讨论',
    archived: false,
    messages: [
      { role: 'assistant', content: '你好，我是 ZW 的 LLM 助手。' },
      { role: 'user', content: '把工作台-对话重做成双栏' },
      { role: 'assistant', content: '已按你的布局更新：左栏为对话历史，切换会话即切换右侧内容。' },
    ],
  },
  { id: 'c2', title: 'A股复盘问答', archived: false, messages: [{ role: 'assistant', content: '关于 A股复盘，你想看哪个方向？' }] },
  { id: 'c3', title: '编码证据疑问', archived: false, messages: [{ role: 'assistant', content: '编码证据是 CompositionOwner 证据核心，记录 run→attempt→effect→approval 身份链。' }] },
  { id: 'c4', title: '主题色方案', archived: false, messages: [{ role: 'user', content: '主题色选哪个方向卡？' }, { role: 'assistant', content: '你选了 card-e Material Design 3（动态紫 #6750A4）。' }] },
  { id: 'c5', title: '部署问题排查', archived: false, messages: [{ role: 'assistant', content: '部署问题请描述现象与日志路径。' }] },
];

type MenuState = { x: number; y: number; id: string } | null;

export function ChatPanel() {
  const [convs, setConvs] = useState<Conversation[]>(SEED);
  const [activeId, setActiveId] = useState<string>('c1');
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [menu, setMenu] = useState<MenuState>(null);

  const active = convs.find((c) => c.id === activeId) ?? convs[0] ?? null;

  function select(id: string) {
    setActiveId(id);
    setMenu(null);
  }

  function updateConv(id: string, messages: Turn[]) {
    setConvs((cs) => cs.map((c) => (c.id === id ? { ...c, messages } : c)));
  }

  async function send() {
    const text = input.trim();
    if (!text || busy || !active) return;
    const next: Turn[] = [...active.messages, { role: 'user', content: text }];
    updateConv(active.id, next);
    setInput('');
    setBusy(true);
    setErr('');
    try {
      const r = await reqJSON('POST', '/api/agent/chat', {
        messages: next.map((m) => ({ role: m.role, content: m.content })),
      });
      updateConv(active.id, [...next, { role: 'assistant', content: r.content }]);
    } catch (e) {
      setErr('调用失败：' + e);
    } finally {
      setBusy(false);
    }
  }

  function doMenuAction(act: string) {
    if (!menu) return;
    const target = convs.find((c) => c.id === menu.id);
    if (act === 'delete') {
      const remaining = convs.filter((c) => c.id !== menu.id);
      setConvs(remaining);
      if (activeId === menu.id) setActiveId(remaining[0]?.id ?? '');
    } else if (act === 'archive') {
      setConvs((cs) => cs.map((c) => (c.id === menu.id ? { ...c, archived: true } : c)));
    } else {
      window.alert('已生成分享链接（预览）：' + (target?.title ?? ''));
    }
    setMenu(null);
  }

  if (convs.length === 0) {
    return <p className="zw-muted">暂无对话。</p>;
  }

  return (
    <div style={{ display: 'flex', gap: 16, height: '64vh' }}>
      <aside
        style={{
          width: 220,
          flex: '0 0 220px',
          border: '0.5px solid var(--zw-surface-variant)',
          borderRadius: 16,
          padding: 12,
          overflowY: 'auto',
        }}
      >
        <div style={{ fontSize: 13, color: 'var(--zw-on-surface-variant)', fontWeight: 500, padding: '8px 12px', marginBottom: 8 }}>
          对话历史
        </div>
        {convs.map((c) => (
          <div
            key={c.id}
            role="button"
            tabIndex={0}
            className={'zw-navitem zw-subitem' + (c.id === activeId ? ' active' : '')}
            style={{ opacity: c.archived ? 0.5 : 1, cursor: 'pointer' }}
            onClick={() => select(c.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                select(c.id);
              }
            }}
            onContextMenu={(e) => {
              e.preventDefault();
              setMenu({ x: e.clientX, y: e.clientY, id: c.id });
            }}
          >
            {c.title}
          </div>
        ))}
      </aside>

      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            border: '0.5px solid var(--zw-surface-variant)',
            borderRadius: 16,
            padding: 16,
            background: 'var(--zw-surface-2)',
          }}
        >
          {active.messages.length === 0 && (
            <p className="zw-muted">先在「设置 / LLM」配置并启用 provider，再开始对话。</p>
          )}
          {active.messages.map((m, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--zw-on-surface-variant)' }}>
                {m.role === 'user' ? '你' : 'Assistant'}
              </div>
              <div
                style={{
                  whiteSpace: 'pre-wrap',
                  background: '#fff',
                  border: '0.5px solid var(--zw-surface-variant)',
                  borderRadius: 8,
                  padding: '8px 10px',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
          {busy && <p className="zw-muted">思考中…</p>}
          {err && <pre style={{ color: 'var(--zw-up)' }}>{err}</pre>}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <textarea
            aria-label="对话输入框"
            style={{
              flex: 1,
              minHeight: 44,
              padding: 8,
              borderRadius: 8,
              border: '0.5px solid var(--zw-outline)',
              fontFamily: 'inherit',
              resize: 'vertical',
            }}
            value={input}
            placeholder="输入消息，Enter 发送（Shift+Enter 换行）"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <button className="zw-btn zw-btn-filled" onClick={() => void send()} disabled={busy}>
            发送
          </button>
        </div>
      </div>

      {menu && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 50 }} onClick={() => setMenu(null)} aria-hidden="true" />
          <div
            role="menu"
            style={{
              position: 'fixed',
              left: menu.x,
              top: menu.y,
              zIndex: 60,
              background: 'var(--zw-surface)',
              border: '0.5px solid var(--zw-surface-variant)',
              borderRadius: 12,
              boxShadow: '0 6px 20px rgba(0,0,0,.14)',
              padding: 4,
              minWidth: 128,
            }}
          >
            <div
              role="menuitem"
              tabIndex={0}
              className="zw-ctx-item"
              onClick={() => doMenuAction('share')}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); doMenuAction('share'); } }}
            >
              分享
            </div>
            <div
              role="menuitem"
              tabIndex={0}
              className="zw-ctx-item"
              onClick={() => doMenuAction('archive')}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); doMenuAction('archive'); } }}
            >
              归档
            </div>
            <div
              role="menuitem"
              tabIndex={0}
              className="zw-ctx-item danger"
              onClick={() => doMenuAction('delete')}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); doMenuAction('delete'); } }}
            >
              删除
            </div>
          </div>
        </>
      )}
    </div>
  );
}
