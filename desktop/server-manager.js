/**
 * server-manager.js — yuleOSH Python 后端子进程生命周期管理
 *
 * @req SHALL-253
 *
 * 职责:
 *   - 启动 Python 后端子进程 (yuleosh UI server)
 *   - 健康检查轮询 (GET /api/v1/health)
 *   - 优雅关闭 (SIGTERM → 等待 → SIGKILL)
 *   - 异常处理与通知
 */

const { spawn, execSync } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const { EventEmitter } = require('events');

// ─── 常量 ────────────────────────────────────────────

const DEFAULT_PORT = 18788;
const HEALTH_CHECK_PATH = '/api/v1/health';
const HEALTH_POLL_INTERVAL_MS = 500;
const HEALTH_TIMEOUT_MS = 15_000;
const GRACEFUL_SHUTDOWN_MS = 5_000;

// ─── 类 ──────────────────────────────────────────────

class ServerManager extends EventEmitter {

  constructor(options = {}) {
    super();
    this.port = options.port || DEFAULT_PORT;
    this.pythonCmd = options.pythonCmd || 'python3';
    this.backendDir = options.backendDir || this._resolveBackendDir();
    this.process = null;
    this.logger = options.logger || null;
    this._healthTimer = null;
    this._isShuttingDown = false;
    this._restarting = false;
    this._starting = false;
    this.maxRestartAttempts = 2;
    this.restartCount = 0;
  }

  /**
   * 解析后端 Python 项目目录
   *
   * 开发模式 (ELECTRON_DEV=true):
   *   从 desktop/ → ../src/ （项目源码目录）
   *
   * 生产模式 (Electron 打包):
   *   Python 后端不以 asar 形式打包（electron-builder.yml 无 backend extraResources），
   *   必须通过 pip install yuleosh 提前安装。
   *   此处返回 process.resourcesPath 作为 fallback 工作目录，
   *   同时使用 Electron userData 目录作为 OSH_HOME 持久化路径。
   */
  _resolveBackendDir() {
    const isDev = process.env.ELECTRON_DEV === 'true';

    if (isDev) {
      // 开发模式：desktop/ → ../src/
      const desktopDir = path.resolve(__dirname);
      const projectDir = path.resolve(desktopDir, '..');
      const srcDir = path.resolve(projectDir, 'src');
      return srcDir;
    }

    // ── 生产模式 ──────────────────────────────────────────────
    // process.resourcesPath is only defined in a packaged Electron runtime.
    // Fall back to the project root so the module remains loadable in tests
    // and in `electron .` runs before packaging.
    const resourcesDir = process.resourcesPath || path.resolve(__dirname, '..');

    // 第一步：检查 extraResources 中是否包含后端源码（预留扩展）
    const bundledBackend = path.join(resourcesDir, 'backend-src');
    if (fs.existsSync(bundledBackend)) {
      return bundledBackend;
    }

    // 第二步：后端未打包，发出清晰警告
    console.warn(
      '[ServerManager] ⚠ WARNING: Python backend source not found in production bundle.\n' +
      `  Expected bundled path: ${bundledBackend}\n` +
      '  Please ensure yuleosh is installed via pip:  pip install yuleosh\n' +
      '  For development, set ELECTRON_DEV=true and ensure src/ exists.'
    );

    // 第三步：fallback — 使用用户数据目录让 OSH_HOME 指向合理的持久化位置
    try {
      const userDataPath = this._getUserDataPath();
      fs.mkdirSync(userDataPath, { recursive: true });
      return userDataPath;
    } catch {
      return resourcesDir;
    }
  }

  /**
   * 解析 OSH_HOME 环境变量值
   *
   * 开发模式: 与 backendDir 相同，指向项目源码 src/
   * 生产模式: 指向 Electron 用户数据目录（用于存储会话、证据等）
   */
  _resolveOshHome() {
    const isDev = process.env.ELECTRON_DEV === 'true';
    if (isDev) {
      return this.backendDir;
    }
    // 生产模式下使用持久化的用户数据目录
    try {
      const userDataPath = this._getUserDataPath();
      fs.mkdirSync(userDataPath, { recursive: true });
      return userDataPath;
    } catch {
      return this.backendDir;
    }
  }

  /**
   * 获取 Electron 用户数据目录
   * 生产模式下 OSH_HOME 指向此目录，使 Python 后端使用正确的工作区
   */
  _getUserDataPath() {
    try {
      const { app } = require('electron');
      return app.getPath('userData');
    } catch {
      // Electron app 模块不可用时的安全 fallback
      return path.join(process.env.HOME || process.env.USERPROFILE || '.', '.yuleosh');
    }
  }

  /**
   * 解析后端启动命令。
   *
   * 优先使用已安装的 `yuleosh` CLI（子命令 `ui`），
   * 未安装时回退到 `python3 -m yuleosh.ui.server`。
   *
   * @returns {{command: string, args: string[]}}
   */
  _resolveCommand() {
    const probe = process.platform === 'win32' ? 'where yuleosh' : 'command -v yuleosh';
    try {
      execSync(probe, { stdio: 'ignore' });
      return { command: 'yuleosh', args: ['ui'] };
    } catch {
      return { command: this.pythonCmd, args: ['-m', 'yuleosh.ui.server'] };
    }
  }

  /**
   * 启动 Python 后端子进程
   * @returns {Promise<void>}
   */
  async start() {
    if (this.process) {
      console.log('[ServerManager] Backend already running');
      return;
    }

    this.restartCount = 0;
    this._startupFailed = false;
    this._isShuttingDown = false;

    // 检查 Python 版本
    await this._checkPythonVersion();

    const oshHome = this._resolveOshHome();

    // Desktop local mode: disable multi-tenant auth (the desktop app is a
    // single-user local tool) and enable the desktop workspace API. The
    // web SaaS stack keeps auth enabled when running outside the desktop.
    const env = {
      ...process.env,
      OSH_PORT: String(this.port),
      PYTHONUNBUFFERED: '1',
      OSH_HOME: oshHome,
      YULEOSH_AUTH_DISABLED: '1',
      YULEOSH_DESKTOP_MODE: '1',
    };

    const { command, args } = this._resolveCommand();

    console.log(`[ServerManager] Starting Python backend...`);
    console.log(`[ServerManager]   Command: ${command} ${args.join(' ')}`);
    console.log(`[ServerManager]   Port:    ${this.port}`);
    console.log(`[ServerManager]   CWD:     ${this.backendDir}`);
    console.log(`[ServerManager]   OSH_HOME: ${oshHome}`);

    const proc = spawn(command, args, {
      cwd: this.backendDir,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.process = proc;
    this._starting = true;
    this._attachProcessHandlers(proc, 'start');

    // 开始健康检查轮询；失败时终止子进程，避免留下孤儿后端
    try {
      await this._waitForHealthy();
      this._starting = false;
    } catch (err) {
      this._startupFailed = true;
      this._starting = false;
      if (this.process === proc && proc.exitCode === null) {
        proc.kill('SIGTERM');
      }
      if (this.process === proc) {
        this.process = null;
      }
      throw err;
    }
  }

  /**
   * 轮询健康检查端点，直到服务可用或超时
   */
  _waitForHealthy() {
    return new Promise((resolve, reject) => {
      const startTime = Date.now();

      const poll = () => {
        if (this._isShuttingDown) {
          reject(new Error('Shutdown initiated during health check'));
          return;
        }

        const elapsed = Date.now() - startTime;
        if (elapsed > HEALTH_TIMEOUT_MS) {
          reject(new Error(
            `Python backend did not become healthy within ${HEALTH_TIMEOUT_MS / 1000}s. ` +
            `Check that yuleOSH is installed (pip install yuleosh)`
          ));
          return;
        }

        this._checkHealth()
          .then((healthy) => {
            if (healthy) {
              console.log(`[ServerManager] Backend healthy after ${elapsed}ms`);
              this.emit('healthy');
              resolve();
            } else {
              this._healthTimer = setTimeout(poll, HEALTH_POLL_INTERVAL_MS);
            }
          })
          .catch(() => {
            // 连接失败 → 继续轮询
            this._healthTimer = setTimeout(poll, HEALTH_POLL_INTERVAL_MS);
          });
      };

      poll();
    });
  }

  /**
   * 发起一次健康检查
   * @returns {Promise<boolean>}
   */
  _checkHealth() {
    return new Promise((resolve) => {
      const req = http.get(
        `http://localhost:${this.port}${HEALTH_CHECK_PATH}`,
        { timeout: 2000 },
        (res) => {
          let body = '';
          res.on('data', (chunk) => { body += chunk; });
          res.on('end', () => {
            try {
              const json = JSON.parse(body);
              // 检查 ok=true 以及 status=healthy/ok
              resolve(json.ok === true || json.status === 'ok' || json.status === 'healthy');
            } catch {
              resolve(res.statusCode === 200);
            }
          });
        }
      );
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    });
  }

  /**
   * 检查 Python 版本 (>= 3.10)
   */
  _checkPythonVersion() {
    return new Promise((resolve, reject) => {
      const proc = spawn(this.pythonCmd, ['--version']);
      let output = '';
      proc.stdout.on('data', (d) => { output += d.toString(); });
      proc.stderr.on('data', (d) => { output += d.toString(); });
      proc.on('close', (code) => {
        if (code !== 0) {
          reject(new Error(`python3 --version 返回退出码 ${code}`));
          return;
        }
        const match = output.match(/Python\s+(\d+)\.(\d+)/);
        if (!match) {
          reject(new Error(`无法解析 Python 版本: "${output.trim()}"`));
          return;
        }
        const major = parseInt(match[1], 10);
        const minor = parseInt(match[2], 10);
        if (major < 3 || (major === 3 && minor < 10)) {
          reject(new Error(`需要 Python >= 3.10，当前: ${output.trim()}`));
          return;
        }
        console.log(`[ServerManager] Python version OK: ${output.trim()}`);
        resolve(output.trim());
      });
      proc.on('error', (err) => {
        reject(new Error(`无法执行 python3: ${err.message}. 请安装 Python 3.10+`));
      });
    });
  }

  /**
   * 写入文件日志（可选）。未注入 logger 时保持纯 console 行为。
   * @param {'info'|'warn'|'error'} level
   * @param {string} message
   */
  _writeLog(level, message) {
    if (this.logger && typeof this.logger[level] === 'function') {
      this.logger[level](message);
    }
  }

  /**
   * 绑定子进程生命周期。start() 与 _restart() 共用，避免两套重复逻辑漂移。
   * @param {import('child_process').ChildProcess} proc
   * @param {'start'|'restart'} phase
   */
  _attachProcessHandlers(proc, phase) {
    proc.stdout.on('data', (data) => {
      const lines = data.toString().trim();
      if (lines) {
        console.log(`[Python stdout] ${lines}`);
        this._writeLog('info', `[Python stdout] ${lines}`);
      }
    });

    proc.stderr.on('data', (data) => {
      const lines = data.toString().trim();
      if (lines) {
        console.error(`[Python stderr] ${lines}`);
        this._writeLog('error', `[Python stderr] ${lines}`);
      }
    });

    proc.on('close', (code, signal) => {
      console.log(`[ServerManager] (${phase}) Process exited: code=${code} signal=${signal}`);
      this._writeLog('warn', `[ServerManager] (${phase}) Process exited: code=${code} signal=${signal}`);
      // 先清引用再重启：_restart() 会在首个 await 前同步 spawn 新进程并写入
      // this.process；若此处无条件置 null，会把新进程引用覆盖掉，导致
      // stop() 失去对后端的控制并留下孤儿进程。
      if (this.process === proc) {
        this.process = null;
      }
      if (this._isShuttingDown || this._startupFailed) {
        return;
      }
      // 首次启动阶段由 start() 的健康检查负责报错，不在这里抢跑重启。
      if (this._starting) {
        return;
      }
      this.emit('crashed', code, signal);
      this._scheduleRestart(code, signal);
    });

    proc.on('error', (err) => {
      console.error(`[ServerManager] (${phase}) Process error: ${err.message}`);
      this._writeLog('error', `[ServerManager] (${phase}) Process error: ${err.message}`);
      this._startupFailed = true;
      if (this.process === proc) {
        this.process = null;
      }
      this.emit('error', err);
    });
  }

  /**
   * 触发一次自动重启。restartCount 表示“连续失败次数”，重启成功后归零。
   */
  _scheduleRestart(code, signal) {
    if (this._restarting) {
      return;
    }
    if (this.restartCount >= this.maxRestartAttempts) {
      this._writeLog('error', '[ServerManager] Restart attempts exhausted; backend fatal');
      this.emit('fatal', code, signal);
      return;
    }
    this.restartCount += 1;
    console.log(`[ServerManager] Auto-restarting (attempt ${this.restartCount}/${this.maxRestartAttempts})...`);
    this._writeLog('warn', `[ServerManager] Auto-restarting (attempt ${this.restartCount}/${this.maxRestartAttempts})`);
    this.emit('restarting', this.restartCount, this.maxRestartAttempts);

    // _restart() 在首个 await 前同步完成 spawn，因此这里立即清除标记是安全的；
    // 若重启后的进程在健康检查期间再次崩溃，close 处理器仍能进入下一轮。
    this._restarting = true;
    let pending;
    try {
      pending = this._restart();
    } finally {
      this._restarting = false;
    }
    pending.catch((err) => {
      console.error(`[ServerManager] Restart failed: ${err.message}`);
      this.emit('fatal', code, signal);
    });
  }

  /**
   * 重启 Python 后端（跳过初始检查，复用 spawn 逻辑）
   */
  async _restart() {
    this._startupFailed = false;
    const oshHome = this._resolveOshHome();

    // Desktop local mode: disable multi-tenant auth (the desktop app is a
    // single-user local tool) and enable the desktop workspace API. The
    // web SaaS stack keeps auth enabled when running outside the desktop.
    const env = {
      ...process.env,
      OSH_PORT: String(this.port),
      PYTHONUNBUFFERED: '1',
      OSH_HOME: oshHome,
      YULEOSH_AUTH_DISABLED: '1',
      YULEOSH_DESKTOP_MODE: '1',
    };

    const { command, args } = this._resolveCommand();

    console.log(`[ServerManager] Restarting Python backend (attempt ${this.restartCount}/${this.maxRestartAttempts})...`);

    const proc = spawn(command, args, {
      cwd: this.backendDir,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.process = proc;
    this._attachProcessHandlers(proc, 'restart');

    // 执行健康检查（_waitForHealthy 成功时已 emit('healthy')，此处不重复发）
    try {
      await this._waitForHealthy();
      console.log(`[ServerManager] Restart succeeded`);
      this.restartCount = 0;
    } catch (err) {
      console.error(`[ServerManager] Restart unhealthy: ${err.message}`);
      // 健康检查失败时终止进程，让 close 处理器管理重试计数
      if (this.process === proc && proc.exitCode === null) {
        proc.kill('SIGTERM');
      }
    }
  }

  /**
   * 优雅关闭 Python 后端
   * @returns {Promise<void>}
   */
  async stop() {
    if (!this.process) {
      console.log('[ServerManager] No backend process to stop');
      return;
    }

    this._isShuttingDown = true;

    // 取消健康检查定时器
    if (this._healthTimer) {
      clearTimeout(this._healthTimer);
      this._healthTimer = null;
    }

    return new Promise((resolve) => {
      const proc = this.process;
      let forceKillTimer = null;

      // 监听进程退出
      const onClose = (code, signal) => {
        if (forceKillTimer) {
          clearTimeout(forceKillTimer);
          forceKillTimer = null;
        }
        console.log(`[ServerManager] Backend stopped (code=${code}, signal=${signal})`);
        this.emit('stopped', code);
        resolve();
      };

      proc.once('close', onClose);

      // Step 1: SIGTERM — 优雅关闭
      console.log('[ServerManager] Sending SIGTERM to backend...');
      proc.kill('SIGTERM');

      // Step 2: 超时后 SIGKILL
      forceKillTimer = setTimeout(() => {
        if (proc.exitCode === null) {
          console.log('[ServerManager] Graceful shutdown timed out, sending SIGKILL...');
          proc.kill('SIGKILL');
        }
      }, GRACEFUL_SHUTDOWN_MS);
    });
  }

  /**
   * 当前运行状态
   */
  isRunning() {
    return this.process !== null && this.process.exitCode === null;
  }

  /**
   * 获取后端 URL
   */
  getBackendUrl() {
    return `http://localhost:${this.port}`;
  }

  /**
   * 销毁（停止 + 清理）
   */
  async destroy() {
    await this.stop();
    this.removeAllListeners();
  }
}

// ─── 导出 ────────────────────────────────────────────

module.exports = ServerManager;
