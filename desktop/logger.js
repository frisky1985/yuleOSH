/**
 * logger.js — 主进程文件日志
 *
 * @req SHALL-253
 *
 * 桌面端崩溃后用户无法回看终端输出，因此把主进程与 Python 后端日志
 * 追加到 Electron 的 logs 目录，并做 5MB 单文件轮转。
 */

const fs = require('fs');
const path = require('path');
const util = require('util');

const DEFAULT_MAX_BYTES = 5 * 1024 * 1024;

function formatMessage(args) {
  return args
    .map((arg) => (typeof arg === 'string' ? arg : util.inspect(arg, { depth: 3 })))
    .join(' ');
}

/**
 * @param {{logDir?: string, filename?: string, maxBytes?: number}} [options]
 * @returns {{info: Function, warn: Function, error: Function, path: string}}
 */
function createLogger(options = {}) {
  const logDir = options.logDir || path.join(process.cwd(), 'logs');
  const filename = options.filename || 'desktop.log';
  const maxBytes = options.maxBytes || DEFAULT_MAX_BYTES;
  const filePath = path.join(logDir, filename);

  try {
    fs.mkdirSync(logDir, { recursive: true });
  } catch (err) {
    console.error(`[Logger] Cannot create log dir ${logDir}: ${err.message}`);
  }

  let size = 0;
  try {
    size = fs.statSync(filePath).size;
  } catch {
    size = 0;
  }

  function rotate() {
    const backup = `${filePath}.1`;
    try {
      if (fs.existsSync(backup)) {
        fs.unlinkSync(backup);
      }
      fs.renameSync(filePath, backup);
    } catch (err) {
      console.error(`[Logger] Rotate failed: ${err.message}`);
    }
    size = 0;
  }

  function write(level, args) {
    const message = formatMessage(args);
    const consoleFn = level === 'ERROR'
      ? console.error
      : level === 'WARN'
        ? console.warn
        : console.log;
    consoleFn(message);

    const line = `${new Date().toISOString()} [${level}] ${message}\n`;
    const bytes = Buffer.byteLength(line);
    try {
      if (size + bytes > maxBytes) {
        rotate();
      }
      fs.appendFileSync(filePath, line);
      size += bytes;
    } catch (err) {
      // 日志失败绝不拖垮主流程
      console.error(`[Logger] Write failed: ${err.message}`);
    }
  }

  return {
    path: filePath,
    info: (...args) => write('INFO', args),
    warn: (...args) => write('WARN', args),
    error: (...args) => write('ERROR', args),
  };
}

module.exports = { createLogger, DEFAULT_MAX_BYTES };
