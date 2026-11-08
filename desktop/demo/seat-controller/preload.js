/**
 * 座椅控制器 — preload
 *
 * 仅暴露最小存储接口，渲染进程不直接接触 Node API。
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('seatStore', {
  /** 读取上次姿态与记忆位置（无记录时返回 null） */
  load: () => ipcRenderer.invoke('seat:load'),
  /** 持久化当前姿态与记忆位置 */
  save: (state) => ipcRenderer.invoke('seat:save', state),
});
