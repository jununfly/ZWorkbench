type ZW = { apiBase?: string; getToken?: () => string };
const w = window as any as { __ZW__?: ZW };

// dev 模式（Vite）下 apiBase 指向 Go 服务；prod 下同源留空，由渲染进程 origin 兜底。
export function apiBase(): string {
  const base = w.__ZW__?.apiBase;
  if (base) return base;
  // prod 同源模式：Electron 加载的 URL 即 Go 服务本体，用 window.location.origin
  // 构造绝对 URL，避免 `new URL('' + path)` 因相对路径抛 Invalid URL（导致白屏）。
  return window.location.origin;
}

export function token(): string {
  if (w.__ZW__?.getToken) return w.__ZW__.getToken();
  return new URLSearchParams(window.location.search).get('token') || '';
}

export async function getJSON(path: string): Promise<any> {
  const u = new URL(apiBase() + path);
  u.searchParams.set('token', token());
  const res = await fetch(u.toString());
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

export async function reqJSON(method: string, path: string, body?: any): Promise<any> {
  const u = new URL(apiBase() + path);
  u.searchParams.set('token', token());
  const res = await fetch(u.toString(), {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}
