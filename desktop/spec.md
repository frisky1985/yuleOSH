## 概述

| 属性 | 值 |
|---|---|
| **标题** | yuleOSH Desktop — Spec 契约层 |
| **版本** | v0.1.0-MVP |
| **状态** | 草案 |
| **编写日期** | 2026-07-10 |
| **负责角色** | 质量架构师（小马） |
| **上游依赖** | startup-analysis.md |
| **目标读者** | 开发（小克）、需求（小明） |

---

## 1. 电子壳（Electron Shell）

### 1.1 窗口管理

- **SHALL-1.1.1** 应用启动时创建主窗口，加载 `frontend/out/index.html`（或等价的渲染入口）。
- **SHALL-1.1.2** 主窗口尺寸默认 1280×860，支持用户缩放。
- **SHALL-1.1.3** 主窗口标题栏显示 "yuleOSH"。
- **SHALL-1.1.4** 主窗口支持原生最小化/最大化/关闭操作。
- **SHOULD-1.1.5** 主窗口关闭时不会终止进程，而是隐藏至系统托盘（参见明确的中断/重新启动或行为取决于如何设置 — 见 SHALL-3.1）。

### 1.2 进程模型

- **SHALL-1.2.1** Electron 启动后维护三个进程角色：主进程（main）、渲染进程（renderer）、预加载脚本（preload）。
- **SHOULD-1.2.2** 渲染进程与主进程之间的通信应通过 contextBridge 暴露的安全 API 进行，而非直接使用 ipcRenderer。
- **SHALL-1.2.3** nodeIntegration 在渲染进程中必须设置为 `false`，contextIsolation 必须设置为 `true`。

### 1.3 前端复用

- **SHALL-1.3.1** 渲染进程加载的静态文件必须来自 `frontend/out/` 目录（`next build && next export` 的输出）。
- **SHAL-1.3.2** 渲染进程在启动后的所有导航（SPA 路由）由 React/Next.js 前端自行控制，Electron 不干预前端路由。

---

## 2. 内嵌 Python 后端

### 2.1 服务生命周期

- **SHALL-2.1.1** Electron 主进程启动后，通过 `child_process.spawn` 启动 Python 后端子进程。
- **SHALL-2.1.2** Python 后端子进程的命令为 `yuleosh server`（或等效的启动命令）。
- **SHALL-2.1.3** 启动后，主进程每 500ms 轮询 `http://localhost:18788/api/health`（或等价健康检查端点），最长等待 15 秒。
- **SHALL-2.1.4** 健康检查通过后，主进程通知渲染进程加载前端页面。
- **SHALL-2.1.5** 健康检查超时（15 秒）后，主进程必须在渲染进程中显示友好错误页，包含 "Python 后端启动失败" 文案及重试按钮。
- **SHALL-2.1.6** 应用退出时（包括系统托盘退出），主进程必须向 Python 后端子进程发送 SIGTERM，并等待不超过 5 秒。超时后发送 SIGKILL。

### 2.2 API 代理

- **SHALL-2.2.1** 渲染进程通过 `fetch('http://localhost:18788')` 直接调用 Python REST API。
- **SHALL-2.2.2** Python 后端必须配置 CORS 头，允许来自渲染进程加载来源的跨域请求。

### 2.3 后端集成测试

- **SHALL-2.3.1** 构建系统必须包含测试，验证 Python 后端子进程可以正常启动且健康检查端点返回 200。

---

## 3. 系统托盘

### 3.1 托盘功能

- **SHALL-3.1.1** 应用启动后必须在系统托盘中显示图标。
- **SHALL-3.1.2** 托盘图标点击（macOS）或右键点击 必须弹出上下文菜单。
- **SHALL-3.1.3** 上下文菜单必须包含以下项目：
  - "显示窗口"（Show Window）— 恢复/聚焦主窗口
  - "隐藏窗口"（Hide Window）— 隐藏主窗口
  - "退出"（Quit）— 完全退出应用（含终止 Python 后端）
- **SHALL-3.1.4** 关闭主窗口（点击红色关闭按钮）的默认行为是隐藏到托盘而非退出。
- **SHALL-3.1.5** 退出应用程序的唯一途径是系统托盘菜单中的 "退出" 或原生菜单中的 "退出"。

---

## 4. 原生菜单

### 4.1 应用菜单结构

- **SHALL-4.1.1** 应用菜单栏包含以下顶级菜单：
  - **文件（File）**：新建项目、打开项目、分隔线、退出
  - **编辑（Edit）**：撤销、重做、分隔线、剪切、复制、粘贴、全选
  - **窗口（Window）**：最小化、切换全屏
  - **帮助（Help）**：关于 yuleOSH
- **SHOULD-4.1.2** 文件菜单中的 "打开项目" 应调用原生 `dialog.showOpenDialog`，限制选择目录。
- **SHOULD-4.1.3** 选中目录后，应将路径通过 IPC 发送给渲染进程，由前端后续处理。

---

## 5. 构建与分发

### 5.1 目标平台

- **SHALL-5.1.1** 必须提供 macOS（.dmg）的构建产物。
- **SHALL-5.1.2** 必须提供 Linux（.AppImage）的构建产物。
- **MAY-5.1.3** 可为 Windows（.exe 或 .msi）提供构建产物。
- **SHOULD-5.1.4** 构建产物中应包含 Python 运行时（或使用 PyInstaller 打包）。当前 MVP 版本用户需自行安装 Python 3.10+。

### 5.2 非功能约束

- **SHALL-5.2.1** 构建产物（含内嵌 Python 运行时）解压后占用磁盘空间不得超过 300MB。
- **SHALL-5.2.2** 从用户双击图标到界面完全可用（健康检查通过 + 前端渲染完毕）的总时间不得超过 5 秒（以主流 M 系列 Mac / 等效硬件为基准）。

---

## 6. 错误处理

### 6.1 后端异常

- **SHALL-6.1.1** 如果在运行期间 Python 后端子进程意外崩溃（exit code ≠ 0），主进程必须：
  1. 检测到子进程退出事件
  2. 在渲染进程中显示错误覆盖层，文案为 "后端服务异常，正在尝试重启…"
  3. 自动重新 spawn 后端子进程
  4. 重复健康检查流程（超时仍设为 15 秒）
  5. 如果重启失败（连续 2 次），显示 "后端服务异常，请检查日志后重试" 并停止自动重试
- **SHALL-6.1.2** 渲染进程网络错误（例如代理不可达）必须在前端层面处理，显示 "网络连接异常" 提示。

---

## 7. 场景定义（GIVEN / WHEN / THEN）

### 场景 1：正常启动流程

```
GIVEN 用户已安装 yuleOSH Desktop v0.1.0-MVP
  AND 系统环境中 yuleosh Python 后端可执行
WHEN 用户双击应用图标启动
THEN Electron 主进程启动
  AND Python 后端子进程 spawn 成功
  AND 健康检查端点 /api/health 在 15 秒内返回 200
  AND 渲染进程加载前端页面并显示登录界面
  AND 系统托盘图标出现
  AND 总启动时间 <= 5 秒
```

### 场景 2：后端启动失败

```
GIVEN 用户已安装 yuleOSH Desktop v0.1.0-MVP
  AND Python 后端不可执行（例如二进制损坏或缺失）
WHEN 用户双击应用图标启动
THEN Electron 主进程启动
  AND Python 后端子进程 spawn 失败或健康检查超时（>15 秒）
  AND 渲染进程显示友好错误页，文案包含 "Python 后端启动失败"
  AND 错误页包含重试按钮
  AND 系统托盘图标仍然出现（用户可退出）
```

### 场景 3：关闭窗口 ≠ 退出

```
GIVEN yuleOSH Desktop 正在运行
  AND 窗口处于打开状态
WHEN 用户点击窗口关闭按钮
THEN 主窗口隐藏
  AND 应用继续在系统托盘运行
  AND Python 后端子进程继续运行
  AND 用户可通过托盘菜单 "显示窗口" 恢复窗口
```

### 场景 4：正常退出

```
GIVEN yuleOSH Desktop 正在运行
WHEN 用户通过系统托盘菜单点击 "退出"
  OR 用户通过原生菜单点击 "退出"
THEN SIGTERM 发送到 Python 后端子进程
  AND 等待最多 5 秒后发送 SIGKILL（如未退出）
  AND 主窗口关闭
  AND 托盘图标移除
  AND 所有进程终止
```

### 场景 5：后端运行时崩溃

```
GIVEN yuleOSH Desktop 正在运行
  AND Python 后端子进程正常工作
WHEN Python 后端子进程意外退出（exit code ≠ 0）
THEN 主进程检测到子进程退出
  AND 渲染进程显示 "后端服务异常，正在尝试重启…"
  AND 主进程自动重新 spawn 后端子进程
  AND 执行健康检查（最长 15 秒）
  AND 重启成功 → 恢复服务
  AND 重启连续失败 2 次 → 显示 "后端服务异常，请检查日志后重试" 并停止自动重试
```

### 场景 6：原生文件选择

```
GIVEN yuleOSH Desktop 正在运行
  AND 用户处于 Dashboard 登录状态
WHEN 用户点击 "打开项目"
  OR 用户通过菜单 "文件 → 打开项目"
THEN 系统弹出原生目录选择对话框
  AND 用户选择目录后，路径通过 IPC 转发给渲染进程
```

### 场景 7：构建产物验证（macOS）

```
GIVEN CI 环境（macOS runner）
WHEN 执行 electron-builder macOS 构建
THEN 产物为 .dmg 文件
  AND 解压后占用空间 <= 300MB
```

### 场景 8：构建产物验证（Linux）

```
GIVEN CI 环境（Linux runner）
WHEN 执行 electron-builder Linux 构建
THEN 产物为 .AppImage 文件
  AND 解压后占用空间 <= 300MB
```

---

## 8. 条款汇总

| 类型 | 数量 |
|---|---|
| SHALL | 26 |
| SHOULD | 4 |
| MAY | 2 |

> SHALL 条款 = 必须实现的契约承诺，每一条对应验收矩阵中的一条判定项。
