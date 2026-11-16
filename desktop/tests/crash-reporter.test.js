/**
 * crash-reporter.test.js — 崩溃上报接线单元测试
 *
 * @req SHALL-253
 */

'use strict';

const { initCrashReporter } = require('../crash-reporter');

function fakeApp(overrides = {}) {
  const listeners = new Map();
  return {
    isPackaged: true,
    getPath: jest.fn(() => '/tmp/yuleosh-crash-dumps'),
    on: jest.fn((event, handler) => {
      listeners.set(event, handler);
    }),
    emit: (event, ...args) => {
      const handler = listeners.get(event);
      if (handler) handler(...args);
    },
    ...overrides,
  };
}

function fakeReporter() {
  return { start: jest.fn() };
}

describe('initCrashReporter', () => {
  test('未打包运行时跳过', () => {
    const reporter = fakeReporter();
    const result = initCrashReporter({
      app: fakeApp({ isPackaged: false }),
      crashReporter: reporter,
      env: {},
    });
    expect(result).toBeNull();
    expect(reporter.start).not.toHaveBeenCalled();
  });

  test('默认只写本地转储，不上报', () => {
    const reporter = fakeReporter();
    const logger = { info: jest.fn(), warn: jest.fn() };
    initCrashReporter({ app: fakeApp(), crashReporter: reporter, logger, env: {} });

    expect(reporter.start).toHaveBeenCalledWith(
      expect.objectContaining({
        productName: 'yuleOSH',
        uploadToServer: false,
        submitURL: undefined,
        compress: true,
      })
    );
    expect(logger.info).toHaveBeenCalledWith(
      expect.stringContaining('/tmp/yuleosh-crash-dumps')
    );
  });

  test('配置上报地址后启用上传', () => {
    const reporter = fakeReporter();
    initCrashReporter({
      app: fakeApp(),
      crashReporter: reporter,
      env: { YULEOSH_CRASH_UPLOAD_URL: 'https://crash.example.com/submit' },
    });

    expect(reporter.start).toHaveBeenCalledWith(
      expect.objectContaining({
        uploadToServer: true,
        submitURL: 'https://crash.example.com/submit',
      })
    );
  });

  test('start 抛错时降级为日志，不影响启动', () => {
    const reporter = { start: jest.fn(() => { throw new Error('bad path'); }) };
    const logger = { info: jest.fn(), warn: jest.fn() };
    const result = initCrashReporter({
      app: fakeApp(),
      crashReporter: reporter,
      logger,
      env: {},
    });

    expect(result).toBeNull();
    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining('bad path')
    );
  });

  test('渲染进程与子进程异常写入日志', () => {
    const app = fakeApp();
    const logger = { info: jest.fn(), warn: jest.fn() };
    initCrashReporter({ app, crashReporter: fakeReporter(), logger, env: {} });

    app.emit('render-process-gone', {}, {}, { reason: 'crashed', exitCode: 139 });
    app.emit('child-process-gone', {}, { type: 'GPU', reason: 'crashed', exitCode: 1 });

    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining('Renderer gone')
    );
    expect(logger.warn).toHaveBeenCalledWith(
      expect.stringContaining('type=GPU')
    );
  });
});
