/**
 * server-lifecycle.test.js — Python 后端生命周期回归测试
 *
 * @tests desktop/server-manager.js
 * @req SHALL-253
 *
 * 覆盖：
 *   - 自动重启后 this.process 必须指向新进程（历史竞态：被旧 close 处理器置 null）
 *   - 重启成功后连续失败计数归零
 *   - 达到最大重试次数后 emit fatal，不再 spawn
 *   - 退出流程/首次启动阶段不得触发自动重启
 */

/* eslint-disable */

process.env.ELECTRON_DEV = 'true';

jest.mock('child_process', () => ({
  spawn: jest.fn(),
  execSync: jest.fn(),
}));

jest.mock('http', () => ({
  get: jest.fn(),
}));

const { EventEmitter } = require('events');
const os = require('os');
const path = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');

const ServerManager = require('../server-manager');

function createProc() {
  const proc = new EventEmitter();
  proc.stdout = new EventEmitter();
  proc.stderr = new EventEmitter();
  proc.exitCode = null;
  proc.kill = jest.fn(() => {
    proc.exitCode = 0;
    proc.emit('close', 0, 'SIGTERM');
  });
  return proc;
}

function healthyResponse() {
  http.get.mockImplementation((_url, _options, callback) => {
    const res = new EventEmitter();
    res.statusCode = 200;
    process.nextTick(() => {
      callback(res);
      res.emit('data', JSON.stringify({ ok: true, status: 'ok' }));
      res.emit('end');
    });
    return { on: jest.fn(), destroy: jest.fn() };
  });
}

function makeManager() {
  return new ServerManager({
    port: 19999,
    pythonCmd: 'python3',
    backendDir: path.join(os.tmpdir(), 'yuleosh-desktop-test'),
  });
}

beforeEach(() => {
  spawn.mockReset();
  execSync.mockReset();
  execSync.mockImplementation(() => {
    throw new Error('yuleosh not installed');
  });
  http.get.mockReset();
  healthyResponse();
});

describe('ServerManager 自动重启', () => {
  test('重启后保留新进程引用，stop() 仍能回收后端', async () => {
    const sm = makeManager();
    const proc1 = createProc();
    const proc2 = createProc();
    spawn.mockReturnValueOnce(proc2);

    sm.process = proc1;
    sm.restartCount = 1;
    sm._attachProcessHandlers(proc1, 'start');

    proc1.exitCode = 1;
    proc1.emit('close', 1, null);

    // _restart() 在首个 await 前同步 spawn，新引用必须立即可见
    expect(spawn).toHaveBeenCalledTimes(1);
    expect(sm.process).toBe(proc2);

    await new Promise((resolve) => setImmediate(resolve));

    expect(sm.process).toBe(proc2);
    expect(sm.isRunning()).toBe(true);
    expect(sm.restartCount).toBe(0);
  });

  test('达到最大重试次数后 emit fatal 且不再 spawn', () => {
    const sm = makeManager();
    sm.restartCount = sm.maxRestartAttempts;
    const proc = createProc();
    sm.process = proc;
    sm._attachProcessHandlers(proc, 'start');
    const fatal = jest.fn();
    sm.on('fatal', fatal);

    proc.exitCode = 1;
    proc.emit('close', 1, null);

    expect(spawn).not.toHaveBeenCalled();
    expect(fatal).toHaveBeenCalledWith(1, null);
    expect(sm.process).toBeNull();
  });

  test('首次启动阶段的崩溃不抢跑重启', () => {
    const sm = makeManager();
    const proc = createProc();
    sm.process = proc;
    sm._starting = true;
    sm._attachProcessHandlers(proc, 'start');

    proc.exitCode = 1;
    proc.emit('close', 1, null);

    expect(spawn).not.toHaveBeenCalled();
    expect(sm.process).toBeNull();
  });

  test('退出流程中的 close 不触发重启', () => {
    const sm = makeManager();
    const proc = createProc();
    sm.process = proc;
    sm._isShuttingDown = true;
    sm._attachProcessHandlers(proc, 'start');

    proc.exitCode = 0;
    proc.emit('close', 0, 'SIGTERM');

    expect(spawn).not.toHaveBeenCalled();
    expect(sm.process).toBeNull();
  });

  test('重启进行中的重复 close 不会并发 spawn', () => {
    const sm = makeManager();
    const proc = createProc();
    sm.process = proc;
    sm._restarting = true;
    sm._attachProcessHandlers(proc, 'start');

    proc.exitCode = 1;
    proc.emit('close', 1, null);

    expect(spawn).not.toHaveBeenCalled();
  });
});
