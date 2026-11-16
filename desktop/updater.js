/**
 * updater.js — 自动更新接线（electron-updater）
 *
 * @req SHALL-253
 *
 * 只有在打包版中才启用：开发/测试运行没有 app-update.yml，检查必然失败。
 * 更新失败一律降级为日志，绝不阻塞应用启动或退出。
 *
 * 可通过 YULEOSH_DISABLE_UPDATE=1 临时禁用（排障 / 离线环境）。
 */

'use strict';

const DISABLE_ENV = 'YULEOSH_DISABLE_UPDATE';

/**
 * @param {object} [options]
 * @param {Electron.App} [options.app]            用于判断 app.isPackaged
 * @param {object} [options.logger]               文件日志（info/warn/error）
 * @param {object} [options.autoUpdater]          仅测试注入，生产从 electron-updater 惰性加载
 * @returns {object|null} autoUpdater 实例；未启用时返回 null
 */
function initAutoUpdater({ app, logger, autoUpdater } = {}) {
  const log = (level, message) => {
    if (logger && typeof logger[level] === 'function') {
      logger[level](message);
    } else if (level === 'error') {
      console.error(message);
    } else if (level === 'warn') {
      console.warn(message);
    } else {
      console.log(message);
    }
  };

  if (!app || !app.isPackaged) {
    log('info', '[Updater] Skipped: not a packaged build');
    return null;
  }
  if (process.env[DISABLE_ENV] === '1') {
    log('info', `[Updater] Skipped: ${DISABLE_ENV}=1`);
    return null;
  }

  let updater = autoUpdater;
  if (!updater) {
    try {
      ({ autoUpdater: updater } = require('electron-updater'));
    } catch (err) {
      log('warn', `[Updater] Unavailable: ${err.message}`);
      return null;
    }
  }

  updater.logger = logger || console;
  updater.autoDownload = true;
  updater.autoInstallOnAppQuit = true;

  updater.on('checking-for-update', () => {
    log('info', '[Updater] Checking for updates');
  });
  updater.on('update-available', (info) => {
    log('info', `[Updater] Update available: ${info && info.version}`);
  });
  updater.on('update-not-available', () => {
    log('info', '[Updater] Already up to date');
  });
  updater.on('update-downloaded', (info) => {
    log('info', `[Updater] ${info && info.version} downloaded, will install on quit`);
  });
  updater.on('error', (err) => {
    log('warn', `[Updater] Update failed (non-fatal): ${err && err.message}`);
  });

  const reportFailure = (err) => {
    log('warn', `[Updater] Check failed (non-fatal): ${err && err.message}`);
  };

  try {
    const pending = updater.checkForUpdatesAndNotify();
    if (pending && typeof pending.catch === 'function') {
      pending.catch(reportFailure);
    }
  } catch (err) {
    reportFailure(err);
  }

  return updater;
}

module.exports = { initAutoUpdater };
