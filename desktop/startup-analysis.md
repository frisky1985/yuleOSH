# yuleOSH Desktop — Superpowers 启动分析

## 为什么做？

yuleOSH 当前是纯 Web 架构：Next.js 前端 + Python REST API 后端。嵌入式工程师的实际工作场景决定了桌面版的必要性：

1. **离线/内网环境** — 嵌入式开发常在封闭网络、产线旁、实验室，没有云端服务器
2. **本地文件系统** — 拖拽 .hex/.elf/.map → 项目导入、直接打开项目目录、自动监控文件变更
3. **系统集成** — 系统托盘后台运行、构建完成弹通知、右键菜单快速启动 Pipeline
4. **原生体验** — 嵌入式工程师习惯 IDE 类原生应用，Web 页面在效率场景有天然短板
5. **IDE 生态入口** — 桌面版可开 WebSocket 与 VS Code/CLion 通信，是 IDE Extension 的前置步骤

## 做什么？— 最小可用产品（MVP）

### 技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| Desktop Shell | **Electron** | 复用 100% Next.js 前端代码，生态成熟，社区庞大 |
| Python 后端嵌入 | **child_process.spawn** | 用户不需要手动启动 server，Electron 启动时自动拉起 |
| 打包 | **electron-builder** | macOS(dmg) / Windows(exe) / Linux(AppImage) |
| 自动更新 | **electron-updater** | GitHub Releases 自动推送 |

### MVP 功能清单

1. **Electron 壳包装现有 Next.js 前端**
   - 加载 `frontend/out/` 静态文件（或 dev 模式代理到 Next.js dev server）
   - 原生窗口（标题栏、最小化/最大化/关闭）
   - 系统托盘（后台运行、右键菜单：显示窗口/退出）

2. **内嵌 Python 后端**
   - Electron 启动时自动 spawn `yuleosh` server 子进程
   - 前端 API 请求代理到本地 `http://localhost:18788`
   - Electron 退出时自动 kill Python 子进程
   - 健康检查：启动后轮询 API 端点，就绪后加载前端

3. **原生菜单**
   - 应用菜单：文件(新建项目/打开项目/退出)、编辑(撤销/重做)、窗口、帮助
   - 项目打开：原生 dialog.selectDirectory() → 传入 Python 后端

### 非功能需求

- 打包体积 < 300MB（含内嵌 Python runtime）
- 启动时间 < 5s（从双击到界面可用）
- macOS / Linux 双平台（Windows 后续）

## 现有代码复用

| 现有模块 | 复用方式 |
|---|---|
| `frontend/` (Next.js 16 + React 19) | 作为 Electron renderer 进程，100% 复用 |
| `src/yuleosh/` (Python backend) | 作为子进程启动，通过 HTTP 通信 |
| `.yuleosh/` (配置目录) | 桌面版读写 `~/.yuleosh/` 配置 |

## 额外文件

- `desktop/` — Electron shell 代码放在 `yuleOSH/desktop/`
  - `package.json` — Electron 依赖
  - `main.js` — Electron 主进程
  - `preload.js` — 安全上下文桥接
  - `tray.js` — 系统托盘
  - `server-manager.js` — Python 子进程管理
  - `electron-builder.yml` — 打包配置

## 验收标准

1. ✅ 双击启动 → 显示 yuleOSH 登录页
2. ✅ 登录后 Dashboard 完整可用
3. ✅ 系统托盘图标出现，右键可显示/隐藏/退出
4. ✅ 关闭窗口 → 后台继续运行（系统托盘）
5. ✅ 退出应用 → Python 后端自动终止
6. ✅ Python 后端启动失败 → 显示友好错误页
7. ✅ macOS .dmg 构建成功
8. ✅ Linux AppImage 构建成功
