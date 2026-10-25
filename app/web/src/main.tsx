import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './theme.css';

// 渲染期错误边界：任何子组件 render 抛错都不再导致「整屏白」，而是显示可读错误。
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { err?: Error }> {
  state: { err?: Error } = {};
  static getDerivedStateFromError(err: Error) {
    return { err };
  }
  componentDidCatch(err: Error, info: React.ErrorInfo) {
    console.error('[ZW] render error:', err, info.componentStack);
  }
  render() {
    if (this.state.err) return <FatalError err={this.state.err} />;
    return this.props.children;
  }
}

function FatalError({ err }: { err: Error }) {
  return (
    <div style={{ padding: 24, fontFamily: 'system-ui', color: '#cf1322' }}>
      <h2>ZWorkbench 渲染错误</h2>
      <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{err.message + '\n\n' + (err.stack || '')}</pre>
    </div>
  );
}

// 兜底：模块加载 / 顶层异常发生在 React 挂载之前（错误边界抓不到），用 window.onerror
// 把错误写进 #root，避免「整屏白」无法诊断。
function showFatal(msg: string) {
  const root = document.getElementById('root');
  if (root && root.childElementCount === 0) {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'padding:24px;font-family:system-ui;color:#cf1322';
    const h = document.createElement('h2');
    h.textContent = 'ZWorkbench 启动错误';
    const pre = document.createElement('pre');
    pre.style.cssText = 'white-space:pre-wrap;font-size:13px';
    pre.textContent = msg;
    wrap.appendChild(h);
    wrap.appendChild(pre);
    root.appendChild(wrap);
  }
}
window.addEventListener('error', (e) => {
  const ev = e as ErrorEvent;
  showFatal((ev.error && (ev.error.stack || ev.error.message)) || ev.message || String(e));
});
window.addEventListener('unhandledrejection', (e) => {
  const r = (e as PromiseRejectionEvent).reason;
  showFatal('unhandledrejection: ' + ((r && (r.stack || r.message)) || String(r)));
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
