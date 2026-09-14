# yuleOSH IoT 模板

本目录包含嵌入式项目模板，供 yuleOSH 流水线使用。所有模板遵循
[`template-spec.md`](./template-spec.md)（**构建系统无关**的统一验收规范）。

## 模板列表

| 模板 | 描述 | 构建系统 | 语言 |
|------|------|----------|------|
| `esp-idf-blinky/` | ESP-IDF Blinky 示例 (UART + GPIO + Wi-Fi Scan + FreeRTOS) | CMake | C |
| `gpio-led-chaser/` | STM32F103 流水灯 (纯 GPIO/定时器, 最干净 demo) | CMake | C |
| `mcu-firmware/` | MCU 固件核心 (合作式调度 / 看门狗 / 日志 / 配置 CRC) | Makefile | C++ |
| `ble-sensor/` | BLE 温度传感器 | Makefile | C |
| `can-bus/` | CAN 总线网关 | Makefile | C |
| `autosar/` | yuleASR AUTOSAR BSW (S32K312, MCAL+ECUAL+Services) | arxml + BSW | C |

## 使用方式

### CLI 复制（统一创建入口）
```bash
yuleosh template init <name> --from templates/<base>
```
复制基线模板（清掉 `.git` / `build` / `__pycache__` 等残留），得到
`docs/spec.md` + `src/` + `tests/` + 构建系统文件的新项目。

### 统一验证（pipeline 门禁，构建系统无关）
```bash
# 真实编排器（24 步）
run_pipeline docs/spec.md
# 或分层 CI
yuleosh ci run 1   # L1
yuleosh ci run 2   # L2
yuleosh ci run 3   # L3
```
硬门禁（`spec-check` / `claude-review` / `review-critical-safety` / `merge-gate` /
`test-qualification` 等）全 `passed` 或按计划 `skipped` 即视为走通。详见
[`template-spec.md`](./template-spec.md) GIVEN-1~5。

## 开发环境要求
各模板依赖见其自身构建文件（`CMakeLists.txt` / `Makefile` / `template.yaml`）。
- CMake 模板：CMake >= 3.16
- Makefile 模板：主机 `gcc`/`g++`（系统级测试由 `test-qualification` 门禁自动即时编译）
- AUTOSAR：完整 MCAL 工具链（非主机可模拟）
