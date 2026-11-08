/**
 * logger.test.js — 主进程文件日志
 *
 * @tests desktop/logger.js
 * @req SHALL-253
 */

/* eslint-disable */

const fs = require('fs');
const os = require('os');
const path = require('path');

const { createLogger } = require('../logger');

describe('logger', () => {
  let logDir;

  beforeEach(() => {
    logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'yuleosh-log-'));
  });

  afterEach(() => {
    fs.rmSync(logDir, { recursive: true, force: true });
  });

  test('写入 info/warn/error 并落盘', () => {
    const logger = createLogger({ logDir, filename: 'desktop.log' });
    logger.info('started');
    logger.warn('degraded');
    logger.error('boom');

    const content = fs.readFileSync(logger.path, 'utf8');
    expect(content).toContain('[INFO] started');
    expect(content).toContain('[WARN] degraded');
    expect(content).toContain('[ERROR] boom');
  });

  test('超过 maxBytes 时轮转为 .1', () => {
    const logger = createLogger({ logDir, filename: 'desktop.log', maxBytes: 80 });
    for (let i = 0; i < 20; i += 1) {
      logger.info(`line-${i}-${'x'.repeat(20)}`);
    }
    expect(fs.existsSync(`${logger.path}.1`)).toBe(true);
    expect(fs.statSync(logger.path).size).toBeLessThan(200);
  });
});
