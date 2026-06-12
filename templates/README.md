# yuleOSH IoT 模板

本目录包含嵌入式项目模板，供 yuleOSH 流水线使用。

## 模板列表

| 模板 | 描述 | 框架 |
|------|------|------|
| `esp-idf-blinky/` | ESP-IDF Blinky 示例 (UART + GPIO + Wi-Fi Scan + FreeRTOS) | ESP-IDF v5.x |

## 使用方式

### CLI 复制
```bash
cp -r templates/esp-idf-blinky/ ./my_project
```

### 流水线引用
在 `pipeline.json` 或 CI 配置中引用模板路径：
```json
{
  "template": "templates/esp-idf-blinky"
}
```

## 开发环境要求

- ESP-IDF v5.x (通过 `export.sh` 或 `idf.py` 激活)
- CMake >= 3.16
- 目标芯片: ESP32 / ESP32-S3 / ESP32-C3 等
