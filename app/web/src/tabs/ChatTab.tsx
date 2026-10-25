import { useState } from 'react';
import { reqJSON } from '../api';

interface Turn { role: string; content: string; }

export function ChatTab() {
  const [messages, setMessages] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    const next = [...messages, { role: 'user', content: text }];
    setMessages(next);
    setInput('');
    setBusy(true);
    setErr('');
    try {
      const r = await reqJSON('POST', '/api/agent/chat', {
        messages: next.map((m) => ({ role: m.role, content: m.content })),
      });
      setMessages([...next, { role: 'assistant', content: r.content }]);
    } catch (e) {
      setErr('调用失败：' + e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 720, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <h2 style={{ marginTop: 0 }}>对话（LLM Provider）</h2>
      <div style={{ flex: 1, overflow: 'auto', border: '1px solid #eee', borderRadius: 8, padding: 12, background: '#fafafa' }}>
        {messages.length === 0 && <p style={{ color: '#999' }}>先在「设置 / LLM」配置并启用 provider，再开始对话。</p>}
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, color: '#888' }}>{m.role === 'user' ? '你' : 'Assistant'}</div>
            <div style={{ whiteSpace: 'pre-wrap', background: '#fff', border: '1px solid #f0f0f0', borderRadius: 6, padding: '8px 10px' }}>{m.content}</div>
          </div>
        ))}
        {busy && <p style={{ color: '#999' }}>思考中…</p>}
        {err && <pre style={{ color: '#cf1322' }}>{err}</pre>}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <textarea
          aria-label="对话输入框"
          style={{ flex: 1, minHeight: 44, padding: 8, borderRadius: 6, border: '1px solid #ddd', fontFamily: 'inherit', resize: 'vertical' }}
          value={input}
          placeholder="输入消息，Enter 发送（Shift+Enter 换行）"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
        />
        <button style={{ padding: '0 18px', borderRadius: 6, border: 'none', background: '#cf1322', color: '#fff', cursor: 'pointer' }} onClick={send} disabled={busy}>发送</button>
      </div>
    </div>
  );
}
