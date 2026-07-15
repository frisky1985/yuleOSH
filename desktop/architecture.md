# yuleOSH Desktop — 架构设计文档

## 1. 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                yuleOSH Desktop (Electron)                │
│                                                         │
│  ┌──────────────────────┐       ┌────────────────────┐  │
│  │    Main Process      │       │  Renderer Process  │  │
│  │    (main.js)         │◄─────►│  (BrowserWindow)   │  │
│  │                      │  IPC  │                    │  │
│  │  ┌────────────────┐  │       │  Next.js Frontend  │  │
│  │  │  Window Manager │  │       │  (frontend/out/)   │  │
│  │  │  - createWindow │  │       │                    │  │
│  │  │  - dev/serve    │  │       │   API calls ────►  │  │
│  │  │  - menu         │  │       │  http://localhost  │  │
│  │  ├────────────────┤  │       │  :18788/api/v1/    │  │
│  │  │  Tray Manager   │  │       └────────────────────┘  │
│  │  │  (tray.js)      │  │                                │
│  │  ├────────────────┤  │        ┌────────────────────┐  │
│  │  │  Server Manager │  │       │  Python Backend    │  │
│  │  │  (server-       │──┼──────►│  (child_process)   │  │
│  │  │   manager.js)   │  │  spawn│  Port 18788        │  │
│  │  │                 │  │       │  REST API Server   │  │
│  │  └────────────────┘  │       └────────────────────┘  │
│  └──────────────────────┘                                │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────┐
│  OS Tray       │
│  (macOS/Linux) │
└────────────────┘
```

## 2. 进程架构

```
┌───────────────┐     HTTP (加载UI)    ┌──────────────────┐
│ Electron Main  │◄────────────────────►│ Browser Renderer │
│ (Node.js)      │                      │ (Chromium)       │
│                │                      │  Next.js Frontend│
│  child_process │                      │  localhost:port  │
│  .spawn()      │                      └──────────────────┘
│       │               HTTP (API)
│       ▼               ──────────►┌──────────────────┐
│  Python Server  │◄──────────────│ Python Backend    │
│  (yuleosh)      │              │ Port 18788          │
│  ─── health:    │              │  - REST API        │
│      /api/v1/   │              │  - Health check     │
│      health     │              │  - Store (SQLite)   │
└─────────────────┘               └──────────────────┘
```

### 进程关系说明

| 进程 | 角色 | 启动方式 | 端口 |
|---|---|---|---|
| Electron Main | 窗口/托盘/子进程管理 | `electron .` | N/A |
| Browser Renderer | 前端 UI 展示 | Electron 自动创建 | 动态 (dev) / 静态文件 (prod) |
| Python Backend | REST API 服务器 | Electron spawn | 18788 |

### 生命周期

```
用户双击启动
  │
  ▼
Electron Main Process 启动
  │
  ├── ServerManager.start() ← spawn Python 子进程
  │     │
  │     ├── 设置 OSH_PORT=18788
  │     ├── spawn python3 -m yuleosh.ui.server
  │     │
  │     └── 轮询 http://localhost:18788/api/v1/health
  │           │
  │           ├── 成功 (200) → 加载 UI
  │           │    │
  │           │    ├── Dev: 代理到 http://localhost:3000
  │           │    └── Prod: 加载本地静态文件
  │           │
  │           └── 失败 (超时 30s) → 显示错误页面
  │
  ├── 创建 BrowserWindow
  │
  └── 注册系统托盘
        │
        └── 右键菜单: 显示窗口 / 隐藏窗口 / 退出

用户点击退出
  │
  ▼
  ├── 关闭所有窗口
  ├── ServerManager.stop()
  │     │
  │     ├── SIGTERM → 等待 5s → SIGKILL
  │     └── 确认进程终止
  ├── 注销托盘图标
  └── app.quit()
```

## 3. 组件模块划分

### 3.1 Main Process 模块

| 模块文件 | 职责 |
|---|---|
| `main.js` | 应用入口：创建窗口、加载前端、设置菜单、IPC 通信 |
| `preload.js` | 安全桥接：通过 `contextBridge` 暴露有限 API |
| `server-manager.js` | Python 子进程生命周期管理 |
| `tray.js` | 系统托盘：图标、右键菜单、窗口切换 |

### 3.2 Renderer Process

100% 复用现有 `frontend/` 代码，无需修改。通过 `preload.js` 暴露的 API 与主进程通信。

## 4. 通信机制

### 4.1 Electron Main ↔ Renderer (IPC)

通过 `contextBridge` + `ipcRenderer` 安全通信：

```javascript
// preload.js — 暴露给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  getBackendUrl: () => 'http://localhost:18788',
  platform: process.platform,
  onBackendReady: (callback) => ipcRenderer.on('backend-ready', callback),
  onBackendError: (callback) => ipcRenderer.on('backend-error', callback),
  onBackendStopped: (callback) => ipcRenderer.on('backend-stopped', (_e, code) => ...),
})
```

### 4.2 Renderer ↔ Python Backend (HTTP)

前端通过 `fetch('http://localhost:18788/api/v1/...')` 直接调用 Python REST API。
这是最可靠的方式，因为：
- 前后端分离，不耦合
- 无需 WebSocket 代理
- 可独立调试

### 4.3 Electron Main ↔ Python Subprocess (stdio + signals)

| 方向 | 方式 |
|---|---|
| Main → Python | `process.stdin.write()` / `process.kill(signal)` |
| Python → Main | `process.stdout.on('data')` / `process.stderr.on('data')` |
| 终止信号 | `SIGTERM` → 5s 等待 → `SIGKILL` |

## 5. 文件目录结构

```
yuleOSH/
├── desktop/                          # ← 新增: Electron 壳代码
│   ├── package.json                  # Electron + electron-builder 依赖
│   ├── main.js                       # 主进程入口
│   ├── preload.js                    # 安全桥接
│   ├── server-manager.js             # Python 子进程管理
│   ├── tray.js                       # 系统托盘
│   ├── electron-builder.yml          # 打包配置
│   ├── assets/                       # 桌面版静态资源
│   │   ├── icon.png                  # 应用图标 (512x512)
│   │   ├── icon.icns                 # macOS 图标
│   │   ├── iconTemplate.png          # 托盘图标 (Template 格式, 22x22)
│   │   └── tray-error.png            # 错误状态托盘图标
│   ├── architecture.md               # 架构文档
│   └── self-check.md                 # 自测检查单
│
├── frontend/                         # 现有: Next.js 前端
│   ├── package.json
│   ├── next.config.ts
│   └── out/                          # 静态导出输出
│       ├── index.html
│       ├── login/index.html
│       ├── dashboard/index.html
│       └── ...
│
└── src/
    └── yuleosh/                      # 现有: Python 后端
        ├── api/
        ├── ui/
        │   └── server.py             # HTTP Server (入口)
        ├── cli/
        └── ...
```

## 6. 数据流

```
┌─────────────────────────────────────────────────────────────┐
│  用户操作 (点击/输入)                                        │
│      │                                                      │
│      ▼                                                      │
│  Next.js React App  (Renderer Process)                      │
│      │                                                      │
│      ├── 静态资源: 由 Electron local HTTP server 或          │
│      │   Next.js dev server 提供                              │
│      │                                                      │
│      └── API 请求: fetch('http://localhost:18788/api/v1/...') │
│              │                                              │
│              ▼                                              │
│  Python HTTP Server  (Port 18788)                           │
│      │                                                      │
│      ├── /api/v1/health   → health.py                       │
│      ├── /api/v1/pipeline → pipeline.py                     │
│      ├── /api/v1/spec     → spec.py                         │
│      ├── /api/v1/ci       → ci.py                           │
│      └── ...                                                │
│              │                                              │
│              ▼                                              │
│  SQLite Store  (yuleosh/store.py)                           │
│      │                                                      │
│      └── JSON Response                                      │
│              │                                              │
│              ▼                                              │
│  UI 更新 (React 状态)                                        │
└─────────────────────────────────────────────────────────────┘
```

### 数据流关键路径

1. **用户登录**: UI → fetch POST /api/v1/auth/login → Python 验证 → 返回 token → UI 存储 token
2. **运行 Pipeline**: UI → fetch POST /api/v1/pipeline/run → Python 调度 Agent → 轮询状态 → UI 更新进度
3. **查看 Dashboard**: UI → fetch GET /api/v1/dashboard → Python 查询 Store → 返回统计数据 → UI 渲染图表

## 7. 关键决策说明

### 7.1 为何选择 Electron 而非 Tauri

| 维度 | Electron | Tauri |
|---|---|---|
| 前端代码复用 | 100% (Chromium) | 依赖系统 WebView |
| `next/image` + static export | 完美兼容 | 需适配 |
| 社区生态 | 成熟、工具链完善 | 相对较新 |
| Python 子进程管理 | 标准 child_process | 需 Rust 层桥接 |
| 打包体积 | ~200MB (含 Chromium) | ~5MB (系统 WebView) |
| 开发速度 | 快 (团队已熟悉 JS 生态) | 慢 (需 Rust) |

结论：MVP 阶段 Electron 开发效率最高，后续可评估迁移到 Tauri。

### 7.2 静态文件服务策略

**开发模式** (`isDev=true`):
- BrowserWindow 加载 `http://localhost:3000` (Next.js dev server)
- 前端 HMR 热更新正常工作

**生产模式** (`isDev=false`):
- Electron 内嵌 HTTP server 提供静态文件
- 映射 `/yuleOSH/*` → `frontend/out/*` (处理 Next.js assetPrefix)
- API 调用直接发往 `localhost:18788`

### 7.3 服务端口 18788

Python 后端默认端口 8080，但桌面版指定 18788 以避免与系统其他服务冲突。

启动方式: `OSH_PORT=18788 python3 -m yuleosh.ui.server`

### 7.4 macOS Tray Icon Template

macOS 系统托盘图标使用 Template 格式：
- 图标文件需命名为 `xxxTemplate.png`（或 `xxxTemplate@2x.png`）
- macOS 自动根据深色/浅色模式调整图标颜色
- Electron 侧的字符串应为 `xxxTemplate.png`（不含 @2x）
- 图标应为纯黑白/透明设计

### 7.5 优雅关闭策略

```
退出事件触发
  │
  ├── IPC: 通知渲染进程
  ├── Python: SIGTERM → 紧耦合等待 5s
  │     │
  │     ├── 进程已退出 → OK
  │     └── 超时未退出 → SIGKILL
  │
  └── 确认所有子进程终止后 app.quit()
```

### 7.6 安全性考虑

- `preload.js` 使用 `contextBridge`，不在 renderer 中暴露 Node.js API
- 启用 `contextIsolation: true`、`nodeIntegration: false`
- `server-manager.js` 使用固定的命令，不拼接用户输入
- 遵循 Electron 安全最佳实践
