/**
 * backend-startup.test.js — 后端可启动性 & 健康检查测试（AC-2.3.1 / AC-2.1.x）
 *
 * 测试策略：
 *   同步测试：命令解析、URL 构造、状态查询 — 纯逻辑验证
 *   异步测试：使用简单 mock 验证 spawn 调用和健康检查 URL
 *
 * @tests desktop/server-manager.js
 * @req SHALL-253
 */
/* eslint-disable */

const mockSpawn = jest.fn();
const mockExecSync = jest.fn();

jest.mock('child_process', () => ({
  spawn: mockSpawn,
  execSync: mockExecSync,
}));

// 不 mock http — 使用一个简单的占位
const { EventEmitter } = require('events');
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ServerManager = require('../server-manager');

/**
 * 构造一个包含内置 yuleosh-server 的临时 resources 目录
 * @returns {{root: string, exe: string}}
 */
function makeBundledRuntime() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'yuleosh-bundle-'));
  const backendDir = path.join(root, 'backend');
  fs.mkdirSync(backendDir);
  const exeName = process.platform === 'win32' ? 'yuleosh-server.exe' : 'yuleosh-server';
  const exe = path.join(backendDir, exeName);
  fs.writeFileSync(exe, '');
  return { root, exe };
}

function makeMockProc() {
  const proc = new EventEmitter();
  proc.stdout = new EventEmitter();
  proc.stderr = new EventEmitter();
  proc.stdin = new EventEmitter();
  proc.pid = 12345;
  proc.exitCode = null;
  proc.killed = false;
  proc.kill = jest.fn();
  return proc;
}

describe('ServerManager — AC-2.x 后端管理', () => {

  beforeEach(() => {
    jest.clearAllMocks();
    jest.restoreAllMocks();
    // 默认 yuleosh CLI 可用
    mockExecSync.mockImplementation(() => Buffer.from('/usr/local/bin/yuleosh'));
  });

  // ── AC-2.1.2: 命令解析 (同步测试) ──────────────

  test('AC-2.1.2: _resolveCommand 返回 yuleosh ui', () => {
    const sm = new ServerManager();
    const r = sm._resolveCommand();
    expect(r.command).toBe('yuleosh');
    expect(r.args).toEqual(['ui']);
  });

  test('AC-2.1.2: _resolveCommand 回退 python3 -m yuleosh.ui.server', () => {
    mockExecSync.mockImplementation(() => { throw new Error('not found'); });
    const sm = new ServerManager();
    const r = sm._resolveCommand();
    expect(r.command).toBe('python3');
    expect(r.args).toEqual(['-m', 'yuleosh.ui.server']);
  });

  // ── AC-2.1.3: 健康检查路径 (同步测试) ──────────

  test('AC-2.1.3: 健康检查 URL 格式正确', () => {
    // 验证 server-manager 内部的常量
    expect(ServerManager.prototype.constructor.name).toBe('ServerManager');
    const sm = new ServerManager({ port: 18788 });
    expect(sm.getBackendUrl()).toBe('http://localhost:18788');
    // 验证 _checkHealth 用 /api/v1/health
    // 这是通过读内部 HEALTH_CHECK_PATH 间接验证的
    // 签名层面验证
    expect(typeof sm._checkHealth).toBe('function');
  });

  // ── AC-2.1.1: spawn 调用分析 ────────────────────

  test('AC-2.1.1/2: spawn 传递 yuleosh server 命令', async () => {
    let spawnCallCount = 0;
    mockSpawn.mockImplementation(() => {
      spawnCallCount++;
      const proc = makeMockProc();
      if (spawnCallCount === 1) {
        process.nextTick(() => {
          proc.stdout.emit('data', 'Python 3.11.0\n');
          proc.emit('close', 0, null);
        });
      }
      return proc;
    });

    // 使用 jest.spyOn 临时 mock http.get
    const mockReq = new EventEmitter();
    mockReq.setTimeout = jest.fn();
    mockReq.destroy = jest.fn();
    const mockHttpGet = jest.spyOn(http, 'get').mockImplementation((url, opts, cb) => {
      if (typeof opts === 'function') { cb = opts; }
      const res = new EventEmitter();
      res.statusCode = 200;
      process.nextTick(() => {
        res.emit('data', '{"ok":true,"status":"healthy"}');
        res.emit('end');
      });
      cb(res);
      return mockReq;
    });

    const sm = new ServerManager({ port: 18788 });
    await sm.start();

    const calls = mockSpawn.mock.calls;
    const lastCall = calls[calls.length - 1];
    expect(lastCall[0]).toBe('yuleosh');
    expect(lastCall[1]).toEqual(['ui']);

    // 验证健康检查 URL 路径
    const healthUrl = mockHttpGet.mock.calls[0][0];
    expect(healthUrl).toContain('/api/v1/health');

    mockHttpGet.mockRestore();
  }, 10000);

  test('AC-2.1.1: 回退和版本检查', async () => {
    // 让 yuleosh CLI 不存在
    mockExecSync.mockImplementation(() => { throw new Error('not found'); });

    let spawnCallCount = 0;
    mockSpawn.mockImplementation(() => {
      spawnCallCount++;
      const proc = makeMockProc();
      if (spawnCallCount === 1) {
        process.nextTick(() => {
          proc.stdout.emit('data', 'Python 3.11.0\n');
          proc.emit('close', 0, null);
        });
      }
      return proc;
    });

    const mockReq = new EventEmitter();
    mockReq.setTimeout = jest.fn();
    mockReq.destroy = jest.fn();
    jest.spyOn(http, 'get').mockImplementation((url, opts, cb) => {
      if (typeof opts === 'function') { cb = opts; }
      const res = new EventEmitter();
      res.statusCode = 200;
      process.nextTick(() => {
        res.emit('data', '{"ok":true,"status":"healthy"}');
        res.emit('end');
      });
      cb(res);
      return mockReq;
    });

    const sm = new ServerManager({ port: 18788 });
    await sm.start();

    const calls = mockSpawn.mock.calls;
    const lastCall = calls[calls.length - 1];
    expect(lastCall[0]).toBe('python3');
    expect(lastCall[1]).toEqual(['-m', 'yuleosh.ui.server']);

    http.get.mockRestore();
  }, 10000);

  // ── AC-2.1.6: stop 逻辑 ─────────────────────────

  test('AC-2.1.6: stop 和 destroy 方法存在', () => {
    const sm = new ServerManager();
    expect(typeof sm.stop).toBe('function');
    expect(typeof sm.destroy).toBe('function');
    // stop() 在没有进程时直接 resolve
    return expect(sm.stop()).resolves.toBeUndefined();
  });

  // ── AC-2.2.1: 后端 URL ─────────────────────────

  test('AC-2.2.1: getBackendUrl 返回 http://localhost:18788', () => {
    const sm = new ServerManager({ port: 18788 });
    expect(sm.getBackendUrl()).toBe('http://localhost:18788');
  });

  // ── isRunning ──────────────────────────────────

  test('isRunning: 未启动时返回 false', () => {
    const sm = new ServerManager();
    expect(sm.isRunning()).toBe(false);
  });

  // ── AC-2.3.1: 重试配置 ─────────────────────────

  test('AC-2.3.1: maxRestartAttempts=2，重启逻辑存在', () => {
    const sm = new ServerManager();
    expect(sm.maxRestartAttempts).toBe(2);
    expect(typeof sm._restart).toBe('function');
    expect(typeof sm.start).toBe('function');
  });

  // ── AC-5.1.4: 内置 Python 运行时 ─────────────────

  test('AC-5.1.4: 打包内置 yuleosh-server 优先于系统 Python', () => {
    const { root, exe } = makeBundledRuntime();
    const prevResourcesPath = process.resourcesPath;
    process.resourcesPath = root;

    try {
      const sm = new ServerManager();
      expect(sm._resolveCommand()).toEqual({ command: exe, args: [], bundled: true });
      expect(sm.backendDir).toBe(path.dirname(exe));
    } finally {
      process.resourcesPath = prevResourcesPath;
      fs.rmSync(root, { recursive: true, force: true });
    }
  });

  test('AC-5.1.4: 使用内置运行时不探测系统 Python 版本', async () => {
    const { root, exe } = makeBundledRuntime();
    const prevResourcesPath = process.resourcesPath;
    process.resourcesPath = root;

    mockSpawn.mockImplementation(() => makeMockProc());

    const mockReq = new EventEmitter();
    mockReq.setTimeout = jest.fn();
    mockReq.destroy = jest.fn();
    const mockHttpGet = jest.spyOn(http, 'get').mockImplementation((_url, _opts, cb) => {
      if (typeof _opts === 'function') { cb = _opts; }
      const res = new EventEmitter();
      res.statusCode = 200;
      process.nextTick(() => {
        res.emit('data', '{"ok":true,"status":"healthy"}');
        res.emit('end');
      });
      cb(res);
      return mockReq;
    });

    try {
      const sm = new ServerManager({ port: 18788 });
      await sm.start();

      const firstCall = mockSpawn.mock.calls[0];
      expect(firstCall[0]).toBe(exe);
      expect(firstCall[1]).toEqual([]);
      const versionProbes = mockSpawn.mock.calls.filter(
        (call) => Array.isArray(call[1]) && call[1].includes('--version')
      );
      expect(versionProbes).toHaveLength(0);
    } finally {
      mockHttpGet.mockRestore();
      process.resourcesPath = prevResourcesPath;
      fs.rmSync(root, { recursive: true, force: true });
    }
  }, 10000);
});
