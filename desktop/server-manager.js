/**
 * server-manager.js — yuleOSH Python 后端子进程生命周期管理
 *
 * 职责:
 *   - 启动 Python 后端子进程 (yuleosh UI server)
 *   - 健康检查轮询 (GET /api/v1/health)
 *   - 优雅关闭 (SIGTERM → 等待 → SIGKILL)
 *   - 异常处理与通知
 */

const { spawn } = require('child_process');
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
    this._healthTimer = null;
    this._isShuttingDown = false;
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
    const resourcesDir = process.resourcesPath;

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
   * 启动 Python 后端子进程
   * @returns {Promise<void>}
   */
  async start() {
    if (this.process) {
      console.log('[ServerManager] Backend already running');
      return;
    }

    this.restartCount = 0;

    // 检查 Python 版本
    await this._checkPythonVersion();

    const oshHome = this._resolveOshHome();

    const env = {
      ...process.env,
      OSH_PORT: String(this.port),
      PYTHONUNBUFFERED: '1',
      OSH_HOME: oshHome,
    };

    // 在当前 shell 环境中检查是否有 yuleosh 命令
    // 如果没有，使用 python -m yuleosh.ui.server
    const args = ['-m', 'yuleosh.ui.server'];

    console.log(`[ServerManager] Starting Python backend...`);
    console.log(`[ServerManager]   Command: ${this.pythonCmd} ${args.join(' ')}`);
    console.log(`[ServerManager]   Port:    ${this.port}`);
    console.log(`[ServerManager]   CWD:     ${this.backendDir}`);
    console.log(`[ServerManager]   OSH_HOME: ${oshHome}`);

    this.process = spawn(this.pythonCmd, args, {
      cwd: this.backendDir,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    // 流式记录 stdout
    this.process.stdout.on('data', (data) => {
      const lines = data.toString().trim();
      if (lines) {
        console.log(`[Python stdout] ${lines}`);
      }
    });

    // 流式记录 stderr
    this.process.stderr.on('data', (data) => {
      const lines = data.toString().trim();
      if (lines) {
        console.error(`[Python stderr] ${lines}`);
      }
    });

    // 进程意外退出处理 — 自动重启逻辑
    this.process.on('close', (code, signal) => {
      console.log(`[ServerManager] Process exited: code=${code} signal=${signal}`);
      if (!this._isShuttingDown) {
        if (this.restartCount < this.maxRestartAttempts) {
          this.restartCount++;
          console.log(`[ServerManager] Auto-restarting (attempt ${this.restartCount}/${this.maxRestartAttempts})...`);
          this.emit('restarting', this.restartCount, this.maxRestartAttempts);
          this._restart();
        } else {
          this.emit('fatal', code, signal);
        }
      }
      this.process = null;
    });

    this.process.on('error', (err) => {
      console.error(`[ServerManager] Process error: ${err.message}`);
      this.emit('error', err);
      this.process = null;
    });

    // 开始健康检查轮询
    await this._waitForHealthy();
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
      const proc = spawn('python3', ['--version']);
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
   * 重启 Python 后端（跳过初始检查，复用 spawn 逻辑）
   */
  async _restart() {
    const oshHome = this._resolveOshHome();

    const env = {
      ...process.env,
      OSH_PORT: String(this.port),
      PYTHONUNBUFFERED: '1',
      OSH_HOME: oshHome,
    };

    const args = ['-m', 'yuleosh.ui.server'];

    console.log(`[ServerManager] Restarting Python backend (attempt ${this.restartCount}/${this.maxRestartAttempts})...`);

    this.process = spawn(this.pythonCmd, args, {
      cwd: this.backendDir,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    // 重新挂载 stdout/stderr 监听
    this.process.stdout.on('data', (data) => {
      const lines = data.toString().trim();
      if (lines) {
        console.log(`[Python stdout] ${lines}`);
      }
    });

    this.process.stderr.on('data', (data) => {
      const lines = data.toString().trim();
      if (lines) {
        console.error(`[Python stderr] ${lines}`);
      }
    });

    // 重启进程的意外退出处理（与 start() 相同的自动重启逻辑）
    this.process.on('close', (code, signal) => {
      console.log(`[ServerManager] (restart) Process exited: code=${code} signal=${signal}`);
      if (!this._isShuttingDown) {
        if (this.restartCount < this.maxRestartAttempts) {
          this.restartCount++;
          console.log(`[ServerManager] Auto-restarting (attempt ${this.restartCount}/${this.maxRestartAttempts})...`);
          this.emit('restarting', this.restartCount, this.maxRestartAttempts);
          this._restart();
        } else {
          this.emit('fatal', code, signal);
        }
      }
      this.process = null;
    });

    this.process.on('error', (err) => {
      console.error(`[ServerManager] (restart) Process error: ${err.message}`);
      this.emit('error', err);
      this.process = null;
    });

    // 执行健康检查
    try {
      await this._waitForHealthy();
      console.log(`[ServerManager] Restart succeeded`);
      this.emit('healthy');
    } catch (err) {
      console.error(`[ServerManager] Restart unhealthy: ${err.message}`);
      // 健康检查失败时终止进程，让 close 处理器管理重试计数
      if (this.process && this.process.exitCode === null) {
        this.process.kill('SIGTERM');
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
