/**
 * preload.js — yuleOSH 安全上下文桥接
 *
 * 使用 contextBridge 安全暴露有限 API 给渲染进程。
 * 绝不暴露 Node.js 原生 API (require, process, fs 等)
 * 遵循 Electron 安全最佳实践 (contextIsolation + nodeIntegration=false)
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // ─── 后端信息 ─────────────────────────────────────

  /** @returns {string} Python 后端 URL */
  getBackendUrl: () => ipcRenderer.sendSync('get-backend-url'),

  // ─── 运行平台 ─────────────────────────────────────

  /** @returns {string} 'darwin' | 'linux' | 'win32' */
  platform: process.platform,

  // ─── 后端状态事件 ─────────────────────────────────

  /**
   * 后端就绪
   * @param {Function} callback
   */
  onBackendReady: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('backend-ready', handler);
    // 返回清理函数
    return () => ipcRenderer.removeListener('backend-ready', handler);
  },

  /**
   * 后端启动失败
   * @param {Function} callback - (errorMessage: string) => void
   */
  onBackendError: (callback) => {
    const handler = (_event, errorMessage) => callback(errorMessage);
    ipcRenderer.on('backend-error', handler);
    return () => ipcRenderer.removeListener('backend-error', handler);
  },

  /**
   * 后端崩溃 / 异常退出
   * @param {Function} callback - (exitCode: number) => void
   */
  onBackendCrashed: (callback) => {
    const handler = (_event, exitCode) => callback(exitCode);
    ipcRenderer.on('backend-crashed', handler);
    return () => ipcRenderer.removeListener('backend-crashed', handler);
  },

  /**
   * 后端已停止
   * @param {Function} callback - (exitCode: number) => void
   */
  onBackendStopped: (callback) => {
    const handler = (_event, exitCode) => callback(exitCode);
    ipcRenderer.on('backend-stopped', handler);
    return () => ipcRenderer.removeListener('backend-stopped', handler);
  },

  // ─── 原生对话框 ───────────────────────────────────

  /**
   * 打开目录选择对话框
   * @returns {Promise<string|null>} 选择的目录路径，取消则 null
   */
  openDirectory: () => ipcRenderer.invoke('open-directory'),

  // ─── 应用信息 ─────────────────────────────────────

  /** @returns {Promise<string>} 应用版本号 */
  getVersion: () => ipcRenderer.invoke('get-app-version'),
});
