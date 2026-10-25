import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // dev 仅：把 /api 代理到 Go 服务（默认 127.0.0.1:18080），避免浏览器跨域；
    // token 由 index.html 的 dev 脚本注入（getToken → 'dev-token'），需与启动 Go 时的 ZW_TOKEN 一致。
    proxy: {
      '/api': { target: 'http://127.0.0.1:18080', changeOrigin: true },
    },
  },
  build: {
    // 覆盖写 dist，不做清空。清空依赖删除整个 outDir，在受限沙箱里会被删除拦截
    // （vite 的 emptyDir 直接抛 EPERM/state lock timeout，构建失败）；
    // dist 是 gitignore 的构建产物目录，覆盖写等价于拿到本次构建的最新文件。
    emptyOutDir: false,
  },
});
