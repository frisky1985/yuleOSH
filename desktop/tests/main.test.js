/**
 * main.test.js — main.js 模块级测试（AC-1.x 窗口管理）
 *
 * 验证：
 *   - AC-1.1.2: 默认窗口尺寸 1280×860
 *   - AC-1.1.3: 窗口标题 "yuleOSH"
 *   - AC-1.2.2: contextIsolation=true, nodeIntegration=false
 *   - AC-1.3.1: 加载 frontend/out/ 静态文件路径正确
 *   - AC-4.1.1: 应用菜单构造
 *
 * @req REQ-006
 */
/* eslint-disable */

const path = require('path');

// Mock BrowserWindow 构造参数存储
const mockBrowserWindowCalls = [];

// jest.mock 工厂函数不能引用外部作用域变量，
// 但可以引用 mock- 前缀的变量
const mockWinEventMap = {};

// Mock Electron 模块 — 必须在任何 require 之前
jest.mock('electron', () => {
  const events = require('events');

  class MockBrowserWindow extends events.EventEmitter {
    constructor(options) {
      super();
      mockBrowserWindowCalls.push(options);
      this.webContents = Object.assign(new events.EventEmitter(), {
        send: jest.fn(),
        toggleDevTools: jest.fn(),
        setWindowOpenHandler: jest.fn(),
        getURL: jest.fn(() => ''),
      });
      this._options = options;
      this._visible = true;
      this._maximized = false;
    }
    loadURL = jest.fn();
    loadFile = jest.fn();
    show = jest.fn();
    hide = jest.fn();
    focus = jest.fn();
    isVisible = jest.fn(() => this._visible);
    isMaximized = jest.fn(() => this._maximized);
    maximize = jest.fn(() => { this._maximized = true; });
    unmaximize = jest.fn(() => { this._maximized = false; });
    minimize = jest.fn();
    close = jest.fn();
    reload = jest.fn();
  }

  return {
    app: {
      name: 'yuleOSH',
      getVersion: () => '0.1.0-test',
      isQuitting: false,
      on: jest.fn(),
      whenReady: jest.fn(() => Promise.resolve()),
      getPath: jest.fn((name) => `/mock/userData/${name}`),
      requestSingleInstanceLock: jest.fn(() => true),
      quit: jest.fn(),
      exit: jest.fn(),
    },
    BrowserWindow: MockBrowserWindow,
    Menu: {
      buildFromTemplate: jest.fn(() => ({})),
      setApplicationMenu: jest.fn(),
    },
    MenuItem: jest.fn(),
    dialog: {
      showOpenDialog: jest.fn(() => Promise.resolve({ canceled: true, filePaths: [] })),
      showSaveDialog: jest.fn(() => Promise.resolve({ canceled: true, filePath: null })),
      showMessageBox: jest.fn(),
    },
    ipcMain: {
      on: jest.fn(),
      handle: jest.fn(),
    },
    Tray: jest.fn().mockImplementation(() => ({
      setToolTip: jest.fn(),
      setContextMenu: jest.fn(),
      on: jest.fn(),
      destroy: jest.fn(),
    })),
    nativeImage: {
      createFromPath: jest.fn(() => ({
        isEmpty: () => false,
        setTemplateImage: jest.fn(),
        resize: jest.fn(() => ({})),
      })),
      createEmpty: jest.fn(() => ({})),
    },
    shell: {
      openExternal: jest.fn(),
    },
  };
}, { virtual: true });

const main = require('../main');
const { Menu } = require('electron');

// ─── AC-1.x 窗口管理 ───────────────────────────────

describe('AC-1.x — 窗口管理', () => {

  test('AC-1.1.2: 默认窗口尺寸 1280×860，可缩放', async () => {
    await main.createWindow();

    expect(mockBrowserWindowCalls.length).toBeGreaterThan(0);
    const opts = mockBrowserWindowCalls[0];
    expect(opts.width).toBe(1280);
    expect(opts.height).toBe(860);
    // 无 resizable: false → 可缩放
    expect(opts).not.toHaveProperty('resizable');
    expect(opts.minWidth).toBe(900);
    expect(opts.minHeight).toBe(600);
  });

  test('AC-1.1.3: 标题栏 "yuleOSH"', () => {
    const opts = mockBrowserWindowCalls[0];
    expect(opts.title).toBe('yuleOSH');
  });

  test('AC-1.2.2: contextIsolation=true + nodeIntegration=false', () => {
    const opts = mockBrowserWindowCalls[0];
    expect(opts.webPreferences.contextIsolation).toBe(true);
    expect(opts.webPreferences.nodeIntegration).toBe(false);
  });

  test('AC-1.3.1: 前端构建目录存在或给出明确构建提示', async () => {
    const desktopDir = path.resolve(__dirname, '..');
    const expectedOutDir = path.resolve(desktopDir, '..', 'frontend', 'out');
    const fs = require('fs');
    if (fs.existsSync(expectedOutDir)) {
      expect(fs.existsSync(path.join(expectedOutDir, 'index.html'))).toBe(true);
      return;
    }
    // 仓库源码目录通常不含构建产物：应 fail-fast 并提示构建命令
    await expect(main.startLocalFileServer()).rejects.toThrow('Frontend build not found');
  });
});

// ── AC-4.x 应用菜单 ───────────────────────────────

describe('AC-4.x — 应用菜单', () => {

  test('AC-4.1.1: buildAppMenu 生成菜单并注册', () => {
    main.buildAppMenu();
    expect(Menu.buildFromTemplate).toHaveBeenCalled();
    expect(Menu.setApplicationMenu).toHaveBeenCalled();
  });
});
