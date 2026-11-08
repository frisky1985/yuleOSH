/**
 * preload.js — yuleOSH 安全上下文桥接
 *
 * @req SHALL-253
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

  /**
   * 重启后端并重新加载前端（错误页重试）
   * @returns {Promise<{ok:boolean, error?:string}>}
   */
  retryStartup: () => ipcRenderer.invoke('retry-startup'),

  /**
   * 查询后端运行状态
   * @returns {Promise<{running:boolean, url:string|null}>}
   */
  getBackendStatus: () => ipcRenderer.invoke('get-backend-status'),

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
   * 后端自动重启中
   * @param {Function} callback - ({attempt, max}) => void
   */
  onBackendRestarting: (callback) => {
    const handler = (_event, info) => callback(info);
    ipcRenderer.on('backend-restarting', handler);
    return () => ipcRenderer.removeListener('backend-restarting', handler);
  },

  /**
   * 后端达到最大重启次数
   * @param {Function} callback - (message: string) => void
   */
  onBackendFatal: (callback) => {
    const handler = (_event, message) => callback(message);
    ipcRenderer.on('backend-fatal', handler);
    return () => ipcRenderer.removeListener('backend-fatal', handler);
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

  // ─── 项目对话框 ───────────────────────────────────

  /**
   * 打开项目目录选择对话框（与菜单“打开项目”同一实现）
   * @returns {Promise<string|null>} 选中的目录；取消则 null
   */
  openProjectDialog: () => ipcRenderer.invoke('open-project-dialog'),

  /**
   * 新建项目目录对话框
   * @returns {Promise<string|null>} 目标目录；取消则 null
   */
  createProjectDialog: () => ipcRenderer.invoke('create-project-dialog'),

  /**
   * 订阅菜单/对话框选中项目事件
   * @param {(projectPath: string) => void} callback
   * @returns {() => void} 取消订阅
   */
  onProjectOpened: (callback) => {
    const handler = (_event, projectPath) => callback(projectPath);
    ipcRenderer.on('project-opened', handler);
    return () => ipcRenderer.removeListener('project-opened', handler);
  },

  /**
   * 订阅新建项目事件
   * @param {(projectPath: string) => void} callback
   * @returns {() => void} 取消订阅
   */
  onCreateProject: (callback) => {
    const handler = (_event, projectPath) => callback(projectPath);
    ipcRenderer.on('create-project', handler);
    return () => ipcRenderer.removeListener('create-project', handler);
  },

  // ─── 原生对话框 ───────────────────────────────────

  /**
   * 打开目录选择对话框
   * @returns {Promise<string|null>} 选择的目录路径，取消则 null
   */
  openDirectory: () => ipcRenderer.invoke('open-directory'),

  /**
   * 打开文件选择对话框（用于导入需求文档）
   * @param {{title?: string, filters?: {name: string, extensions: string[]}[]}} [options]
   * @returns {Promise<string|null>}
   */
  openFile: (options) => ipcRenderer.invoke('open-file', options),

  /**
   * 读取本地文件文本内容
   * @param {string} filePath
   * @returns {Promise<{ok:boolean, content?:string, error?:string}>}
   */
  readFile: (filePath) => ipcRenderer.invoke('read-file', filePath),

  /** 判断当前是否运行在 Electron 桌面环境 */
  isDesktop: true,

  // ─── 应用信息 ─────────────────────────────────────

  /** @returns {Promise<string>} 应用版本号 */
  getVersion: () => ipcRenderer.invoke('get-app-version'),
});
