import type { ReactNode } from 'react';

interface SourceStatusBannerProps {
  source?: string;
  fallback?: boolean;
  status?: string; // ok | unconfigured | source_failed（roadmap 1-2-5）
  reason?: string;
  asOf?: string;
}

// 统一展示「数据来源 + 语义状态」横幅（roadmap 1-2-5）。
// 关键不变量：未配置 ≠ 源失败 ≠ 陈旧快照，三者都不能被当成成功展示。
//   - ok            → 绿色「实时数据」
//   - unconfigured  → 灰信息「未接入实时源，展示本地快照」（良性，不报警）
//   - source_failed → 红色告警，含 reason，明确「请勿当作实时结果」（绝不当作成功）
// fallback=true + source=local-snapshot 即代表「数据来自内嵌种子，可能陈旧」。
export function SourceStatusBanner({ source, fallback, status, reason, asOf }: SourceStatusBannerProps): ReactNode {
  let banner: ReactNode = null;
  if (status === 'source_failed') {
    banner = (
      <div style={{ marginTop: 8, padding: '8px 12px', borderRadius: 8, background: '#fff1f0', border: '1px solid #ffccc7', color: '#cf1322', fontSize: 13, lineHeight: 1.6 }}>
        <b>⚠ 实时源连接失败</b>{reason ? `：${reason}` : ''}。已回退本地快照，数据可能陈旧，<b>请勿当作实时结果</b>。
      </div>
    );
  } else if (status === 'unconfigured') {
    banner = (
      <div style={{ marginTop: 8, padding: '6px 12px', borderRadius: 8, background: '#fafafa', border: '1px solid #e8e8e8', color: '#888', fontSize: 13, lineHeight: 1.6 }}>
        未接入实时源，当前展示本地快照（数据可能陈旧）。可在「设置」页配置实时数据源。
      </div>
    );
  } else if (status === 'ok') {
    banner = (
      <div style={{ marginTop: 8, padding: '6px 12px', borderRadius: 8, background: '#f6ffed', border: '1px solid #b7eb8f', color: '#389e0d', fontSize: 13 }}>
        ✓ 实时数据
      </div>
    );
  }
  return (
    <div>
      <div style={{ fontSize: 12, color: '#888' }}>
        来源 {source || '-'}
        {fallback && <span style={{ color: '#d46b08' }}>（回退）</span>}
        {asOf ? ` · ${asOf}` : ''}
      </div>
      {banner}
    </div>
  );
}
