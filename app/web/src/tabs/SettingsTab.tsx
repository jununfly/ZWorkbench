import { useEffect, useState } from 'react';
import { getJSON, reqJSON } from '../api';

const RED = '#cf1322';
const GREEN = '#3f8600';

export function SettingsTab() {
  const [baseURL, setBaseURL] = useState('https://api.deepseek.com/v1');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('deepseek-chat');
  const [enabled, setEnabled] = useState(false);
  const [keySet, setKeySet] = useState(false);
  const [status, setStatus] = useState('');
  const [testOut, setTestOut] = useState('');

  useEffect(() => {
    getJSON('/api/config')
      .then((d: any) => {
        const l = d.llm || {};
        setBaseURL(l.base_url || 'https://api.deepseek.com/v1');
        setModel(l.model || 'deepseek-chat');
        setEnabled(!!l.enabled);
        setKeySet(!!l.api_key_set);
      })
      .catch((e) => setStatus('加载配置失败：' + e));
  }, []);

  async function save() {
    setStatus('保存中…');
    try {
      const r = await reqJSON('PUT', '/api/config', {
        llm: { base_url: baseURL, api_key: apiKey, model, enabled },
      });
      setKeySet(!!r.api_key_set);
      setApiKey(''); // 清空输入框，避免误存/误显
      setStatus(r.ok ? (enabled ? '已保存并启用' : '已保存（未启用）') : '保存失败');
    } catch (e) {
      setStatus('保存失败：' + e);
    }
  }

  async function test() {
    setTestOut('调用中…');
    try {
      const r = await reqJSON('POST', '/api/agent/chat', {
        messages: [{ role: 'user', content: 'ping' }],
      });
      setTestOut('provider=' + r.model + '：\n' + r.content);
    } catch (e) {
      setTestOut('调用失败：' + e);
    }
  }

  return (
    <div style={{ maxWidth: 560 }}>
      <h2 style={{ marginTop: 0 }}>设置 / LLM Provider</h2>
      <p style={{ color: '#888', fontSize: 13 }}>
        配置 OpenAI / DeepSeek 兼容端点，持久化到本地 config.json（明文存储，单用户桌面可接受）。
        {keySet && <span style={{ color: GREEN }}> 当前已存有 API Key。</span>}
      </p>

      <label style={labelStyle}>Base URL</label>
      <input style={inputStyle} value={baseURL} onChange={(e) => setBaseURL(e.target.value)} placeholder="https://api.deepseek.com/v1" />

      <label style={labelStyle}>API Key</label>
      <input
        style={inputStyle}
        type="password"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder={keySet ? '已设置，留空则保持不变' : 'sk-...'}
      />

      <label style={labelStyle}>Model</label>
      <input style={inputStyle} value={model} onChange={(e) => setModel(e.target.value)} placeholder="deepseek-chat" />

      <label style={{ ...labelStyle, display: 'flex', alignItems: 'center', gap: 8 }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        启用（启用后「对话」页与 agent 端点会真实调用）
      </label>

      <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
        <button style={btnStyle} onClick={save}>保存</button>
        <button style={{ ...btnStyle, background: '#fff', color: '#333', border: '1px solid #ccc' }} onClick={test}>测试连接</button>
      </div>

      {status && <p style={{ fontSize: 13 }}>{status}</p>}
      {testOut && <pre style={{ background: '#f7f7f7', padding: 10, borderRadius: 6, whiteSpace: 'pre-wrap', fontSize: 13 }}>{testOut}</pre>}
    </div>
  );
}

const labelStyle: React.CSSProperties = { display: 'block', marginTop: 12, marginBottom: 4, fontSize: 13, color: '#555' };
const inputStyle: React.CSSProperties = { width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #ddd', boxSizing: 'border-box', fontFamily: 'inherit' };
const btnStyle: React.CSSProperties = { padding: '8px 16px', borderRadius: 6, border: 'none', background: RED, color: '#fff', cursor: 'pointer' };
