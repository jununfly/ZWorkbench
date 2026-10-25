// 轻量图标组件：复用 preview 的 Material Symbols 派生路径（Apache-2.0，无运行时）。
// 不引入 @material/web，保持零额外依赖。

export const ICON_PATHS = {
  home: 'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z',
  dash: 'M3 13h8V3H3zm0 8h8v-6H3zm10 0h8V11h-8zm0-18v6h8V3z',
  theme:
    'M12 3a9 9 0 100 18c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01-.23-.26-.39-.61-.39-.99 0-.83.67-1.5 1.5-1.5H16a5 5 0 005-5c0-4.42-4.03-8-9-8z',
  stock: 'M3.5 18.5l6-6 4 4 7.5-7.5v5h2v-9h-9v2h5.5l-5.5 5.5-4-4-7 7z',
  folder: 'M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8z',
  chart: 'M5 9.2h3V19H5zM10.6 5h3v14h-3zm5.6 8H19v6h-2.8z',
  list: 'M4 6h16v2H4zm0 5h16v2H4zm0 5h16v2H4z',
  set: 'M19.14 12.94c.04-.31.06-.64.06-1s-.02-.69-.06-1l2.04-1.58a.5.5 0 00.12-.64l-1.94-3.36a.5.5 0 00-.61-.22l-2.4.96a7.3 7.3 0 00-1.74-1l-.36-2.54a.5.5 0 00-.5-.42h-3.88a.5.5 0 00-.5.42l-.36 2.54c-.62.25-1.2.59-1.74 1l-2.4-.96a.5.5 0 00-.61.22L2.3 8.12a.5.5 0 00.12.64l2.04 1.58c-.04.31-.06.64-.06 1s.02.69.06 1l-2.04 1.58a.5.5 0 00-.12.64l1.94 3.36c.14.24.43.34.69.22l2.4-.96c.54.41 1.12.75 1.74 1l.36 2.54c.05.24.25.42.5.42h3.88c.25 0 .45-.18.5-.42l.36-2.54c.62-.25 1.2-.59 1.74-1l2.4.96c.26.12.55.02.69-.22l1.94-3.36a.5.5 0 00-.12-.64zM12 15.5A3.5 3.5 0 1112 8.5a3.5 3.5 0 010 7z',
} as const;

export type IconName = keyof typeof ICON_PATHS;

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      style={{ flex: '0 0 ' + size + 'px' }}
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}
