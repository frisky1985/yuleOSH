/**
 * static-server.test.js — 生产静态文件服务器集成测试
 *
 * @tests desktop/main.js
 * @req SHALL-253
 *
 * 依赖 frontend/out（npm run build 产物）；未构建时自动跳过。
 */

/* eslint-disable */

const http = require('http');
const fs = require('fs');
const path = require('path');

jest.mock('electron', () => {
  const events = require('events');
  return {
    app: {
      name: 'yuleOSH',
      getVersion: () => '0.1.0-test',
      getPath: jest.fn(() => '/tmp/yuleosh-test'),
      on: jest.fn(),
      whenReady: jest.fn(() => Promise.resolve()),
      requestSingleInstanceLock: jest.fn(() => true),
      quit: jest.fn(),
      exit: jest.fn(),
      isQuitting: false,
    },
    BrowserWindow: class extends events.EventEmitter {},
    Menu: { buildFromTemplate: jest.fn(() => ({})), setApplicationMenu: jest.fn() },
    MenuItem: jest.fn(),
    dialog: { showOpenDialog: jest.fn(), showSaveDialog: jest.fn(), showMessageBox: jest.fn() },
    ipcMain: { on: jest.fn(), handle: jest.fn() },
    shell: { openExternal: jest.fn() },
    session: { defaultSession: { setPermissionRequestHandler: jest.fn(), setPermissionCheckHandler: jest.fn() } },
    Tray: jest.fn(() => ({ setToolTip: jest.fn(), setContextMenu: jest.fn(), on: jest.fn(), destroy: jest.fn() })),
    nativeImage: { createFromPath: jest.fn(() => ({ isEmpty: () => false, setTemplateImage: jest.fn(), resize: jest.fn() })), createEmpty: jest.fn(() => ({})) },
  };
}, { virtual: true });

const main = require('../main');

const OUT_DIR = path.resolve(__dirname, '..', '..', 'frontend', 'out');
const hasBuild = fs.existsSync(path.join(OUT_DIR, 'index.html'));
const describeIfBuilt = hasBuild ? describe : describe.skip;

function request(port, requestPath) {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: '127.0.0.1', port, path: requestPath }, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
    });
    req.on('error', reject);
  });
}

describeIfBuilt('生产静态文件服务器', () => {
  let port;

  beforeAll(async () => {
    port = await main.startLocalFileServer();
  });

  afterAll(async () => {
    await main.stopLocalFileServer();
  });

  test('/desktop 返回 HTML 且带 CSP 与安全响应头', async () => {
    const res = await request(port, '/desktop');
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toContain('text/html');
    expect(res.headers['content-security-policy']).toContain("default-src 'self'");
    expect(res.headers['content-security-policy']).toContain("frame-ancestors 'none'");
    expect(res.headers['x-content-type-options']).toBe('nosniff');
    expect(res.headers['x-frame-options']).toBe('DENY');
    expect(res.body).toContain('<html');
  });

  test('根路径回退到 index.html', async () => {
    const res = await request(port, '/');
    expect(res.status).toBe(200);
    expect(res.body).toContain('<html');
  });

  test('路径穿越被拒绝', async () => {
    const res = await request(port, '/../../package.json');
    expect([403, 404]).toContain(res.status);
    expect(res.body).not.toContain('"name": "desktop"');
  });

  test('关闭后端口不可访问', async () => {
    await main.stopLocalFileServer();
    await expect(request(port, '/desktop')).rejects.toBeTruthy();
    port = await main.startLocalFileServer();
  });
});
