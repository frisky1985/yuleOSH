/**
 * updater.test.js — 自动更新接线单元测试
 *
 * @req SHALL-253
 */

'use strict';

const { EventEmitter } = require('events');
const { initAutoUpdater } = require('../updater');

function fakeUpdater() {
  const updater = new EventEmitter();
  updater.checkForUpdatesAndNotify = jest.fn(() => Promise.resolve(null));
  return updater;
}

describe('initAutoUpdater', () => {
  const originalDisable = process.env.YULEOSH_DISABLE_UPDATE;

  afterEach(() => {
    if (originalDisable === undefined) {
      delete process.env.YULEOSH_DISABLE_UPDATE;
    } else {
      process.env.YULEOSH_DISABLE_UPDATE = originalDisable;
    }
  });

  test('未打包运行时跳过（避免 app-update.yml 缺失导致报错）', () => {
    const updater = fakeUpdater();
    const result = initAutoUpdater({
      app: { isPackaged: false },
      autoUpdater: updater,
    });
    expect(result).toBeNull();
    expect(updater.checkForUpdatesAndNotify).not.toHaveBeenCalled();
  });

  test('YULEOSH_DISABLE_UPDATE=1 时跳过', () => {
    process.env.YULEOSH_DISABLE_UPDATE = '1';
    const updater = fakeUpdater();
    const result = initAutoUpdater({
      app: { isPackaged: true },
      autoUpdater: updater,
    });
    expect(result).toBeNull();
    expect(updater.checkForUpdatesAndNotify).not.toHaveBeenCalled();
  });

  test('打包版启用下载与退出安装，并立即检查', () => {
    const updater = fakeUpdater();
    const logger = { info: jest.fn(), warn: jest.fn(), error: jest.fn() };
    const result = initAutoUpdater({
      app: { isPackaged: true },
      logger,
      autoUpdater: updater,
    });

    expect(result).toBe(updater);
    expect(updater.autoDownload).toBe(true);
    expect(updater.autoInstallOnAppQuit).toBe(true);
    expect(updater.checkForUpdatesAndNotify).toHaveBeenCalledTimes(1);
  });

  test('更新事件写入日志', () => {
    const updater = fakeUpdater();
    const logger = { info: jest.fn(), warn: jest.fn(), error: jest.fn() };
    initAutoUpdater({
      app: { isPackaged: true },
      logger,
      autoUpdater: updater,
    });

    updater.emit('update-available', { version: '4.3.0' });
    updater.emit('update-downloaded', { version: '4.3.0' });
    updater.emit('error', new Error('network down'));

    expect(logger.info).toHaveBeenCalledWith(
      expect.stringContaining('4.3.0')
    );
    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining('network down')
    );
  });

  test('检查更新失败不抛出（不阻塞启动）', async () => {
    const updater = fakeUpdater();
    updater.checkForUpdatesAndNotify = jest.fn(() =>
      Promise.reject(new Error('offline'))
    );
    const logger = { info: jest.fn(), warn: jest.fn(), error: jest.fn() };

    expect(() =>
      initAutoUpdater({ app: { isPackaged: true }, logger, autoUpdater: updater })
    ).not.toThrow();

    await Promise.resolve();
    await Promise.resolve();
    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining('offline')
    );
  });
});
