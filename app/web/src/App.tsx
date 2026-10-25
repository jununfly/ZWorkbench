import { useState } from 'react';
import { HomeScreen } from './screens/HomeScreen';
import { WorkbenchScreen } from './screens/WorkbenchScreen';
import { AstockScreen } from './screens/AstockScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { PlaceholderScreen } from './screens/PlaceholderScreen';
import { Icon, ICON_PATHS } from './components/Icon';

// 固定一级导航（个人综合工作台）：不再依赖 /api/tabs，导航即设计事实。
type ScreenId = 'home' | 'workbench' | 'astock' | 'projects' | 'stats' | 'logs' | 'settings';

interface NavLeaf {
  label: string;
  icon: keyof typeof ICON_PATHS;
  screen: ScreenId;
}
interface NavNode {
  id: string;
  label: string;
  icon: keyof typeof ICON_PATHS;
  screen?: ScreenId;
  children?: NavLeaf[];
}

const NAV: NavNode[] = [
  { id: 'home', label: '首页', icon: 'home', screen: 'home' },
  { id: 'workbench', label: '工作台', icon: 'dash', screen: 'workbench' },
  {
    id: 'theme',
    label: '主题',
    icon: 'theme',
    children: [{ label: 'A股投研', icon: 'stock', screen: 'astock' }],
  },
  { id: 'projects', label: '项目', icon: 'folder', screen: 'projects' },
  { id: 'stats', label: '统计', icon: 'chart', screen: 'stats' },
  { id: 'logs', label: '日志', icon: 'list', screen: 'logs' },
  { id: 'settings', label: '设置', icon: 'set', screen: 'settings' },
];

function nodeIsActive(n: NavNode, screen: ScreenId): boolean {
  if (n.screen === screen) return true;
  return n.children?.some((c) => c.screen === screen) ?? false;
}

function renderScreen(s: ScreenId) {
  switch (s) {
    case 'home':
      return <HomeScreen />;
    case 'workbench':
      return <WorkbenchScreen />;
    case 'astock':
      return <AstockScreen />;
    case 'settings':
      return <SettingsScreen />;
    case 'projects':
      return <PlaceholderScreen title="项目" hint="项目页待实现（本轮占位）" />;
    case 'stats':
      return <PlaceholderScreen title="统计" hint="统计页待实现（可聚合交易数据）" />;
    case 'logs':
      return <PlaceholderScreen title="日志" hint="日志页待实现（可接现有 log）" />;
  }
}

export function App() {
  const [screen, setScreen] = useState<ScreenId>('home');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <aside
        style={{
          width: 240,
          flex: '0 0 240px',
          background: 'var(--zw-surface)',
          borderRight: '0.5px solid var(--zw-surface-variant)',
          padding: '16px 12px',
          overflowY: 'auto',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 12px',
            fontWeight: 500,
            fontSize: 16,
            marginBottom: 16,
          }}
        >
          <span
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: 'var(--zw-primary)',
              color: '#fff',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            Z
          </span>
          ZWorkbench
        </div>

        {NAV.map((n) => {
          const active = nodeIsActive(n, screen);
          if (n.children) {
            const open = expanded[n.id] ?? false;
            return (
              <div key={n.id} style={{ marginBottom: 2 }}>
                <div
                  role="button"
                  tabIndex={0}
                  className="zw-navitem"
                  onClick={() => setExpanded((e) => ({ ...e, [n.id]: !open }))}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded((x) => ({ ...x, [n.id]: !open })); } }}
                >
                  <Icon name={n.icon} />
                  <span>{n.label}</span>
                  <span className="zw-caret" style={{ transform: open ? 'rotate(90deg)' : 'none' }}>
                    ▶
                  </span>
                </div>
                {open && (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 2,
                      paddingLeft: 32,
                      marginTop: 2,
                    }}
                  >
                    {n.children.map((c) => (
                      <div
                        key={c.label}
                        role="button"
                        tabIndex={0}
                        className={'zw-navitem zw-subitem' + (c.screen === screen ? ' active' : '')}
                        onClick={() => setScreen(c.screen)}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setScreen(c.screen); } }}
                      >
                        <Icon name={c.icon} />
                        <span>{c.label}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          }
          return (
            <div
              key={n.id}
              role="button"
              tabIndex={0}
              className={'zw-navitem' + (active ? ' active' : '')}
              style={{ marginBottom: 2 }}
              onClick={() => n.screen && setScreen(n.screen)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (n.screen) setScreen(n.screen); } }}
            >
              <Icon name={n.icon} />
              <span>{n.label}</span>
            </div>
          );
        })}
      </aside>

      <main style={{ flex: 1, overflowY: 'auto', padding: 32, background: 'var(--zw-surface)' }}>
        {renderScreen(screen)}
      </main>
    </div>
  );
}
