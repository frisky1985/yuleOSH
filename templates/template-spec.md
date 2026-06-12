# yuleOSH 模板规范 — template-spec.md

> 定义所有模板必须满足的 GIVEN/WHEN/THEN 验收条件。

---

## 通用条件（所有模板）

### GIVEN-1: 目录结构完整
GIVEN 一个模板目录  
WHEN 检查目录结构  
THEN 必须包含:
- `CMakeLists.txt` — 顶层项目 CMake
- `main/CMakeLists.txt` — 组件 CMake
- `main/main.c` — 主源文件
- `sdkconfig` — 默认配置
- `README.md` — 项目说明

### GIVEN-2: CMake 语法正确
GIVEN 模板的 `CMakeLists.txt`  
WHEN 使用 `cmake -S . -B build`（在 IDF 环境中）进行语法检查  
THEN 必须:
- `cmake_minimum_required(VERSION 3.16)` 存在
- `include($ENV{IDF_PATH}/tools/cmake/project.cmake)` 存在
- `project(...)` 定义了项目名

### GIVEN-3: 组件 CMake 语法正确
GIVEN 模板的 `main/CMakeLists.txt`  
WHEN 检查组件注册  
THEN 必须:
- 包含 `idf_component_register(SRCS ...)`
- `SRCS` 列出了所有 `.c` 源文件
- `REQUIRES` 列出了所有外部依赖

---

## esp-idf-blinky 模板验收条件

### GIVEN-B1: GPIO 闪烁
GIVEN `esp-idf-blinky` 模板  
WHEN 编译并烧录到 ESP32  
THEN `blink_task` 应在 GPIO2 上输出 1Hz 方波 (500ms ON / 500ms OFF)

### GIVEN-B2: UART 日志输出
GIVEN `esp-idf-blinky` 模板  
WHEN 通过串口监视器连接（9600 baud）  
THEN 应输出:
- `yuleOSH Blinky 示例启动`
- `Hello from yuleOSH!`
- 周期性 `LED ON` / `LED OFF`

### GIVEN-B3: Wi-Fi 扫描
GIVEN `esp-idf-blinky` 模板  
WHEN 启动后 30 秒内  
THEN `wifi_task` 应执行扫描并输出 `发现 N 个 AP:` 及扫描列表

### GIVEN-B4: FreeRTOS 多任务
GIVEN `esp-idf-blinky` 模板  
WHEN 检查源代码  
THEN 必须:
- 存在 `blink_task` 和 `wifi_task` 两个独立 `xTaskCreate` 调用
- 两个任务运行在不同的栈空间（blink: 2048, wifi: 4096）

### GIVEN-B5: 可配置 GPIO
GIVEN `esp-idf-blinky` 模板  
WHEN 查看 `sdkconfig`  
THEN `CONFIG_BLINK_GPIO` 默认值为 2

### GIVEN-B6: 波特率兼容
GIVEN `esp-idf-blinky` 模板  
WHEN 查看 `sdkconfig`  
THEN `CONFIG_ESP_CONSOLE_UART_BAUDRATE` 默认值为 9600  
WHEN 查看 `main.c`  
THEN `UART_BAUD` 常量定义为 115200（注释值，实际由 sdkconfig 控制）

---

## 验收状态

| 条件 | 状态 | 备注 |
|------|------|------|
| GIVEN-1 | ✅ | 目录结构完整 |
| GIVEN-2 | ✅ | 顶层 CMakeLists.txt 语法正确 |
| GIVEN-3 | ✅ | 组件 CMakeLists.txt 语法正确 |
| GIVEN-B1 | ⏳ | 需实际硬件验证 |
| GIVEN-B2 | ⏳ | 需实际串口验证 |
| GIVEN-B3 | ⏳ | 需 Wi-Fi 环境验证 |
| GIVEN-B4 | ✅ | 代码 `xTaskCreate` 存在 |
| GIVEN-B5 | ✅ | sdkconfig CONFIG_BLINK_GPIO=2 |
| GIVEN-B6 | ✅ | 9600 sdkconfig / 115200 代码 |

> ✅ = 静态检查通过  
> ⏳ = 需运行时验证  
> ❌ = 未通过
