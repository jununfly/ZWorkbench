const { contextBridge } = require('electron');

// 仅暴露最小桥接：apiBase（同机 Go 服务地址）+ token 读取。
// token 优先从 URL query 取（Electron 加载时带入），避免把密钥暴露给渲染进程全局。
contextBridge.exposeInMainWorld('__ZW__', {
  apiBase: '',
  getToken: () => new URLSearchParams(window.location.search).get('token') || '',
});
