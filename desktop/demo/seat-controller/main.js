/**
 * 座椅控制器 — Electron 主进程入口
 *
 * 基于 yuleOSH Desktop 的进程结构（主进程 + preload + 静态渲染页），
 * 独立运行、独立打包，用于演示车载座椅的姿态与舒适功能控制。
 *
 * 运行方式（复用 desktop 已安装的 Electron）:
 *   cd desktop && ./node_modules/.bin/electron demo/seat-controller
 */

const { app, BrowserWindow, ipcMain, Menu, shell } = require('electron');
const path = require('path');
const fs = require('fs');

const APP_NAME = '座椅控制器';
const STATE_LIMIT = 100 * 1024; // 状态文件上限 100KB，防止异常写入

app.setName(APP_NAME);

// ─── 本地持久化（记忆位置 / 上次姿态）────────────────────────

function storePath() {
  return path.join(app.getPath('userData'), 'seat-state.json');
}

function readState() {
  try {
    return JSON.parse(fs.readFileSync(storePath(), 'utf8'));
  } catch {
    return null;
  }
}

function writeState(state) {
  const payload = JSON.stringify(state, null, 2);
  if (payload.length > STATE_LIMIT) {
    throw new Error('state payload too large');
  }
  fs.mkdirSync(path.dirname(storePath()), { recursive: true });
  fs.writeFileSync(storePath(), payload, 'utf8');
  return { ok: true, path: storePath() };
}

// ─── 窗口 ──────────────────────────────────────────────────

/** @type {BrowserWindow|null} */
let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 1000,
    minHeight: 680,
    title: APP_NAME,
    backgroundColor: '#0a1017',
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // 外部链接交给系统浏览器，避免在应用内打开
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ─── 菜单（保留复制/缩放/开发者工具等基础能力）────────────────

function buildMenu() {
  const template = [
    {
      label: '视图',
      submenu: [
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: '编辑',
      submenu: [{ role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ─── 启动 ──────────────────────────────────────────────────

app.whenReady().then(() => {
  ipcMain.handle('seat:load', () => readState());
  ipcMain.handle('seat:save', (_event, state) => writeState(state));

  buildMenu();
  createWindow();

  // 无头冒烟模式：--screenshot=<file> 渲染完成后截图并退出
  const shotArg = process.argv.find((arg) => arg.startsWith('--screenshot='));
  if (shotArg) {
    const target = shotArg.slice('--screenshot='.length);
    mainWindow.webContents.once('did-finish-load', () => {
      setTimeout(async () => {
        try {
          const image = await mainWindow.webContents.capturePage();
          fs.mkdirSync(path.dirname(path.resolve(target)), { recursive: true });
          fs.writeFileSync(path.resolve(target), image.toPNG());
          console.log(`[SeatController] screenshot saved: ${path.resolve(target)}`);
        } catch (err) {
          console.error(`[SeatController] screenshot failed: ${err.message}`);
        } finally {
          app.quit();
        }
      }, 1500);
    });
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
