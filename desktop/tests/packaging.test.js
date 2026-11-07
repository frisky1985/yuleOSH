/**
 * packaging.test.js — 打包产物契约测试（AC-1.3.2 生产资源路径）
 *
 * @tests desktop/main.js
 * @req SHALL-253
 *
 * 验证 electron-builder 配置与运行时路径解析一致：
 *   - resources/frontend-out（extraResources 目标）与 main.js 打包路径一致
 *   - asar files 白名单包含 main.js 的全部本地依赖
 */

/* eslint-disable */

const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

jest.mock('electron', () => {
  const events = require('events');
  return {
    app: {
      name: 'yuleOSH',
      isPackaged: true,
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

const originalResourcesPath = process.resourcesPath;
process.resourcesPath = '/mock/resources';

const main = require('../main');
const builderConfig = yaml.load(
  fs.readFileSync(path.resolve(__dirname, '..', 'electron-builder.yml'), 'utf8')
);

afterAll(() => {
  process.resourcesPath = originalResourcesPath;
});

describe('AC-1.3.2 — 生产打包资源路径', () => {
  test('打包模式下前端目录指向 resources/frontend-out', () => {
    expect(main.FRONTEND_OUT_DIR).toBe(path.join('/mock/resources', 'frontend-out'));
  });

  test('extraResources 目标与运行时路径一致', () => {
    const target = builderConfig.extraResources.map((item) => item.to);
    expect(target).toContain('frontend-out');
  });

  test('asar files 白名单包含全部本地依赖模块', () => {
    const files = builderConfig.files;
    for (const module of ['main.js', 'preload.js', 'server-manager.js', 'tray.js', 'logger.js']) {
      expect(files).toContain(module);
    }
  });
});
