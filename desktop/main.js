/**
 * main.js — yuleOSH Desktop 主进程入口
 *
 * 职责:
 *   - Electron 应用生命周期管理
 *   - BrowserWindow 创建/管理
 *   - 内嵌静态文件服务器 (生产模式)
 *   - 应用菜单
 *   - IPC 通信
 *   - 协调 ServerManager + TrayManager
 */

const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');
const path = require('path');
const http = require('http');
const fs = require('fs');
const url = require('url');

const ServerManager = require('./server-manager');
const TrayManager = require('./tray');

// ─── 常量 ────────────────────────────────────────────

const DEV_MODE = process.env.ELECTRON_DEV === 'true';
const DEV_SERVER_PORT = 3000;
const BACKEND_PORT = 18788;
const LOCAL_SERVER_PORT = 18789; // 用于生产模式静态文件服务
const FRONTEND_OUT_DIR = path.resolve(__dirname, '..', 'frontend', 'out');

// ─── 状态 ────────────────────────────────────────────

/** @type {Electron.BrowserWindow|null} */
let mainWindow = null;

/** @type {import('./server-manager')|null} */
let serverManager = null;

/** @type {import('./tray')|null} */
let trayManager = null;

/** @type {http.Server|null} */
let localFileServer = null;

// ─── 应用菜单 ────────────────────────────────────────

function buildAppMenu() {
  const isMac = process.platform === 'darwin';

  const template = [
    // macOS 应用菜单
    ...(isMac ? [{
      label: app.name,
      submenu: [
        { role: 'about', label: '关于 yuleOSH' },
        { type: 'separator' },
        {
          label: '偏好设置...',
          accelerator: 'Cmd+,',
          click: () => {
            // 未来: 打开设置页面
            if (mainWindow) {
              mainWindow.webContents.send('navigate', '/settings');
            }
          },
        },
        { type: 'separator' },
        { role: 'services', label: '服务' },
        { type: 'separator' },
        { role: 'hide', label: '隐藏 yuleOSH' },
        { role: 'hideOthers', label: '隐藏其他' },
        { role: 'unhide', label: '显示全部' },
        { type: 'separator' },
        { role: 'quit', label: '退出 yuleOSH' },
      ],
    }] : []),

    // 文件菜单
    {
      label: '文件',
      submenu: [
        {
          label: '新建项目...',
          accelerator: isMac ? 'Cmd+N' : 'Ctrl+N',
          click: () => openCreateProject(),
        },
        {
          label: '打开项目...',
          accelerator: isMac ? 'Cmd+O' : 'Ctrl+O',
          click: () => openProjectDialog(),
        },
        { type: 'separator' },
        {
          label: '退出',
          accelerator: isMac ? 'Cmd+Q' : 'Ctrl+Q',
          click: () => {
            app.isQuitting = true;
            app.quit();
          },
        },
      ],
    },

    // 编辑菜单
    {
      label: '编辑',
      submenu: [
        { role: 'undo', label: '撤销' },
        { role: 'redo', label: '重做' },
        { type: 'separator' },
        { role: 'cut', label: '剪切' },
        { role: 'copy', label: '复制' },
        { role: 'paste', label: '粘贴' },
        { role: 'selectAll', label: '全选' },
      ],
    },

    // 视图菜单
    {
      label: '视图',
      submenu: [
        {
          label: '重新加载',
          accelerator: isMac ? 'Cmd+R' : 'Ctrl+R',
          click: () => mainWindow && mainWindow.reload(),
        },
        {
          label: '开发者工具',
          accelerator: isMac ? 'Cmd+Alt+I' : 'Ctrl+Shift+I',
          click: () => mainWindow && mainWindow.webContents.toggleDevTools(),
        },
        { type: 'separator' },
        { role: 'resetZoom', label: '重置缩放' },
        { role: 'zoomIn', label: '放大' },
        { role: 'zoomOut', label: '缩小' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '全屏' },
      ],
    },

    // 窗口菜单
    {
      label: '窗口',
      submenu: [
        { role: 'minimize', label: '最小化' },
        { role: 'zoom', label: '缩放' },
        ...(isMac ? [
          { type: 'separator' },
          { role: 'front', label: '全部置于顶层' },
        ] : [
          { role: 'close', label: '关闭' },
        ]),
      ],
    },

    // 帮助菜单
    {
      label: '帮助',
      submenu: [
        {
          label: 'yuleOSH 文档',
          click: () => shell.openExternal('https://github.com/frisky1985/yuleOSH'),
        },
        {
          label: '反馈问题',
          click: () => shell.openExternal('https://github.com/frisky1985/yuleOSH/issues'),
        },
        { type: 'separator' },
        {
          label: '关于 yuleOSH',
          click: () => {
            dialog.showMessageBox({
              type: 'info',
              title: '关于 yuleOSH',
              message: `yuleOSH Desktop v${app.getVersion()}`,
              detail: '嵌入式AI开发全流程平台\nMIT License',
            });
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

// ─── 原生对话框 ──────────────────────────────────────

function openProjectDialog() {
  dialog.showOpenDialog(mainWindow, {
    title: '打开 yuleOSH 项目',
    properties: ['openDirectory'],
    buttonLabel: '选择项目目录',
  }).then((result) => {
    if (!result.canceled && result.filePaths.length > 0) {
      const projectPath = result.filePaths[0];
      if (mainWindow) {
        mainWindow.webContents.send('project-opened', projectPath);
      }
    }
  });
}

function openCreateProject() {
  dialog.showSaveDialog(mainWindow, {
    title: '创建新项目',
    defaultPath: 'my-yuleosh-project',
    buttonLabel: '创建',
    properties: ['createDirectory'],
  }).then((result) => {
    if (!result.canceled && result.filePath) {
      if (mainWindow) {
        mainWindow.webContents.send('create-project', result.filePath);
      }
    }
  });
}

// ─── 静态文件服务器 (生产模式) ────────────────────────

/**
 * 启动本地 HTTP 服务器，提供 frontend/out/ 静态文件
 * 处理 Next.js assetPrefix "/yuleOSH" 路径映射
 * @returns {Promise<number>} 服务器端口号
 */
function startLocalFileServer() {
  return new Promise((resolve, reject) => {
    // 检查前端构建目录是否存在
    if (!fs.existsSync(FRONTEND_OUT_DIR)) {
      reject(new Error(
        `Frontend build not found at ${FRONTEND_OUT_DIR}\n` +
        `Run 'cd frontend && npm run build' first`
      ));
      return;
    }

    const server = http.createServer((req, res) => {
      const parsedUrl = url.parse(req.url, true);
      let filePath = parsedUrl.pathname;

      // 处理 assetPrefix: 将 /yuleOSH/* → 去掉前缀
      if (filePath.startsWith('/yuleOSH/')) {
        filePath = filePath.slice('/yuleOSH'.length);
      }

      // 默认首页
      if (filePath === '/' || filePath === '') {
        filePath = '/index.html';
      }

      // ── Path traversal protection ────────────────────────────────────
      // Resolve the full path and verify it stays within FRONTEND_OUT_DIR.
      const fullPath = path.resolve(path.join(FRONTEND_OUT_DIR, filePath));
      if (!fullPath.startsWith(path.resolve(FRONTEND_OUT_DIR))) {
        res.writeHead(403, { 'Content-Type': 'text/plain' });
        res.end('Forbidden');
        return;
      }

      // 检查文件是否存在
      fs.stat(fullPath, (err, stats) => {
        if (err || !stats.isFile()) {
          // SPA fallback: 对 HTML 路由, 返回 index.html
          if (!filePath.includes('.')) {
            const indexPath = path.join(FRONTEND_OUT_DIR, 'index.html');
            // Also protect SPA fallback path
            const resolvedIndex = path.resolve(indexPath);
            if (!resolvedIndex.startsWith(path.resolve(FRONTEND_OUT_DIR))) {
              res.writeHead(403, { 'Content-Type': 'text/plain' });
              res.end('Forbidden');
              return;
            }
            serveFile(res, resolvedIndex);
          } else {
            res.writeHead(404, { 'Content-Type': 'text/plain' });
            res.end('Not Found');
          }
          return;
        }

        serveFile(res, fullPath);
      });
    });

    server.on('error', (err) => {
      if (err.code === 'EADDRINUSE') {
        // 端口被占用，尝试下一个
        console.warn(`[FileServer] Port ${LOCAL_SERVER_PORT} in use, trying ${LOCAL_SERVER_PORT + 1}`);
        server.listen(LOCAL_SERVER_PORT + 1);
      } else {
        reject(err);
      }
    });

    server.on('listening', () => {
      const addr = server.address();
      localFileServer = server;
      console.log(`[FileServer] Serving frontend on http://localhost:${addr.port}`);
      resolve(addr.port);
    });

    server.listen(LOCAL_SERVER_PORT);
  });
}

/**
 * 发送文件内容
 */
function serveFile(res, fullPath) {
  const ext = path.extname(fullPath).toLowerCase();
  const mimeTypes = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.txt': 'text/plain; charset=utf-8',
    '.map': 'application/json',
  };

  const contentType = mimeTypes[ext] || 'application/octet-stream';

  fs.readFile(fullPath, (err, data) => {
    if (err) {
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end('Internal Server Error');
      return;
    }
    res.writeHead(200, {
      'Content-Type': contentType,
      'Cache-Control': ext === '.html' ? 'no-cache' : 'max-age=31536000',
    });
    res.end(data);
  });
}

// ─── 创建窗口 ────────────────────────────────────────

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: 'yuleOSH',
    icon: path.resolve(__dirname, 'assets', 'icon.png'),
    show: false,
    backgroundColor: '#0a0e17', // 与前端背景色一致, 防止白闪
    webPreferences: {
      preload: path.resolve(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false, // 需要 preload 使用 Node.js API
    },
  });

  // 窗口可见后显示 (防止白闪)
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // 关闭按钮行为: 隐藏到托盘 (macOS 行为)
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  // 窗口显示/隐藏时更新托盘菜单
  mainWindow.on('show', () => {
    if (trayManager) {
      trayManager.notifyWindowStateChanged();
    }
  });
  mainWindow.on('hide', () => {
    if (trayManager) {
      trayManager.notifyWindowStateChanged();
    }
  });

  // 窗口打开后创建托盘
  mainWindow.once('show', () => {
    createTray();
  });

  // 创建应用菜单
  buildAppMenu();

  // 注册 IPC 处理器
  registerIpcHandlers();
}

// ─── 加载前端 ────────────────────────────────────────

async function loadFrontend() {
  if (DEV_MODE) {
    // 开发模式: 加载 Next.js dev server
    const devUrl = `http://localhost:${DEV_SERVER_PORT}`;
    console.log(`[Main] DEV mode — loading from ${devUrl}`);
    console.log(`[Main] Make sure to run 'cd frontend && npm run dev' first`);
    mainWindow.loadURL(devUrl);
  } else {
    // 生产模式: 加载本地静态文件服务器
    try {
      const port = await startLocalFileServer();
      const url = `http://localhost:${port}/`;
      console.log(`[Main] PROD mode — loading from ${url}`);
      mainWindow.loadURL(url);
    } catch (err) {
      console.error(`[Main] Failed to start file server: ${err.message}`);
      // 显示错误页面
      showErrorPage(err.message);
    }
  }
}

/**
 * 显示错误页面
 */
function showErrorPage(message) {
  const escaped = message.replace(/</g, '&lt;').replace(/>/g, '&gt;');
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <title>yuleOSH — 启动错误</title>
      <style>
        body {
          background: #0a0e17;
          color: #e2e8f0;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          margin: 0;
          padding: 20px;
        }
        .error-card {
          max-width: 500px;
          text-align: center;
        }
        .error-icon {
          font-size: 48px;
          margin-bottom: 16px;
        }
        h1 {
          font-size: 20px;
          color: #ff4d4f;
          margin-bottom: 12px;
        }
        p {
          color: #94a3b8;
          font-size: 14px;
          line-height: 1.6;
        }
        code {
          background: #1e293b;
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 13px;
          color: #10b981;
          word-break: break-all;
        }
        .retry-btn {
          display: inline-block;
          margin-top: 20px;
          padding: 10px 24px;
          border-radius: 8px;
          background: linear-gradient(135deg, #722ed1, #1677ff);
          color: white;
          border: none;
          font-size: 14px;
          cursor: pointer;
        }
      </style>
    </head>
    <body>
      <div class="error-card">
        <div class="error-icon">⚠️</div>
        <h1>启动失败</h1>
        <p>${escaped}</p>
        <p>请确保已安装依赖并构建前端：</p>
        <p>
          <code>cd frontend && npm install && npm run build</code>
        </p>
        <button class="retry-btn" onclick="location.reload()">重试</button>
      </div>
    </body>
    </html>
  `)}`);
}

/**
 * 显示 Python 后端启动失败的错误页面
 */
function showBackendErrorPage(message) {
  const escaped = message.replace(/</g, '&lt;').replace(/>/g, '&gt;');
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <title>yuleOSH — 后端启动失败</title>
      <style>
        body {
          background: #0a0e17;
          color: #e2e8f0;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          margin: 0;
          padding: 20px;
        }
        .error-card {
          max-width: 560px;
          text-align: center;
        }
        .error-icon {
          font-size: 48px;
          margin-bottom: 16px;
        }
        h1 {
          font-size: 20px;
          color: #ff4d4f;
          margin-bottom: 12px;
        }
        p {
          color: #94a3b8;
          font-size: 14px;
          line-height: 1.6;
        }
        code {
          background: #1e293b;
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 13px;
          color: #10b981;
          word-break: break-all;
        }
        .retry-btn {
          display: inline-block;
          margin-top: 20px;
          padding: 10px 24px;
          border-radius: 8px;
          background: linear-gradient(135deg, #722ed1, #1677ff);
          color: white;
          border: none;
          font-size: 14px;
          cursor: pointer;
        }
      </style>
    </head>
    <body>
      <div class="error-card">
        <div class="error-icon">⚙️</div>
        <h1>Python 后端启动失败</h1>
        <p>无法启动 Python 后端服务。请确认：</p>
        <p>
          1. Python 3.10+ 已安装<br>
          2. yuleosh 已安装：<code>pip install yuleosh</code><br>
          3. 端口 18788 未被占用
        </p>
        <p><code>${escaped}</code></p>
        <button class="retry-btn" onclick="location.reload()">重试</button>
      </div>
    </body>
    </html>
  `)}`);
}

// ─── 创建托盘 ────────────────────────────────────────

function createTray() {
  if (trayManager) {
    return;
  }
  trayManager = new TrayManager(mainWindow);
  trayManager.create();
}

// ─── IPC 处理器 ──────────────────────────────────────

function registerIpcHandlers() {
  // 获取后端 URL (同步)
  ipcMain.on('get-backend-url', (event) => {
    const url = serverManager ? serverManager.getBackendUrl() : `http://localhost:${BACKEND_PORT}`;
    event.returnValue = url;
  });

  // 打开目录选择对话框
  ipcMain.handle('open-directory', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '选择项目目录',
      properties: ['openDirectory'],
    });
    return result.canceled ? null : result.filePaths[0];
  });

  // 获取应用版本
  ipcMain.handle('get-app-version', () => {
    return app.getVersion();
  });
}

// ─── 后端健康检查 ────────────────────────────────────

/**
 * 轮询后端健康检查端点直到就绪 (AR-P1-03)。
 * @param {string} url - 健康检查 URL
 * @param {number} timeoutMs - 超时毫秒
 * @param {number} intervalMs - 轮询间隔毫秒
 * @returns {Promise<void>}
 */
function waitForBackend(url, timeoutMs = 15000, intervalMs = 500) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    function poll() {
      if (Date.now() - start > timeoutMs) {
        reject(new Error('Backend health check timed out'));
        return;
      }
      const req = http.get(url, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          setTimeout(poll, intervalMs);
        }
      });
      req.on('error', () => {
        // Backend not ready yet — retry
        setTimeout(poll, intervalMs);
      });
      req.setTimeout(2000, () => {
        req.destroy();
        setTimeout(poll, intervalMs);
      });
    }
    poll();
  });
}

// ─── 信号转发 ────────────────────────────────────────

/**
 * 将 ServerManager 的事件转发到渲染进程
 */
function wireBackendEvents() {
  if (!serverManager) return;

  serverManager.on('healthy', () => {
    console.log('[Main] Backend healthy — sending to renderer');
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('backend-ready');
    }
  });

  serverManager.on('error', (err) => {
    console.error('[Main] Backend error:', err.message);
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('backend-error', err.message);
    }
  });

  serverManager.on('restarting', (attempt, max) => {
    console.warn(`[Main] Backend restarting (${attempt}/${max})...`);
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('backend-restarting', { attempt, max });
    }
  });

  serverManager.on('fatal', (code) => {
    console.error(`[Main] Backend fatal — max restart attempts exceeded, code=${code}`);
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('backend-fatal', '后端服务异常，请检查日志后重试');
    }
  });

  serverManager.on('stopped', (code) => {
    console.log(`[Main] Backend stopped with code ${code}`);
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('backend-stopped', code);
    }
  });
}

// ─── 启动 Python 后端 ────────────────────────────────

async function startBackend() {
  serverManager = new ServerManager({
    port: BACKEND_PORT,
  });

  wireBackendEvents();

  try {
    await serverManager.start();
    console.log('[Main] Python backend started successfully');
  } catch (err) {
    console.error('[Main] Failed to start backend:', err.message);

    // 健康检查超时或启动失败时由主进程直接加载错误页
    showBackendErrorPage(err.message);
  }
}

// ─── 应用生命周期 ────────────────────────────────────

app.whenReady().then(async () => {
  console.log(`[Main] yuleOSH Desktop v${app.getVersion()}`);
  console.log(`[Main] Platform: ${process.platform}`);
  console.log(`[Main] Dev mode: ${DEV_MODE}`);

  // 1. 创建窗口
  await createWindow();

  // 2. AR-P1-03: 先启动后端，等待健康检查通过后再加载 UI
  const healthCheckUrl = `http://localhost:${BACKEND_PORT}/api/health`;

  // Start backend (fires healthy event on success)
  startBackend();

  // Wait for backend health before UI loads
  try {
    await waitForBackend(healthCheckUrl, 15000, 500);
    console.log('[Main] Backend health check passed — loading UI');
    // Re-load the frontend now that backend is healthy
    await loadFrontend();
  } catch (err) {
    console.warn('[Main] Backend not ready in time — loading UI anyway');
    // Show backend-loading page or just load the frontend
    await loadFrontend();
  }

  // macOS: 点击 Dock 图标重新显示窗口
  app.on('activate', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.focus();
      } else {
        mainWindow.show();
      }
    } else {
      createWindow();
    }
  });
});

// 所有窗口关闭时 (macOS 除外)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    // Linux/Windows 托盘继续运行
    // 只有用户主动退出才关闭
  }
});

// 退出前清理
app.on('before-quit', async (event) => {
  if (!app.isQuitting) {
    app.isQuitting = true;
  }

  event.preventDefault();

  console.log('[Main] Shutting down...');

  // 1. 停止 Python 后端
  if (serverManager) {
    try {
      await serverManager.destroy();
    } catch (err) {
      console.error('[Main] Error stopping backend:', err.message);
    }
  }

  // 2. 销毁托盘
  if (trayManager) {
    trayManager.destroy();
  }

  // 3. 关闭静态文件服务器
  if (localFileServer) {
    await new Promise((resolve) => {
      localFileServer.close(resolve);
    });
    console.log('[Main] File server stopped');
  }

  // 4. 退出应用
  app.exit(0);
});

// ─── 导出 (用于测试) ──────────────────────────────

module.exports = {
  createWindow,
  startBackend,
  buildAppMenu,
  startLocalFileServer,
};
