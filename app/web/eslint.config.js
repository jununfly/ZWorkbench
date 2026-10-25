import tsParser from '@typescript-eslint/parser';
import jsxA11y from 'eslint-plugin-jsx-a11y';

// ZWorkbench Web a11y 门禁（G-V4）：基于 eslint-plugin-jsx-a11y recommended。
// 强制（error）：必填输入可访问性 —— control-has-associated-label / label-has-associated-control。
// 告警（warn，不阻断构建）：交互元素键盘可达性（no-static-element-interactions 等），作为后续迭代待办跟踪。
// 不启用 no-undef：TS 文件由 tsc 负责未定义检查，避免 React/window 等浏览器全局误报。
export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'ui-spec/**', '*.config.js', '*.config.ts'],
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { 'jsx-a11y': jsxA11y },
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      'jsx-a11y/no-static-element-interactions': 'warn',
      'jsx-a11y/click-events-have-key-events': 'warn',
      'jsx-a11y/no-noninteractive-element-interactions': 'warn',
    },
  },
];
