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
const builderConfigText = fs.readFileSync(
  path.resolve(__dirname, '..', 'electron-builder.yml'),
  'utf8'
);

afterAll(() => {
  process.resourcesPath = originalResourcesPath;
});

describe('AC-1.3.2 — 生产打包资源路径', () => {
  test('打包模式下前端目录指向 resources/frontend-out', () => {
    expect(main.FRONTEND_OUT_DIR).toBe(path.join('/mock/resources', 'frontend-out'));
  });

  test('extraResources 目标与运行时路径一致', () => {
    expect(builderConfigText).toMatch(/to:\s*frontend-out/);
    expect(builderConfigText).toMatch(/to:\s*backend/);
  });

  test('AC-5.1.4: 构建脚本包含内置 Python 运行时产物', () => {
    expect(builderConfigText).toMatch(/from:\s*build\/backend\/yuleosh-server/);

    const pkg = JSON.parse(
      fs.readFileSync(path.resolve(__dirname, '..', 'package.json'), 'utf8')
    );
    expect(pkg.scripts['build:backend']).toBe('node scripts/build-backend.js');
    expect(pkg.scripts['build:linux']).toContain('npm run build:backend');
    expect(pkg.scripts['build:mac']).toContain('npm run build:backend');
  });

  test('asar files 白名单包含全部本地依赖模块', () => {
    for (const module of ['main.js', 'preload.js', 'server-manager.js', 'tray.js', 'logger.js']) {
      expect(builderConfigText).toMatch(new RegExp(`-\\s*${module.replace('.', '\\.')}`));
    }
  });
});
