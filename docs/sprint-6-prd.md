# Sprint 6: 文档站 + 模板库 + 安全加固 (Ralph Loop)

## 目标
补齐文档缺口、预设模板、加固安全，让 yuleOSH 对开发者和团队都 ready。

## 任务清单

- [ ] T6-1: 在线文档站
  - 创建 src/ui/marketing/docs.html — 开发者文档页
  - 介绍 yuleOSH 架构、安装、配置、API 参考
  - 内嵌 CLI 命令一览表
  - 响应式、暗色主题
  
- [ ] T6-2: 嵌入式项目模板库
  - 创建 templates/ 目录
  - 3 个内置模板:
    - templates/ble-sensor/ — BLE 传感器固件 (C)
    - templates/can-bus/ — CAN Bus 车载通信 (C++)
    - templates/mcu-firmware/ — MCU 裸机固件 (C)
  - 每个模板含: src/, tests/, docs/spec.md
  - 命令: yuleosh template create <project> --from <template>

- [ ] T6-3: 安全加固
  - 添加速率限制 (src/api/ratelimit.py)
  - 添加请求日志审计 (src/api/audit.py)
  - 添加 CSP/安全头 (src/ui/server.py)
  - 添加 API 输入校验中间件

- [ ] T6-4: 性能优化
  - src/pipeline/run.py 数据库查询优化
  - src/ci/run.py 测试发现缓存
  - 减少不必要的文件 I/O

## 验证
- 33+ tests 通过
- 无回归
