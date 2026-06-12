# ESP-IDF Blinky 示例 (yuleOSH 模板)

## 概述

一个最小 ESP-IDF v5.x 项目，演示：

- **GPIO 输出** — GPIO2 驱动 LED 以 1s 周期闪烁
- **UART 控制台** — 通过 ESP_LOG 输出系统日志（默认 9600 baud）
- **Wi-Fi 扫描** — 每 30 秒扫描周围 AP，打印 SSID/RSSI/信道/认证类型
- **FreeRTOS 任务** — `blink_task` + `wifi_task` 两个独立任务

## 硬件需求

| 引脚 | 连接         |
|------|-------------|
| GPIO2 | LED (阳极 → 330Ω → GPIO2, 阴极 → GND) |
| TX (GPIO1) | UART 转 USB 串口模块 |
| RX (GPIO3) | UART 转 USB 串口模块 |

> 💡 大多数 ESP32 开发板（如 ESP32-DevKitC）已板载串口芯片和 GPIO2 LED。

## 构建 & 烧录

```bash
# 1. 设置目标芯片 (ESP32/ESP32-S3/ESP32-C3)
idf.py set-target esp32

# 2. 配置 (可选)
idf.py menuconfig

# 3. 构建
idf.py build

# 4. 烧录 + 监视
idf.py flash monitor
```

按 `Ctrl+]` 退出 monitor。

## 输出示例

```
I (123) yuleOSH: yuleOSH Blinky 示例启动
I (123) yuleOSH: UART 波特率: 9600
I (123) yuleOSH: LED GPIO: 2
I (123) yuleOSH: 任务已创建 — Hello from yuleOSH!
I (223) yuleOSH: LED ON
I (723) yuleOSH: LED OFF
I (1523) yuleOSH: 开始 Wi-Fi 扫描...
I (3523) yuleOSH: 发现 8 个 AP:
I (3523) yuleOSH:   [ 0] SSID: MyHomeWiFi                      RSSI: -45  CH: 6   WPA2_PSK
I (3523) yuleOSH:   [ 1] SSID: Neighbor_5G                     RSSI: -67  CH: 149 WPA2_PSK
...
```

## Kconfig 选项

| 选项               | 默认值 | 说明          |
|--------------------|--------|--------------|
| `CONFIG_BLINK_GPIO` | 2      | LED GPIO 引脚 |
