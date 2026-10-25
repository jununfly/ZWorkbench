import { ReactNode, useState } from 'react';

interface SectionCardProps {
  id: string;
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

// A股投研长页面分区大卡片：标题可点击折叠/展开内容（状态保留，不卸载）。
export function SectionCard({ id, title, defaultOpen = true, children }: SectionCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = `${id}-body`;
  return (
    <section id={id} className="zw-section-card" style={{ scrollMarginTop: 32 }}>
      <button
        type="button"
        className="zw-section-head"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="zw-section-title">{title}</span>
        <span className={`zw-section-caret${open ? ' open' : ''}`} aria-hidden="true">▾</span>
      </button>
      <div id={bodyId} className="zw-section-body" style={{ display: open ? 'block' : 'none' }}>
        {children}
      </div>
    </section>
  );
}
