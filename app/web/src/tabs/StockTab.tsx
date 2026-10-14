import { useEffect, useState } from 'react';
import { getJSON } from '../api';

export function StockTab() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    getJSON('/api/stock/overview')
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <div>
      <h2>行情总览</h2>
      {err && <pre style={{ color: 'red' }}>{err}</pre>}
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
