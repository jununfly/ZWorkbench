const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const crypto = require('crypto');

const PORT = process.env.ZW_PORT || '18080';
const TOKEN = process.env.ZW_TOKEN || crypto.randomBytes(32).toString('hex');

let goProc = null;

// 启动 Go 本地服务（prod 用编译好的 bin；dev 由外部 `go run` 接管时注释本函数）
function startGoServer() {
  const bin = path.join(__dirname, '..', 'bin', 'zworkbench-go');
  goProc = spawn(bin, [], {
    env: { ...process.env, ZW_PORT: PORT, ZW_TOKEN: TOKEN },
    stdio: 'inherit',
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  // prod: Go 服务直接托管前端；dev: 走 Vite（ZW_WEB_URL）
  const url = process.env.ZW_WEB_URL || `http://127.0.0.1:${PORT}/?token=${TOKEN}`;
  win.loadURL(url);
}

app.whenReady().then(() => {
  startGoServer();
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (goProc) goProc.kill();
  if (process.platform !== 'darwin') app.quit();
});
