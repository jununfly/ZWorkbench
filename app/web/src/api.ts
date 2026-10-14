type ZW = { apiBase?: string; getToken?: () => string };
const w = window as any as { __ZW__?: ZW };

// dev 模式（Vite）下 apiBase 指向 Go 服务；prod 下同源留空。
export function apiBase(): string {
  return w.__ZW__?.apiBase ?? 'http://127.0.0.1:18080';
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
