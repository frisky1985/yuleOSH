/**
 * crash-reporter.js — 崩溃转储与子进程异常观测
 *
 * @req SHALL-253
 *
 * 打包版默认只写本地 crash dumps（Electron 标准目录），不联网。
 * 配置 YULEOSH_CRASH_UPLOAD_URL 后才会把转储上报到该地址。
 * 任何初始化失败都只记日志，不影响应用启动。
 */

'use strict';

const UPLOAD_ENV = 'YULEOSH_CRASH_UPLOAD_URL';

/**
 * @param {object} [options]
 * @param {Electron.App} [options.app]
 * @param {Electron.CrashReporter} [options.crashReporter] 仅测试注入
 * @param {object} [options.logger]
 * @param {NodeJS.ProcessEnv} [options.env]
 * @returns {object|null}
 */
function initCrashReporter({ app, crashReporter, logger, env = process.env } = {}) {
  const log = (level, message) => {
    if (logger && typeof logger[level] === 'function') {
      logger[level](message);
    } else if (level === 'warn') {
      console.warn(message);
    } else {
      console.log(message);
    }
  };

  if (!app || !app.isPackaged) {
    log('info', '[Crash] Skipped: not a packaged build');
    return null;
  }

  let reporter = crashReporter;
  if (!reporter) {
    try {
      ({ crashReporter: reporter } = require('electron'));
    } catch (err) {
      log('warn', `[Crash] Unavailable: ${err.message}`);
      return null;
    }
  }

  const uploadUrl = String(env[UPLOAD_ENV] || '').trim();
  try {
    reporter.start({
      productName: 'yuleOSH',
      companyName: 'frisky1985',
      submitURL: uploadUrl || undefined,
      uploadToServer: Boolean(uploadUrl),
      compress: true,
      ignoreSystemCrashHandler: false,
    });
  } catch (err) {
    log('warn', `[Crash] Start failed (non-fatal): ${err.message}`);
    return null;
  }

  let dumpDir = '';
  try {
    dumpDir = app.getPath('crashDumps');
  } catch (err) {
    dumpDir = '';
  }
  log(
    'info',
    `[Crash] Reporter started (upload=${uploadUrl ? 'on' : 'off'}, dumps=${dumpDir || 'n/a'})`
  );

  if (typeof app.on === 'function') {
    app.on('render-process-gone', (_event, _contents, details) => {
      log(
        'warn',
        `[Crash] Renderer gone: reason=${details && details.reason} exitCode=${details && details.exitCode}`
      );
    });
    app.on('child-process-gone', (_event, details) => {
      log(
        'warn',
        `[Crash] Child process gone: type=${details && details.type} reason=${details && details.reason} exitCode=${details && details.exitCode}`
      );
    });
  }

  return reporter;
}

module.exports = { initCrashReporter };
