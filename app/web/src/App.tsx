import { useEffect, useState } from 'react';
import { getJSON } from './api';
import { StockTab } from './tabs/StockTab';
import { LimitUpTab } from './tabs/LimitUpTab';
import { SettingsTab } from './tabs/SettingsTab';
import { ChatTab } from './tabs/ChatTab';
import { PlaceholderTab } from './tabs/PlaceholderTab';

interface Tab { id: string; title: string; group: string; }

export function App() {
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [active, setActive] = useState<string>('');

  useEffect(() => {
    getJSON('/api/tabs')
      .then((t: Tab[]) => { setTabs(t); if (t[0]) setActive(t[0].id); })
      .catch((e) => console.error('load tabs failed', e));
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'system-ui' }}>
      <aside style={{ width: 200, borderRight: '1px solid #ddd', padding: 12 }}>
        <h3>ZWorkbench</h3>
        {tabs.map((t) => (
          <div
            key={t.id}
            onClick={() => setActive(t.id)}
            style={{
              padding: '8px 10px', cursor: 'pointer',
              background: active === t.id ? '#eef' : 'transparent',
              borderRadius: 6,
            }}
          >
            {t.title}
          </div>
        ))}
      </aside>
      <main style={{ flex: 1, padding: 16, overflow: 'auto' }}>
        {active === 'stock-overview' && <StockTab />}
        {active === 'stock-limitup' && <LimitUpTab />}
        {active === 'settings' && <SettingsTab />}
        {active === 'chat' && <ChatTab />}
        {active && active !== 'stock-overview' && active !== 'stock-limitup' && active !== 'settings' && active !== 'chat' && <PlaceholderTab id={active} />}
      </main>
    </div>
  );
}
