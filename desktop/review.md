# yuleOSH Desktop — 正式审查报告

| 属性 | 值 |
|---|---|
| **审查对象** | yuleOSH Desktop 架构设计 + Electron 壳代码 |
| **审查版本** | v0.1.0-MVP |
| **审查日期** | 2026-07-10 |
| **审查角色** | 质量架构师（小马 🐴） |
| **审查依据** | spec.md (27 SHALL + 3 SHOULD + 2 MAY)、acceptance-matrix.md (33 AC) |
| **审查范围** | architecture.md, main.js (415L), server-manager.js, preload.js, tray.js, electron-builder.yml, self-check.md |

---

## 审查概况

| 维度 | 评分 (1-100) | 判定 |
|---|---|---|
| **总体** | **62** | **❌ 有条件通过** |

### 🟢 代码质量不错的部分
- 模块划分清晰（main / server-manager / tray / preload），职责单一
- 安全性核心配置正确（contextIsolation=true, nodeIntegration=false, contextBridge）
- 优雅关闭流程实现正确（SIGTERM → 5s → SIGKILL）
- IPC 通信接口设计良好，返回 cleanup 函数
- macOS tray Template 图标正确支持
- 健康检查间隔和超时参数完全对齐 spec

### 🔴 P0 阻塞项（5 项 — 必须修复才能进入下一阶段）
**不修复则 v0.1.0-MVP 不可发布。**

---

### P0-1：API 代理缺失 — SHALL-2.2.1 / SHALL-2.2.2 未实现

**严重程度：** 🔴 P0 · Spec 偏离

**描述：**
- **Spec 要求**：渲染进程发出的所有 API 请求（`/api/*`）均通过**主进程代理转发**到 `http://localhost:18788`，端口 18788 **不对外暴露**。
- **实际代码**：渲染进程通过 `fetch('http://localhost:18788/api/v1/...')` **直接调用** Python REST API（见 architecture.md §4.2）。main.js 中没有注册任何 protocol handler 或 net 模块代理。
- **后果**：
  1. 端口 18788 暴露给渲染进程（违反 SHALL-2.2.2）
  2. 渲染进程到 Python 后端存在跨域（CORS）问题——渲染进程实际从 `localhost:18789`（生产）或 `localhost:3000`（开发）加载，向 `localhost:18788` 发请求属于 cross-origin
  3. Python 后端必须配置 CORS 头，否则请求被浏览器拦截

**修复建议：**
方案 A（对齐 spec）：在 main.js 中注册主进程代理
- 使用 `net.request` 或 `session.protocol.registerHttpProtocol` 处理 `/api/*` 请求
- 渲染进程通过 IPC 发送请求或 preload 暴露的 fetch 封装

方案 B（改 spec）：如果团队决定直接用 fetch 调用后端
- 必须在 spec.md 和 acceptance-matrix.md 中修改 SHALL-2.2.1 / SHALL-2.2.2
- 必须在 Python 后端确保 CORS 头正确返回（`Access-Control-Allow-Origin: *`）
- 架构设计文档需与 spec 保持一致

---

### P0-2：后端运行时崩溃自动重启未实现 — SHALL-6.1.1 未实现

**严重程度：** 🔴 P0 · Spec 偏离

**描述：**
Spec 要求后端意外崩溃后主进程必须：
1. ✅ 检测子进程退出事件 — `process.on('close')` 实现
2. ❌ 在渲染进程显示错误覆盖层，文案 "后端服务异常，正在尝试重启…" — 仅发送 IPC 事件 `backend-crashed`，未确保显示
3. ❌ **自动重新 spawn 后端子进程** — 完全未实现
4. ❌ **重复健康检查流程** — 未实现
5. ❌ **连续 2 次失败停止重试** — 完全未实现

当前 main.js 中 `serverManager.on('crashed')` 仅向渲染进程发送 IPC 事件，不做任何恢复操作。

**修复建议：**
1. 在 `ServerManager` 中增加自动重启逻辑（重试计数器 + 最大重试次数）
2. 在 main.js 中处理 `crashed` 事件：发送 IPC → 显示覆盖层 → 自动重启
3. 实现连续 2 次失败后停止逻辑
4. 重启时复用现有的 `_waitForHealthy()` 健康检查逻辑

---

### P0-3：健康检查超时错误页 — SHALL-2.1.5 未完全对齐

**严重程度：** 🔴 P0 · Spec 偏离

**描述：**
- **Spec 要求**：健康检查超时（15 秒）后，**主进程必须在渲染进程中显示友好错误页**，包含 "Python 后端启动失败" 文案及重试按钮。
- **实际代码**：`startBackend()` 在超时后仅通过 IPC 发送 `backend-error` 事件，依赖前端自行处理。没有像 `showErrorPage()` 那样直接加载错误页面。
- **对比**：文件服务器启动失败时，main.js 有专用的 `showErrorPage()` 函数直接加载 data URL 错误页面（含样式和重试按钮）。而后端超时场景缺少同样的兜底处理。
- **风险**：如果前端代码未实现 `onBackendError` 监听器，错误将被静默忽略。

**修复建议：**
- 健康检查超时后，main 进程应直接使用 `mainWindow.loadURL()` 加载内置错误页面（类似 `showErrorPage()`），文案包含 "Python 后端启动失败" + 重试按钮
- IPC 事件可以作为补充通知，但主进程必须有兜底

---

### P0-4：Python 运行时未打包 — SHALL-5.1.4 未实现

**严重程度：** 🔴 P0 · Spec 偏离

**描述：**
- **Spec 要求**：构建产物中必须包含 Python 运行时，确保用户无需手动安装 Python。
- **实际代码**：`electron-builder.yml` 中的 `extraResources` 仅包含 `frontend/out/`，没有配置 Python 运行时或预编译二进制的打包。
- **后果**：用户必须手动安装 Python 并 `pip install yuleosh`，完全不符合 spec 承诺。如果用户安装了错误版本的 Python，启动即失败。

**修复建议：**
方案 A（使用 embedded Python）：配置 electron-builder 使用 python-shell 或 embedded Python（如 python-build-standalone）
方案 B（使用 PyInstaller）：将 Python 后端打包为独立二进制（`yuleosh-server`），打包时将其作为 extraResource
方案 C（Perl/python 环境检测改进）：如果 MVP 阶段不打包，至少需要：
- 在 spec 中明确降低到 SHOULD 级别
- 在 `server-manager.js` 中检测 Python 环境并给出清晰的安装指引
- 在启动失败时显示明确错误 "请安装 Python 3.10+"

---

### P0-5：窗口高度与 spec 不一致 — SHALL-1.1.2 偏离

**严重程度：** 🔴 P0 · Spec 偏离

**描述：**
- **Spec 要求**：主窗口尺寸默认 **1280×800**
- **验收矩阵 AC-1.1.2**：窗口创建时宽 1280、高 800
- **实际代码**：`width: 1280, height: 860`
- 860 可能是设计偏好（暗色背景更多垂直空间），但与 spec 和验收矩阵直接冲突。

**修复建议：** 统一使用 1280×800（对齐 spec），或在修改 spec 后对齐代码。验收矩阵也必须同步。

---

## 各维度评分

| 维度 | 评分 | 简要评估 |
|---|---|---|
| **Spec 对齐** | 50/100 | 27 条 SHALL 中 5 条 P0 偏离，另有 3 条 P1 偏离 |
| **安全性** | 85/100 | contextIsolation/nodeIntegration 正确；sandbox=false 需注记；`process.platform` 轻微泄露 |
| **错误处理** | 40/100 | 崩溃恢复完全缺失；超时错误页仅依赖前端；重复通知风险 |
| **跨平台** | 80/100 | macOS/Linux 分支处理基本正确；Wayland 兼容性需实测 |
| **代码质量** | 75/100 | 结构清晰、命名规范、注释充分；`before-quit` 模式脆弱；自测文档有数值错误 |
| **可测试性** | 45/100 | 自测覆盖大部分手动场景；缺少单元测试框架、CI 自动化测试；P0 缺失测试 |
| **验收矩阵满足** | 55/100 | 33 条 AC 覆盖 29 条 P0，其中 5 条 P0 未通过 |

---

## P1 重要问题（建议修复）

### P1-1：spawn 命令与验收矩阵不一致 — AC-2.1.2

- **AC 要求**：spawn 的 command 为 `yuleosh`，args 包含 `server`
- **实际代码**：`spawn('python3', ['-m', 'yuleosh.ui.server'])`
- **影响**：CI 验收测试若断言 `yuleosh` 为 command 字符串将直接失败
- **建议**：统一命令表达。如果团队决定用 `python3 -m` 方式（本开发环境需要），需修改 AC-2.1.1 / AC-2.1.2 放宽匹配条件

### P1-2：单实例锁缺失 — self-check 7.3

- **自测要求**："快速双击启动两次 → 只启动一个实例"
- **实际代码**：没有 `app.requestSingleInstanceLock()` 调用
- **后果**：用户双击两次会启动两个 Electron 进程，两个 Python 后端争抢 18788 端口
- **建议**：在 `app.whenReady()` 前添加 `const gotLock = app.requestSingleInstanceLock(); if (!gotLock) app.quit();`

### P1-3："视图" 菜单未在 spec 中定义

- **Spec SHALL-4.1.1** 定义了 文件/编辑/窗口/帮助 四个顶级菜单
- **实际代码** 多出了 "视图" 菜单（含重新加载/开发者工具/缩放/全屏）
- **影响**：开发者工具和重新加载在生产环境暴露可能带来安全/体验风险
- **建议**：要么更新 spec 包含 "视图" 菜单，要么在生产模式下隐藏开发者工具项

### P1-4：窗口菜单 "缩放" vs "切换全屏" 标签不一致

- **Spec 要求**：窗口菜单包含 "切换全屏"
- **实际代码**：`{ role: 'zoom', label: '缩放' }` — 使用了 `zoom` role（实际是 macOS 窗口缩放/最大化），非全屏 toggle
- **影响**：功能行为和 spec 描述不一致
- **建议**：用 `{ role: 'togglefullscreen', label: '切换全屏' }` 替换当前项，或更新 spec

### P1-5：CI 后端启动测试未实现 — SHALL-2.3.1 / AC-2.3.1

- **AC 要求**：CI 构建流程包含测试步骤：spawn Python 后端，健康检查端点返回 200
- **实际状态**：无测试文件、无 CI 配置、self-check 仅为手动测试
- **建议**：创建 `tests/` 目录，添加集成测试（例如 `tests/backend-spawn.test.js`），配置 GitHub Actions 在 PR 时自动运行

### P1-6：spec 与 acceptance-matrix 不一致（命令表述）

- **Spec SHALL-2.1.2**：`yuleosh server`（或等效的启动命令）— 留有余地
- **AC-2.1.1 / AC-2.1.2**：要求具体 command 为 `yuleosh`，args 为 `server` — **更严格**
- **影响**：同一个 SHALL 条款在 spec 和 AC 之间有歧义，导致代码无法同时满足两者
- **建议**：统一表述。如果 AC 是门禁标准，则代码必须对齐 AC；如果 AC 过严，则放宽 AC

---

## P2 建议改进（可延迟到下一个迭代）

### P2-1：tray 菜单中的假快捷键文字

`tray.js` 中菜单项显示 `"隐藏窗口 (H)"` 和 `"显示窗口 (S)"`，但实际没有注册任何快捷键加速器。用户看到 (H)/(S) 会以为有键盘快捷键。

**建议**：去掉后缀文字，或注册真实加速器。

### P2-2：重复的错误 IPC 通知

当 Python spawn 失败时：
1. `process.on('error')` → emit 'error' → wireBackendEvents 发送 `backend-error` IPC
2. `_waitForHealthy()` 超时 reject → `startBackend()` catch → 再次发送 `backend-error` IPC

渲染进程会收到两次相同的错误通知。

**建议**：在 ServerManager 中增加去重逻辑，或统一错误出口。

### P2-3：`before-quit` + `app.exit(0)` 模式脆弱

Electron 官方推荐使用 `will-quit` 事件做异步清理（该事件设计为等待 Promise）。当前使用 `event.preventDefault()` + `app.exit(0)` 虽然结果正确，但不是标准做法，后续维护可能引入竞态条件。

**建议**：改为 `app.on('will-quit', ...)` 配合 async 清理。

### P2-4：health check 路径不一致

- **Spec SHALL-2.1.3**：`/api/health`
- **实际代码**：`/api/v1/health`
- Spec 允许 "等价健康检查端点" 所以不阻塞，但应一致

**建议**：在架构文档中明确记录 health check 路径为 `/api/v1/health`，并确认 Python 后端实现了该端点。

### P2-5：self-check.md 中超时数值错误

self-check 2.2.2 写 "30s 后显示友好错误"，但实际超时为 15s。自测文档应与实现一致。

### P2-6：sandbox: false 需记录安全考量

`webPreferences.sandbox: false` 是因为 preload 需要 `require('electron')` 和 `process.platform`。此配置禁用沙箱，降低安全性。应在架构文档中记录此决策的风险和缓解措施。

### P2-7：缺失资产文件声明

`electron-builder.yml` 引用了以下文件，但这些文件可能在仓库中尚未创建或明确交付：
- `assets/icon.icns`
- `assets/dmg-background.png`
- `assets/iconTemplate.png`
- `assets/tray-error.png`（架构文档列出但 tray.js 未使用）
- `assets/entitlements.mac.plist`

**建议**：确认所有引用文件已就位，或从配置中移除未准备的文件。

### P2-8：health check 响应解析过于宽松

`_checkHealth()` 中只要满足 `json.ok === true || json.status === 'ok' || json.status === 'healthy'` 任一条件即视为健康。如果后端返回 `{ status: 'error' }` 但意外包含 `ok: true`，会被误判为健康。

**建议**：使用单一明确的判断标准，建议 `json.status === 'ok'`。

---

## Spec ↔ Acceptance Matrix 差异

以下差异需要在进入下一阶段前由小明（需求）裁决：

| # | 项 | spec.md | acceptance-matrix.md | 建议 |
|---|---|---|---|---|
| 1 | spawn 命令 | `yuleosh server`（或等效） | command=`yuleosh`, args=`['server']` | 放宽 AC 或对齐代码 |
| 2 | 窗口高度 | 1280×800 | 1280×800 | 统一（见 P0-5） |
| 3 | API 通信方式 | 主进程代理 | 主进程代理 | 统一决策（见 P0-1） |
| 4 | 健康检查路径 | `/api/health`（或等价） | 未明确 | 文档化统一路径 |
| 5 | 菜单结构 | 文件/编辑/窗口/帮助 | 无菜单详细检查 | 补充 P1-3 / P1-4 |

---

## 架构设计 vs 代码一致性

| 架构文档陈述 | 代码实现 | 一致？ |
|---|---|---|
| 健康检查在 `/api/v1/health` | ✅ server-manager.js 使用此路径 | ✅ |
| spawn `python3 -m yuleosh.ui.server` | ✅ server-manager.js 使用 | ✅ |
| 使用 OSH_PORT 环境变量 | ✅ server-manager.js 设置 | ✅ |
| 开发模式加载 `localhost:3000` | ✅ main.js 实现 | ✅ |
| API 直接 fetch 后端 | ✅ 无代理（**与 spec 冲突**） | ⚠️ |
| 关闭窗口=隐藏到托盘 | ✅ main.js 实现 | ✅ |
| 启动到 UI 无白闪 | ✅ `show: false` + `ready-to-show` | ✅ |
| `frontend/out/` 静态文件服务 | ✅ startLocalFileServer() | ✅ |

---

## 审查结论

### 总体判定：❌ 有条件通过

**条件（5 项 P0 修复完成后允许进入下一阶段）：**

1. ✅ **修复 P0-1**：实现 API 代理（或修改 spec 并确保 CORS）
2. ✅ **修复 P0-2**：实现后端崩溃自动重启 + 重试限制
3. ✅ **修复 P0-3**：健康检查超时由主进程直接加载错误页
4. ✅ **修复 P0-4**：配置 Python 运行时打包（或调整 spec 承诺级别）
5. ✅ **修复 P0-5**：窗口高度统一为 1280×800

### 安全底线核查 ✅

- contextIsolation=true ✅
- nodeIntegration=false ✅
- contextBridge 暴露有限 API ✅
- 无 Node.js API 泄露 ✅

### 下一阶段建议

1. **优先修复 5 项 P0**，完成后重新审查
2. **裁决 spec ↔ 架构设计差异**：API 代理方式需要小明决策
3. **建立自动化测试框架**：至少覆盖 ServerManager、IPC 通信、健康检查逻辑
4. **补充资产文件**：确认 mac 图标、dmg background、托盘图标等资产就位
5. **交付前执行全部 self-check 测试**（修正其中 30s→15s 的数值错误）

---

*审查人：小马 🐴 | 2026-07-10 | 如有分歧由小明裁决*
