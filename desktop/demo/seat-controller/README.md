# 座椅控制器（Seat Controller）Demo

基于 yuleOSH Desktop 的 Electron 进程结构实现的独立演示程序：主进程 + preload + 静态渲染页，
不依赖 Python 后端，可直接运行与打包。

## 功能

- **姿态调节**：靠背角度（90°–160°）、前后滑动、座垫高度、腿托角度、头枕高度
- **实时侧视姿态**：SVG 座椅随参数联动，含靠背旋转、腿托展开、整体滑移/升降
- **舒适功能**：三档加热、三档通风（气流动画）、四种按摩模式（波浪/脉冲/腰部）+ 强度
- **记忆位置**：M1/M2/M3 保存与调用，数字键 `1`/`2`/`3` 快捷调用
- **状态持久化**：姿态与记忆位置写入 Electron `userData/seat-state.json`，重启自动恢复

## 运行

复用 `desktop/node_modules` 中已安装的 Electron：

```bash
cd desktop
./node_modules/.bin/electron demo/seat-controller
```

无头环境（CI / 容器）：

```bash
cd desktop
xvfb-run -a ./node_modules/.bin/electron demo/seat-controller --no-sandbox
```

截图冒烟（渲染完成后截图并退出）：

```bash
xvfb-run -a ./node_modules/.bin/electron demo/seat-controller --no-sandbox \
  --screenshot=/tmp/seat-controller.png
```

## 目录结构

```
seat-controller/
├── main.js              # 主进程：窗口、菜单、状态读写、IPC
├── preload.js           # contextBridge 暴露最小存储接口
├── package.json
└── renderer/
    ├── index.html       # 界面结构与座椅 SVG
    ├── styles.css       # 深色车载 HMI 风格
    └── app.js           # 状态机、姿态映射、交互
```

## 说明

- 渲染进程开启 `contextIsolation` + `sandbox`，无 Node 访问权限；状态读写只经由白名单 IPC。
- 独立 `package.json`，不会被主桌面程序 `electron-builder.yml` 的 `files` 白名单打入 yuleOSH 安装包。
- 状态文件路径：`~/.config/座椅控制器/seat-state.json`（Linux）。
