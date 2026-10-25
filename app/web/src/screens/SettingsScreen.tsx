import { useState } from 'react';
import { SettingsTab } from '../tabs/SettingsTab';

// 设置：通用（本轮占位）+ LLM Provider 配置（复用现有 SettingsTab）。
export function SettingsScreen() {
  const [tab, setTab] = useState<'general' | 'llm'>('general');
  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 500, margin: '0 0 8px' }}>设置</h1>
      <p className="zw-muted" style={{ marginBottom: 24 }}>
        通用设置 + LLM 配置
      </p>

      <div
        style={{
          display: 'flex',
          gap: 4,
          borderBottom: '0.5px solid var(--zw-surface-variant)',
          marginBottom: 24,
        }}
      >
        {(['general', 'llm'] as const).map((t) => (
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
            {t === 'general' ? '通用' : 'LLM 配置'}
          </div>
        ))}
      </div>

      {tab === 'general' && (
        <div className="zw-card" style={{ maxWidth: 560 }}>
          <h3>通用</h3>
          <p className="zw-muted" style={{ margin: 0 }}>
            主题：浅色（M3 深主题为派生可选，本轮仅浅色）。编码证据 / 对话等核心功能位于「工作台」。
          </p>
        </div>
      )}
      {tab === 'llm' && <SettingsTab />}
    </div>
  );
}
