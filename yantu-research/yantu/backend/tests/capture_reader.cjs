const { execFileSync, spawn } = require('node:child_process');
const { createHash, randomBytes } = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const port = Number(process.env.READER_DEBUG_PORT || 9333);
const baseUrl = process.env.READER_BASE_URL || 'http://127.0.0.1:8089';
const resourceId = process.env.READER_RESOURCE_ID;
const userId = process.env.READER_USER_ID;
const container = process.env.READER_CONTAINER || 'yantu-lxc-lab-research-1';
const viewportWidth = Number(process.env.READER_WIDTH || 1600);
const viewportHeight = Number(process.env.READER_HEIGHT || 1000);
const output =
  process.env.READER_OUTPUT ||
  path.join(process.cwd(), 'reader-desktop.png');
const edge =
  process.env.READER_BROWSER ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

if (!resourceId || !userId) {
  throw new Error('READER_RESOURCE_ID and READER_USER_ID are required');
}

const token = randomBytes(32).toString('base64url');
const digest = createHash('sha256').update(token).digest('hex');
const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();
const python = `
import os, psycopg
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(url) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into yt_sessions(token_hash,user_id,expires_at) values (%s,%s,%s)",
            (os.sys.argv[1], os.sys.argv[2], os.sys.argv[3]),
        )
`;
const removeToken = `
import os, psycopg
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(url) as connection:
    with connection.cursor() as cursor:
        cursor.execute("delete from yt_sessions where token_hash=%s", (os.sys.argv[1],))
`;

execFileSync(
  'docker',
  ['exec', container, 'python', '-c', python, digest, userId, expiresAt],
  { stdio: 'pipe' },
);

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'yantu-reader-edge-'));
const browser = spawn(
  edge,
  [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--disable-gpu',
    '--hide-scrollbars',
    `--window-size=${viewportWidth},${viewportHeight}`,
    'about:blank',
  ],
  { windowsHide: true, stdio: 'ignore' },
);

async function waitForJson(url) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.json();
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error('Browser DevTools did not start');
}

async function main() {
  await waitForJson(`http://127.0.0.1:${port}/json/version`);
  const target = await (
    await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
      method: 'PUT',
    })
  ).json();
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = reject;
  });
  let nextId = 0;
  const pending = new Map();
  const consoleMessages = [];
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.consoleAPICalled') {
      consoleMessages.push(
        message.params.args
          .map((argument) => argument.value ?? argument.description ?? '')
          .join(' '),
      );
    }
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  };
  const command = (method, params = {}) => {
    const id = ++nextId;
    socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
    });
  };
  await command('Page.enable');
  await command('Network.enable');
  await command('Runtime.enable');
  await command('Network.setCookie', {
    name: 'yantu_session',
    value: token,
    url: baseUrl + '/',
    path: '/',
    httpOnly: true,
    sameSite: 'Lax',
  });
  await command('Page.navigate', {
    url: `${baseUrl}/reader.html?id=${encodeURIComponent(resourceId)}`,
  });
  await new Promise((resolve) => setTimeout(resolve, 9000));
  const evaluation = await command('Runtime.evaluate', {
    expression: `(() => {
      const frame = document.querySelector('#viewer');
      const app = frame?.contentWindow?.PDFViewerApplication;
      const toolbar = frame?.contentDocument?.querySelector('#toolbarContainer');
      return {
        title: document.title,
        titleText: document.querySelector('#title')?.textContent,
        pageCount: document.querySelector('#pageCount')?.textContent,
        pageInput: document.querySelector('#pageInput')?.value,
        outlineItems: document.querySelectorAll('.outline-item').length,
        thumbnailItems: document.querySelectorAll('.page-thumbnail').length,
        noteVisible: !document.body.classList.contains('notes-closed'),
        navVisible: !document.body.classList.contains('nav-closed'),
        pdfLoaded: Boolean(app?.pdfDocument),
        pdfToolbarHidden: toolbar ? getComputedStyle(toolbar).display === 'none' : false,
        error: document.querySelector('#errorState')?.hidden === false
          ? document.querySelector('#errorMessage')?.textContent
          : ''
      };
    })()`,
    returnByValue: true,
    awaitPromise: true,
  });
  const screenshot = await command('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false,
  });
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, Buffer.from(screenshot.data, 'base64'));
  await command('Runtime.evaluate', {
    expression:
      "document.querySelector('[data-navigation=pages]')?.click()",
  });
  await new Promise((resolve) => setTimeout(resolve, 5000));
  const thumbnails = await command('Runtime.evaluate', {
    expression: `({
      thumbnails: document.querySelectorAll('.page-thumbnail').length,
      renderedThumbnails: [...document.querySelectorAll('.page-thumbnail canvas')]
        .filter(canvas => canvas.width > 110).length
    })`,
    returnByValue: true,
  });
  const thumbnailShot = await command('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false,
  });
  const parsed = path.parse(output);
  const thumbnailOutput = path.join(
    parsed.dir,
    `${parsed.name}-pages${parsed.ext || '.png'}`,
  );
  fs.writeFileSync(
    thumbnailOutput,
    Buffer.from(thumbnailShot.data, 'base64'),
  );
  socket.close();
  return {
    metrics: evaluation.result.value,
    thumbnailMetrics: thumbnails.result.value,
    consoleMessages,
    output,
    thumbnailOutput,
  };
}

main()
  .then((result) => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(() => {
    browser.kill();
    try {
      execFileSync(
        'docker',
        ['exec', container, 'python', '-c', removeToken, digest],
        { stdio: 'pipe' },
      );
    } catch {}
    setTimeout(() => {
      if (!profile.startsWith(os.tmpdir())) return;
      try {
        fs.rmSync(profile, { recursive: true, force: true });
      } catch {}
    }, 1000);
  });
