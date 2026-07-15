/**
 * tray.js — yuleOSH 系统托盘
 *
 * 职责:
 *   - 创建/更新系统托盘图标
 *   - 右键菜单 (显示窗口 / 隐藏窗口 / 退出)
 *   - 根据窗口状态切换图标
 *   - macOS Template 图标支持 (自动适配 dark/light mode)
 */

const { Tray, Menu, nativeImage, app } = require('electron');
const path = require('path');

// ─── 常量 ────────────────────────────────────────────

const TRAY_ICON_SIZE = 22; // 标准托盘图标尺寸

// ─── 类 ──────────────────────────────────────────────

class TrayManager {

  /**
   * @param {Electron.BrowserWindow} mainWindow - 主窗口引用
   */
  constructor(mainWindow) {
    this.tray = null;
    this.mainWindow = mainWindow;
    this._iconPath = null;
  }

  /**
   * 创建系统托盘
   */
  create() {
    if (this.tray) {
      return;
    }

    // 获取图标路径
    this._iconPath = this._resolveIconPath();

    // 创建托盘图标
    const icon = this._loadIcon(this._iconPath);
    this.tray = new Tray(icon);

    // 设置工具提示
    this.tray.setToolTip('yuleOSH — 嵌入式AI开发全流程平台');

    // 构建右键菜单
    this._updateMenu();

    // 左键单击显示/隐藏窗口
    this.tray.on('click', () => {
      this._toggleWindow();
    });

    // 双击显示窗口 (Windows 行为, 保留跨平台)
    this.tray.on('double-click', () => {
      if (this.mainWindow) {
        this.mainWindow.show();
        this.mainWindow.focus();
      }
    });

    console.log('[Tray] Created');
  }

  /**
   * 更新托盘菜单 (窗口状态变化时调用)
   */
  _updateMenu() {
    if (!this.tray) {
      return;
    }

    const isVisible = this.mainWindow && this.mainWindow.isVisible();

    const contextMenu = Menu.buildFromTemplate([
      {
        label: isVisible ? '隐藏窗口 (H)' : '显示窗口 (S)',
        click: () => this._toggleWindow(),
      },
      { type: 'separator' },
      {
        label: '关于 yuleOSH',
        click: () => {
          const { dialog } = require('electron');
          dialog.showMessageBox({
            type: 'info',
            title: '关于 yuleOSH',
            message: 'yuleOSH Desktop',
            detail: `版本: ${app.getVersion()}\n嵌入式AI开发全流程平台\nMIT License`,
          });
        },
      },
      { type: 'separator' },
      {
        label: '退出',
        click: () => {
          app.isQuitting = true;
          app.quit();
        },
      },
    ]);

    this.tray.setContextMenu(contextMenu);
  }

  /**
   * 切换窗口显示/隐藏
   */
  _toggleWindow() {
    if (!this.mainWindow) {
      return;
    }

    if (this.mainWindow.isVisible()) {
      this.mainWindow.hide();
    } else {
      this.mainWindow.show();
      this.mainWindow.focus();
    }
  }

  /**
   * 获取托盘图标路径
   * macOS: 使用 Template 格式 (自动适配 dark/light mode)
   * Linux: 使用普通 PNG
   */
  _resolveIconPath() {
    const assetsDir = path.resolve(__dirname, 'assets');

    if (process.platform === 'darwin') {
      // macOS 使用 Template 图标
      return path.join(assetsDir, 'iconTemplate.png');
    }

    return path.join(assetsDir, 'icon.png');
  }

  /**
   * 加载图标文件
   */
  _loadIcon(iconPath) {
    // macOS 需要手动标记为 Template
    if (process.platform === 'darwin') {
      const icon = nativeImage.createFromPath(iconPath);
      if (!icon.isEmpty()) {
        icon.setTemplateImage(true);
        return icon;
      }
    }

    // Linux: 创建适当尺寸的图标
    const icon = nativeImage.createFromPath(iconPath);
    if (!icon.isEmpty()) {
      return icon.resize({ width: TRAY_ICON_SIZE, height: TRAY_ICON_SIZE });
    }

    // 回退: 创建空白图标
    console.warn('[Tray] Icon not found, using fallback');
    return nativeImage.createEmpty();
  }

  /**
   * 窗口状态变化时更新托盘
   */
  notifyWindowStateChanged() {
    this._updateMenu();
  }

  /**
   * 销毁托盘
   */
  destroy() {
    if (this.tray) {
      this.tray.destroy();
      this.tray = null;
      console.log('[Tray] Destroyed');
    }
  }
}

// ─── 导出 ────────────────────────────────────────────

module.exports = TrayManager;
