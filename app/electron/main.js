const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const net = require('net');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ---------------------------------------------------------------------------
// 1-1-3 打包运行时契约（决策见路线图节点 1-1-3）：
//   1) 端口不写死：先取一个空闲端口再注入 ZW_PORT，避免与已运行的 `go run` 冲突；
//   2) 单实例锁：第二次拉起只聚焦已有窗口，绝不启动第二个 Go 进程；
//   3) 落点可写：packaged app 的 cwd 在 macOS 下是 `/`，所以 ZW_CONFIG 显式指向
//      userData，否则 LLM 配置保存会写失败；
//   4) Go 二进制定位两路：packaged → process.resourcesPath/bin，dev → ../bin；
//   5) 加载窗口前先探活 Go 服务，避免竞态导致首屏 404/白屏。
// ---------------------------------------------------------------------------

let goProc = null;

function goBinPath() {
  const name = process.platform === 'win32' ? 'zworkbench-go.exe' : 'zworkbench-go';
  const base = app.isPackaged ? path.join(process.resourcesPath, 'bin') : path.join(__dirname, '..', 'bin');
  return path.join(base, name);
}

function webDir() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'web', 'dist')
    : path.join(__dirname, '..', 'web', 'dist');
}

function logFilePath() {
  try {
    return path.join(app.getPath('userData'), 'zw-go.log');
  } catch {
    return path.join(app.getPath('temp'), 'zw-go.log');
  }
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(String(port)));
    });
  });
}

function startGoServer(port, token) {
  const bin = goBinPath();
  if (!fs.existsSync(bin)) {
    throw new Error(`Go 二进制缺失：${bin}（先执行 app/scripts/build-desktop.sh 构建）`);
  }

  const logPath = logFilePath();
  try {
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.writeFileSync(logPath, `[zw-electron] ${new Date().toISOString()} start ${bin}\n`);
  } catch (e) {
    console.warn('[zw-electron] 无法写入日志：', e.message);
  }

  goProc = spawn(bin, [], {
    env: {
      ...process.env,
      ZW_PORT: port,
      ZW_TOKEN: token,
      ZW_WEB_DIR: webDir(),
      ZW_CONFIG: path.join(app.getPath('userData'), 'config.json'),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  const pipe = (stream) => {
    stream.on('data', (buf) => {
      try {
        fs.appendFileSync(logPath, buf);
      } catch {
        /* 日志写失败不阻断主流程 */
      }
    });
  };
  pipe(goProc.stdout);
  pipe(goProc.stderr);

  goProc.on('error', (err) => console.error('[zw-electron] Go 进程启动失败：', err.message));
  goProc.on('exit', (code, signal) => {
    console.log(`[zw-electron] Go 进程退出 code=${code} signal=${signal}`);
    goProc = null;
  });

  return logPath;
}

// 探活：Go 服务起来后端口才 accept。用 TCP connect 判定，不依赖 /api/health 的 token。
function waitForHealth(port, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tick = () => {
      const sock = net.connect({ host: '127.0.0.1', port: Number(port) });
      const done = () => sock.destroy();
      sock.setTimeout(1000);
      sock.on('connect', () => {
        done();
        resolve(true);
      });
      const retry = () => {
        done();
        if (Date.now() > deadline) {
          reject(new Error(`Go 服务在 ${timeoutMs}ms 内未在 127.0.0.1:${port} 就绪，详见 ${logFilePath()}`));
          return;
        }
        setTimeout(tick, 200);
      };
      sock.on('error', retry);
      sock.on('timeout', retry);
    };
    tick();
  });
}

async function boot() {
  const token = crypto.randomBytes(32).toString('hex');
  const port = process.env.ZW_PORT || (await freePort());

  let logPath = '';
  try {
    logPath = startGoServer(port, token);
    await waitForHealth(port);
  } catch (err) {
    dialog.showErrorBox('ZWorkbench 启动失败', `${err.message}\n\nGo 服务日志：${logPath || logFilePath()}`);
    app.quit();
    return null;
  }

  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'ZWorkbench',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // ---- 渲染进程诊断（1-1-3 白屏排查）-----------------------------------------
  // 把 Chromium 侧看到的 console / 加载失败 / 渲染进程崩溃 落到 zw-go.log，
  // 这样「整屏白」不再无迹可寻：要么是资源 404/CORS（did-fail-load），要么是 JS
  // 异常（console-message），要么是 React 根本没挂载（dom-ready 时 #root 子节点为 0）。
  const zwLog = (...a) => {
    try {
      fs.appendFileSync(
        logFilePath(),
        a.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(' ') + '\n',
      );
    } catch {
      /* 日志写失败不阻断主流程 */
    }
  };
  win.webContents.on('console-message', (e) => {
    zwLog(`[renderer:console:${e.type}]`, e.message, e.location ? `${e.location.url}:${e.location.line}` : '');
  });
  win.webContents.on('did-fail-load', (_e, code, desc, failedUrl) => {
    zwLog(`[did-fail-load] code=${code} desc=${desc} url=${failedUrl}`);
  });
  win.webContents.on('render-process-gone', (_e, details) => {
    zwLog(`[render-process-gone] reason=${details.reason}`);
  });
  win.webContents.on('did-start-loading', () => zwLog('[did-start-loading]'));
  win.webContents.on('did-finish-load', () => zwLog('[did-finish-load]'));
  win.webContents.on('dom-ready', () => {
    win.webContents
      .executeJavaScript('(function(){var r=document.getElementById("root");return r?r.childElementCount:-1;})()')
      .then((n) => zwLog(`[dom-ready] #root childCount=${n}`))
      .catch((e) => zwLog('[dom-ready] exec err ' + e));
  });

  // dev 可指向 Vite（ZW_WEB_URL）；prod 走 Go 同源托管的前端产物。
  const url = process.env.ZW_WEB_URL || `http://127.0.0.1:${port}/?token=${token}`;
  await win.loadURL(url);
  return win;
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const all = BrowserWindow.getAllWindows();
    if (all.length) {
      if (all[0].isMinimized()) all[0].restore();
      all[0].focus();
    }
  });

  app.whenReady().then(async () => {
    await boot();
    app.on('activate', async () => {
      if (BrowserWindow.getAllWindows().length === 0) await boot();
    });
  });
}

function stopGo() {
  if (goProc && !goProc.killed) {
    goProc.kill();
    goProc = null;
  }
}

app.on('window-all-closed', () => {
  stopGo();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', stopGo);
app.on('will-quit', stopGo);
