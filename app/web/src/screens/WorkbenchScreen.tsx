import { useState } from 'react';
import { ChatPanel } from '../components/ChatPanel';
import { CodingEvidenceTab } from '../tabs/CodingEvidenceTab';

// 工作台：非交易自治能力 —— 对话（ChatPanel）+ 编码证据（CodingEvidenceTab）。
export function WorkbenchScreen() {
  const [tab, setTab] = useState<'chat' | 'evidence'>('chat');
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 500, margin: '0 0 8px' }}>工作台</h1>
      <p className="zw-muted" style={{ marginBottom: 24 }}>
        非交易自治能力：对话 + 编码证据
      </p>

      <div
        style={{
          display: 'flex',
          gap: 4,
          borderBottom: '0.5px solid var(--zw-surface-variant)',
          marginBottom: 24,
        }}
      >
        {(['chat', 'evidence'] as const).map((t) => (
          <div
            key={t}
            role="button"
            tabIndex={0}
            onClick={() => setTab(t)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTab(t); } }}
            style={{
              padding: '12px 16px',
              cursor: 'pointer',
              color: tab === t ? 'var(--zw-primary)' : 'var(--zw-on-surface-variant)',
              borderBottom: '2px solid ' + (tab === t ? 'var(--zw-primary)' : 'transparent'),
              fontWeight: tab === t ? 500 : 400,
            }}
          >
            {t === 'chat' ? '对话' : '编码证据'}
          </div>
        ))}
      </div>

      {tab === 'chat' && <ChatPanel />}
      {tab === 'evidence' && <CodingEvidenceTab />}
    </div>
  );
}
