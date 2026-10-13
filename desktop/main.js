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

const { app, BrowserWindow } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

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

// Screenshot mode must not touch the real user-data directory: it is a
// verification run, and on a locked-down host Electron's shutdown cleanup of
// ~/Library/Application Support can be denied, which turns a successful run
// into a non-zero exit. Keeping the profile next to the PNGs makes the run
// self-contained and its exit code mean "were the views broken".
if (SCREENSHOT_MODE) {
  app.setPath('userData', path.join(SHOTS_DIR, '_userdata'));
}

let host = null;
let hostStopping = false;

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
  window.loadURL(baseUrl);
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

app.whenReady().then(async () => {
  let exitCode = 0;
  try {
    host = spawnHost();
    const baseUrl = await waitForServing(host);
    process.stdout.write('[desktop] serving at ' + baseUrl + '\n');
    if (SCREENSHOT_MODE) {
      exitCode = await runScreenshotMode(baseUrl);
    } else {
      createWindow(baseUrl);
      return; // stay alive until the window closes
    }
  } catch (error) {
    process.stderr.write('[desktop] ' + error.message + '\n');
    exitCode = 1;
  }
  await stopHost();
  app.exit(exitCode);
});

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
