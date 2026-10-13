// ZWorkbench desktop shell — roadmap slice 1-1-1.
//
// Contract this file relies on (src/zworkbench/cli.py):
//   * `zworkbench ui-host` binds loopback only and takes `--port 0` to ask the
//     OS for a free port, so the shell never has to guess or reserve one.
//   * Before entering its serving loop it prints one JSON line to STDOUT:
//       {"event": "serving", "mode": "read-only", "review": false,
//        "base_url": "http://127.0.0.1:<port>"}
//     Reading that line is the documented readiness signal, so the shell does
//     not poll the port.
//   * It traps SIGINT/SIGTERM, closes the socket, prints {"event":"stopped"}
//     and exits, which is what lets this shell stop it cleanly.
//
// The child is the only server; the shell owns nothing but the window.
// Nothing here opens the owner database or touches durable state.
//
// Two modes:
//   * default         — open a visible window (the product path).
//   * screenshot mode — ZW_DESKTOP_SHOTS_DIR is set: render each route in an
//     offscreen window, write PNG + a DOM probe to that dir, then exit. This
//     is how the window contents get verified in a headless environment where
//     no human can look at the screen.

const { app, BrowserWindow, Menu, Tray, nativeImage } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

// A macOS tray icon has to be a real image and the repo ships no asset, so the
// icon is a generated 32x32 RGBA ring inlined here (168 bytes). Template mode
// lets macOS tint it for light/dark menu bars.
const TRAY_ICON_DATA_URL =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAb0lEQVR42u2XUQoAIAhDvf+l7QQRNcdmGOzXvcBsRjQ9uZHElA6ToKTmEEQWS2p+BZFkSc2PEFIAtAgMUdVIVIDKRqbc/rkeY5oNwH8A1CaUP8M2g4g6iuc3tAgkFpHMIpRaxHKLxcRiNbNZTilnAZ5hPd+tLErDAAAAAElFTkSuQmCC';

// The CLI is resolved from the environment so a source checkout works without
// installing the console script:
//   ZWORKBENCH_CLI=<executable>            (default: "zworkbench" on PATH)
//   ZWORKBENCH_CLI_PREARGS=<args before>   (e.g. "-m zworkbench.cli")
const CLI = process.env.ZWORKBENCH_CLI || 'zworkbench';
const PREARGS = (process.env.ZWORKBENCH_CLI_PREARGS || '')
  .split(/\s+/)
  .filter(Boolean);
const READY_TIMEOUT_MS = Number(process.env.ZWORKBENCH_READY_TIMEOUT_MS || 20000);
const STOP_TIMEOUT_MS = 5000;

// Screenshot mode configuration.
const SHOTS_DIR = process.env.ZW_DESKTOP_SHOTS_DIR || '';
const SHOTS_ROUTES = (process.env.ZW_DESKTOP_SHOTS_ROUTES || '/home,/record-view,/task-detail')
  .split(',')
  .map((route) => route.trim())
  .filter(Boolean);
const SHOTS_WIDTH = Number(process.env.ZW_DESKTOP_SHOTS_WIDTH || 1280);
const SHOTS_HEIGHT = Number(process.env.ZW_DESKTOP_SHOTS_HEIGHT || 860);
// Server-rendered HTML needs no bundler, but layout/paint still takes a beat.
const SHOTS_SETTLE_MS = Number(process.env.ZW_DESKTOP_SHOTS_SETTLE_MS || 1500);

const SCREENSHOT_MODE = SHOTS_DIR !== '';
const SELFCHECK_MODE = process.env.ZW_DESKTOP_SELFCHECK === '1';

// Screenshot mode must not touch the real user-data directory: it is a
// verification run, and on a locked-down host Electron's shutdown cleanup of
// ~/Library/Application Support can be denied, which turns a successful run
// into a non-zero exit. Keeping the profile next to the PNGs makes the run
// self-contained and its exit code mean "were the views broken".
if (SCREENSHOT_MODE || SELFCHECK_MODE) {
  app.setPath('userData', path.join(SHOTS_DIR || process.env.TMPDIR || '/tmp', '_zw_verify_userdata'));
}

let host = null;
let hostStopping = false;
let mainWindow = null;
let currentBaseUrl = null;
let tray = null;

// The route catalogue is the one thing both the menu and the tray menu drive,
// so a new view only has to be declared once.
const ROUTES = [
  { id: 'view-home', label: '工作台', route: '/home' },
  { id: 'view-task-detail', label: '任务详情', route: '/task-detail' },
  { id: 'view-record-view', label: '记录视图', route: '/record-view' },
];

function spawnHost() {
  const args = [...PREARGS, 'ui-host', '--host', '127.0.0.1', '--port', '0'];
  const child = spawn(CLI, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  child.stderr.on('data', (chunk) => {
    process.stderr.write('[ui-host] ' + chunk.toString('utf8'));
  });
  return child;
}

// Resolve with base_url once the child announces that it is serving.
function waitForServing(child) {
  return new Promise((resolve, reject) => {
    let buffer = '';
    const timer = setTimeout(() => {
      reject(
        new Error(
          'timed out after ' +
            READY_TIMEOUT_MS +
            'ms waiting for the ui-host serving announcement'
        )
      );
    }, READY_TIMEOUT_MS);

    const settle = (fn, value) => {
      clearTimeout(timer);
      fn(value);
    };

    child.stdout.on('data', (chunk) => {
      buffer += chunk.toString('utf8');
      let newline = buffer.indexOf('\n');
      while (newline >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        newline = buffer.indexOf('\n');
        if (!line) continue;
        let payload;
        try {
          payload = JSON.parse(line);
        } catch (error) {
          continue; // any non-JSON chatter is not the announcement
        }
        if (payload && payload.event === 'serving' && payload.base_url) {
          settle(resolve, payload.base_url);
          return;
        }
      }
    });

    child.on('error', (error) => {
      settle(
        reject,
        new Error(
          'failed to start ' +
            CLI +
            ': ' +
            error.message +
            ' (set ZWORKBENCH_CLI / ZWORKBENCH_CLI_PREARGS)'
        )
      );
    });
    child.on('exit', (code, signal) => {
      settle(
        reject,
        new Error(
          'ui-host exited before serving (code=' + code + ' signal=' + signal + ')'
        )
      );
    });
  });
}

// Ask ui-host to stop. It traps SIGTERM and closes the socket itself; SIGKILL
// is only the fallback for a child that ignored the signal.
function stopHost() {
  if (!host || hostStopping || host.exitCode !== null) return Promise.resolve();
  hostStopping = true;
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (host.exitCode === null) host.kill('SIGKILL');
      resolve();
    }, STOP_TIMEOUT_MS);
    host.once('exit', () => {
      clearTimeout(timer);
      resolve();
    });
    host.kill('SIGTERM');
  });
}

// Loads a route into the shell's own window. Handlers resolve the window from
// module scope rather than the click callback's window argument: an offscreen
// or unfocused window arrives there as undefined, and a menu that silently
// does nothing is worse than one that navigates.
function navigateTo(route) {
  if (!mainWindow || !currentBaseUrl) return false;
  mainWindow.loadURL(currentBaseUrl.replace(/\/+$/, '') + route);
  return true;
}

function buildApplicationMenu() {
  const template = [
    {
      label: app.name,
      submenu: [
        { id: 'app-about', label: '关于 ZWorkbench', role: 'about' },
        { type: 'separator' },
        { id: 'app-quit', label: '退出', role: 'quit' },
      ],
    },
    {
      label: '视图',
      submenu: [
        ...ROUTES.map((entry) => ({
          id: entry.id,
          label: entry.label,
          accelerator: undefined,
          click: () => navigateTo(entry.route),
        })),
        { type: 'separator' },
        { id: 'view-reload', label: '重新加载', role: 'reload' },
        { id: 'view-actual-size', label: '实际大小', role: 'resetZoom' },
        { id: 'view-toggle-devtools', label: '开发者工具', role: 'toggleDevTools' },
      ],
    },
    {
      label: '窗口',
      submenu: [
        { id: 'window-minimize', label: '最小化', role: 'minimize' },
        { id: 'window-close', label: '关闭', role: 'close' },
      ],
    },
  ];
  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
  return menu;
}

function createTray() {
  const image = nativeImage.createFromDataURL(TRAY_ICON_DATA_URL);
  image.setTemplateImage(true);
  const menu = Menu.buildFromTemplate([
    {
      id: 'tray-show',
      label: '显示窗口',
      click: () => {
        if (!mainWindow) return;
        if (mainWindow.isVisible()) mainWindow.show();
        mainWindow.focus();
      },
    },
    { type: 'separator' },
    ...ROUTES.map((entry) => ({
      id: 'tray-' + entry.id,
      label: entry.label,
      click: () => {
        navigateTo(entry.route);
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    })),
    { type: 'separator' },
    { id: 'tray-quit', label: '退出', role: 'quit' },
  ]);
  const instance = new Tray(image);
  instance.setToolTip('ZWorkbench');
  instance.setContextMenu(menu);
  tray = instance;
  // The menu is returned as well as attached: recent Electron removed
  // Tray.getContextMenu(), so callers that want to assert on it have to hold
  // the reference themselves.
  return menu;
}

function createWindow(baseUrl) {
  const window = new BrowserWindow({
    width: 1280,
    height: 860,
    title: 'ZWorkbench',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  window.on('closed', () => {
    if (mainWindow === window) mainWindow = null;
  });
  window.loadURL(baseUrl);
  mainWindow = window;
  return window;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Runs inside the renderer. A HTTP 200 only proves the server answered; this
// proves the DOM was actually built and holds visible content.
function domProbe() {
  const text = ((document.body && document.body.innerText) || '').trim();
  const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
    .map((element) => (element.textContent || '').trim())
    .filter(Boolean)
    .slice(0, 8);
  return {
    url: location.href,
    title: document.title || '',
    nodeCount: document.querySelectorAll('*').length,
    textLength: text.length,
    headings,
    textHead: text.slice(0, 400),
    looksBroken:
      text.length === 0 ||
      /Traceback \(most recent call last\)|Internal Server Error|500\b/.test(text),
  };
}

// Decoding the bitmap turns "did it actually paint" into a number instead of
// an opinion. A blank or single-colour page is the failure mode a HTTP 200
// cannot catch, and it is cheaper to assert here than to ask somebody to
// squint at a PNG.
function pixelStats(image) {
  const bitmap = image.toBitmap();
  const size = image.getSize();
  const total = size.width * size.height;
  // Sample rather than walk every pixel; 200k samples is plenty to tell a
  // rendered page from an empty one.
  const stride = Math.max(1, Math.floor(total / 200000));
  const counts = new Map();
  let sampled = 0;
  for (let i = 0; i < total; i += stride) {
    const offset = i * 4;
    const key = (bitmap[offset] << 16) | (bitmap[offset + 1] << 8) | bitmap[offset + 2];
    counts.set(key, (counts.get(key) || 0) + 1);
    sampled += 1;
  }
  let topKey = 0;
  let topCount = 0;
  for (const [key, count] of counts) {
    if (count > topCount) {
      topCount = count;
      topKey = key;
    }
  }
  return {
    width: size.width,
    height: size.height,
    sampled,
    uniqueColors: counts.size,
    dominantColor: '#' + topKey.toString(16).padStart(6, '0'),
    inkRatio: Number((1 - topCount / sampled).toFixed(4)),
  };
}

// A page that painted text, borders or cards is never one flat colour.
function looksBlank(pixels) {
  return pixels.inkRatio < 0.005 || pixels.uniqueColors < 8;
}

async function captureRoute(window, baseUrl, route, outDir) {
  const url = baseUrl.replace(/\/+$/, '') + route;
  const consoleErrors = [];
  const loadFailures = [];

  const onMessage = (...args) => {
    const event = args[0] || {};
    const level = typeof args[1] === 'number' ? args[1] : event.level;
    const message = typeof args[2] === 'string' ? args[2] : event.message;
    if (level === 'error' || level === 3) consoleErrors.push(String(message || ''));
  };
  const onFail = (event, errorCode, errorDescription, validatedURL) => {
    loadFailures.push({ errorCode, errorDescription, url: validatedURL || url });
  };

  window.webContents.on('console-message', onMessage);
  window.webContents.on('did-fail-load', onFail);

  const loaded = new Promise((resolve) => {
    window.webContents.once('did-finish-load', () => resolve(true));
    window.webContents.once('did-fail-load', () => resolve(false));
  });

  await window.webContents.loadURL(url);
  const loadedOk = await loaded;
  await sleep(SHOTS_SETTLE_MS);

  const probe = await window.webContents.executeJavaScript(
    '(' + domProbe.toString() + ')()'
  );

  const image = await window.webContents.capturePage();
  const slug = route.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'root';
  const pngPath = path.join(outDir, slug + '.png');
  await fs.promises.writeFile(pngPath, image.toPNG());
  const pixels = pixelStats(image);

  window.webContents.off('console-message', onMessage);
  window.webContents.off('did-fail-load', onFail);

  return {
    route,
    url,
    loadedOk,
    pngPath,
    bytes: image.toPNG().length,
    pixels,
    blank: looksBlank(pixels),
    probe,
    consoleErrors,
    loadFailures,
  };
}

// Offscreen render + PNG + DOM probe, then exit. No GUI session required.
async function runScreenshotMode(baseUrl) {
  await fs.promises.mkdir(SHOTS_DIR, { recursive: true });
  const window = new BrowserWindow({
    show: false,
    width: SHOTS_WIDTH,
    height: SHOTS_HEIGHT,
    webPreferences: {
      offscreen: true,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const results = [];
  for (const route of SHOTS_ROUTES) {
    results.push(await captureRoute(window, baseUrl, route, SHOTS_DIR));
  }
  window.destroy();

  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    viewport: { width: SHOTS_WIDTH, height: SHOTS_HEIGHT },
    results,
  };
  const reportPath = path.join(SHOTS_DIR, 'report.json');
  await fs.promises.writeFile(reportPath, JSON.stringify(report, null, 2));

  for (const result of results) {
    process.stdout.write(
      '[desktop] shot ' +
        result.route +
        ' -> ' +
        result.pngPath +
        ' (' +
        result.bytes +
        ' bytes, ' +
        result.pixels.width +
        'x' +
        result.pixels.height +
        ', colors=' +
        result.pixels.uniqueColors +
        ', ink=' +
        result.pixels.inkRatio +
        ', blank=' +
        result.blank +
        ', nodes=' +
        result.probe.nodeCount +
        ', text=' +
        result.probe.textLength +
        ', broken=' +
        result.probe.looksBroken +
        ')\n'
    );
  }
  process.stdout.write('[desktop] report ' + reportPath + '\n');

  const anyBroken = results.some(
    (result) =>
      !result.loadedOk ||
      result.probe.looksBroken ||
      result.blank ||
      result.loadFailures.length > 0
  );
  return anyBroken ? 1 : 0;
}

// Poll the renderer for its pathname. This is what turns "the menu works"
// from a claim into an observation: the menu item is clicked for real and the
// window is then asked where it ended up.
function waitForPathname(window, expected, timeoutMs) {
  return new Promise((resolve) => {
    const started = Date.now();
    const tick = async () => {
      let pathname = null;
      try {
        pathname = await window.webContents.executeJavaScript('location.pathname');
      } catch (error) {
        pathname = null;
      }
      if (pathname === expected) return resolve({ ok: true, pathname });
      if (Date.now() - started > timeoutMs) return resolve({ ok: false, pathname });
      setTimeout(tick, 200);
    };
    tick();
  });
}

// Headless self-check for slice 1.2: menu structure, real menu-driven
// navigation, tray construction. Prints one JSON blob and exits 0/1, so the
// shell's chrome is verifiable without anybody looking at a screen.
async function runSelfcheckMode(baseUrl) {
  const menu = Menu.getApplicationMenu();
  const menuReport = { built: Boolean(menu), topLevel: [], routeItems: [] };
  if (menu) {
    menuReport.topLevel = menu.items.map((item) => item.label);
    menuReport.routeItems = ROUTES.map((entry) => {
      const item = menu.getMenuItemById(entry.id);
      return { id: entry.id, present: Boolean(item), label: item ? item.label : null };
    });
  }

  const window = new BrowserWindow({
    show: false,
    width: SHOTS_WIDTH,
    height: SHOTS_HEIGHT,
    webPreferences: {
      offscreen: true,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow = window;

  const start = baseUrl.replace(/\/+$/, '') + '/home';
  await window.webContents.loadURL(start);
  await sleep(SHOTS_SETTLE_MS);

  const navigation = [];
  for (const entry of ROUTES) {
    const item = menu ? menu.getMenuItemById(entry.id) : null;
    if (!item) {
      navigation.push({ id: entry.id, clicked: false, ok: false, reason: 'menu item missing' });
      continue;
    }
    const before = await window.webContents.executeJavaScript('location.pathname');
    item.click();
    const waited = await waitForPathname(window, entry.route, 8000);
    navigation.push({
      id: entry.id,
      clicked: true,
      expected: entry.route,
      before,
      after: waited.pathname,
      ok: waited.ok,
    });
  }

  let trayReport;
  try {
    const trayMenu = createTray();
    const ids = ['tray-show', ...ROUTES.map((entry) => 'tray-' + entry.id), 'tray-quit'];
    trayReport = {
      created: true,
      template: true,
      menuItemsPresent: ids.filter((id) => Boolean(trayMenu.getMenuItemById(id))),
      menuItemsExpected: ids,
    };
  } catch (error) {
    trayReport = { created: false, error: error.message };
  }

  window.destroy();
  mainWindow = null;
  if (tray) {
    tray.destroy();
    tray = null;
  }

  const ok =
    menuReport.built &&
    menuReport.routeItems.every((item) => item.present) &&
    navigation.every((entry) => entry.ok) &&
    trayReport.created;

  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    singleInstanceLock: { acquired: true },
    menu: menuReport,
    menuNavigation: navigation,
    tray: trayReport,
    ok,
  };
  process.stdout.write('[desktop] selfcheck ' + JSON.stringify(report, null, 2) + '\n');
  return ok ? 0 : 1;
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();

if (!gotSingleInstanceLock) {
  // A second instance must not spawn a second ui-host: it would bind another
  // port and fork the state the first window is already showing.
  process.stdout.write('[desktop] already running; handing over to the running instance\n');
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(async () => {
    let exitCode = 0;
    try {
      host = spawnHost();
      const baseUrl = await waitForServing(host);
      currentBaseUrl = baseUrl;
      process.stdout.write('[desktop] serving at ' + baseUrl + '\n');
      if (SCREENSHOT_MODE) {
        exitCode = await runScreenshotMode(baseUrl);
      } else {
        buildApplicationMenu();
        if (SELFCHECK_MODE) {
          exitCode = await runSelfcheckMode(baseUrl);
        } else {
          createWindow(baseUrl);
          try {
            createTray();
          } catch (error) {
            // No menu bar to sit in (headless/SSH session) is not a reason to
            // refuse to run: the window works, only the tray is missing.
            process.stderr.write('[desktop] tray unavailable: ' + error.message + '\n');
          }
          return; // stay alive until the window closes
        }
      }
    } catch (error) {
      process.stderr.write('[desktop] ' + error.message + '\n');
      exitCode = 1;
    }
    await stopHost();
    app.exit(exitCode);
  });
}

app.on('window-all-closed', async () => {
  await stopHost();
  app.quit();
});

// Best-effort backstop: if Electron is killed outright the child would
// otherwise outlive it. Known limitation is recorded on the roadmap slice
// 1-1-1; a supervisor-level guard belongs to a later slice.
process.on('exit', () => {
  if (host && host.exitCode === null) host.kill('SIGKILL');
});
