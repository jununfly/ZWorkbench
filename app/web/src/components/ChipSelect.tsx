import { useEffect, useRef, useState } from 'react';

// ChipSelect：将 Codex 的「上下文 chips」实现为可点击胶囊 + 下拉 popover（menu 模式）。
// a11y：胶囊是原生 <button>（自带键盘可达），popover 用 role="menu"/"menuitem"，
// 满足 eslint G-V4（label-has-associated-control 仅约束原生 input/select，此处用
// aria-label 提供可访问名；menuitem 不支持 aria-selected，选中态用视觉高亮 + 勾选符表达）。
// 键盘：ArrowUp/Down 在选项间移动、Escape 关闭；焦点在选项按钮上。
const CHIP: React.CSSProperties = {
  border: '1px solid #6750A4',
  color: '#6750A4',
  borderRadius: 999,
  padding: '4px 12px',
  background: '#fff',
  fontSize: 13,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
};

const POPOVER: React.CSSProperties = {
  position: 'absolute',
  top: 'calc(100% + 4px)',
  left: 0,
  zIndex: 10,
  margin: 0,
  padding: 4,
  listStyle: 'none',
  background: '#fff',
  border: '1px solid #eee',
  borderRadius: 8,
  boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
  minWidth: 150,
};

const OPTION: React.CSSProperties = {
  display: 'block',
  width: '100%',
  textAlign: 'left',
  border: 'none',
  background: 'transparent',
  padding: '6px 10px',
  borderRadius: 6,
  fontSize: 13,
  cursor: 'pointer',
  color: '#333',
};

interface ChipSelectProps {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  placeholder?: string;
}

export function ChipSelect({ label, value, options, onChange, placeholder }: ChipSelectProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const optRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  // 打开时把焦点移到首个选项，便于键盘操作。
  useEffect(() => {
    if (open) optRefs.current[0]?.focus();
  }, [open]);

  const choose = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  const onMenuKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setOpen(false);
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const cur = optRefs.current.findIndex((b) => b === document.activeElement);
      const delta = e.key === 'ArrowDown' ? 1 : -1;
      const next = Math.min(Math.max(cur < 0 ? 0 : cur + delta, 0), options.length - 1);
      optRefs.current[next]?.focus();
    }
  };

  return (
    <div ref={wrapRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        style={CHIP}
      >
        <span>{value || placeholder || `（${label}）`}</span>
        <span aria-hidden style={{ fontSize: 10 }}>▾</span>
      </button>
      {open && (
        <ul role="menu" aria-label={label} onKeyDown={onMenuKey} style={POPOVER}>
          {options.map((opt, i) => {
            const selected = opt === value;
            return (
              <li key={opt} role="none">
                <button
                  ref={(el) => {
                    optRefs.current[i] = el;
                  }}
                  role="menuitem"
                  onClick={() => choose(opt)}
                  style={{ ...OPTION, background: selected ? '#f0ecf8' : 'transparent' }}
                >
                  <span aria-hidden style={{ display: 'inline-block', width: 14 }}>
                    {selected ? '✓' : ''}
                  </span>
                  {opt}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
