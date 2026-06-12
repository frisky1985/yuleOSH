# SIL 仿真 Pipeline Step (Step 5.5)

## 概述

在 yuleOSH Pipeline 的固件编译之后、最终测试报告生成之前，插入 **Step 5.5: SIL 仿真验证**。该步骤利用 Vector SIL Kit 创建虚拟 ECU，运行软件在环仿真，提前发现固件行为缺陷。

---

## Pipeline 位置

```
Pipeline Steps:
  Step 1: 源码拉取 (git clone / checkout)
  Step 2: 依赖安装
  Step 3: 代码静态分析 (lint / SAST)
  Step 4: 单元测试
  Step 5: 固件编译 (Build)

  ╔══════════════════════════════════════════════════╗
  ║  Step 5.5: SIL 仿真验证 (NEW)                   ║
  ║  ┌──────────────────────────────────────────────╢
  ║  │ 5.5.1 编译固件（若 Step 5 未产出）          ║
  ║  │ 5.5.2 启动 SIL Kit Manager                  ║
  ║  │ 5.5.3 创建虚拟 ECU Participant               ║
  ║  │ 5.5.4 上载固件镜像                          ║
  ║  │ 5.5.5 运行 SIL 测试场景                     ║
  ║  │ 5.5.6 收集仿真结果                          ║
  ║  │ 5.5.7 停止 SIL Kit Manager                  ║
  ║  └──────────────────────────────────────────────╢
  ╚══════════════════════════════════════════════════╝

  Step 6: 集成测试
  Step 7: Pipeline 报告汇总
  Step 8: 产物归档 / 部署
```

---

## Step 5.5 详细流程

### 5.5.1 编译固件

如果上一 Step (Step 5) 已产出固件镜像（.elf / .hex / .bin），跳过此阶段；否则自动编译。

```yaml
# pipeline.yml
steps:
  - id: sil_simulation
    type: sil_kit
    config:
      registry_uri: "silkit://localhost:8500"
      timeout_s: 60
      participants:
        ecu_brake: "build/brake_controller.elf"
        ecu_motor: "build/motor_driver.elf"
      test_scenarios:
        - name: "emergency_brake"
          signals:
            inject: { "CAN_brake_pedal": 100 }
            expect: { "CAN_wheel_speed": 0, timeout_ms: 500 }
        - name: "motor_overcurrent"
          inject: { "LIN_motor_current": 350 }
          expect: { "LIN_error_flag": 1, timeout_ms: 200 }
```

### 5.5.2 启动 SIL Kit Manager

```python
from yuleosh_sil import SILKitAdapter

adapter = SILKitAdapter()
adapter.connect("silkit://localhost:8500")
# SIL Kit Manager 自动启动（或连接到已有 Registry）
```

- Manager 负责 Participant 注册、时钟同步、信号路由
- 如果 Registry 已存在，则复用；否则创建一个新的仿真会话

### 5.5.3 创建虚拟 ECU Participant

为配置中的每个 ECU 创建对应的 Participant：

```python
participants = {}
for name, fw_path in config["participants"].items():
    p = adapter.create_participant(name, simulation_name="pipeline-run-001")
    p.firmware_path = fw_path
    participants[name] = p
```

每个 Participant 内部模拟：

- 一个简单的虚拟 CPU（执行固件指令循环）
- CAN / LIN 收发器（发送和接收总线信号）
- DIO / PWM / ADC 外设（根据 SIL Kit Plugin 能力）
- 诊断服务（UDS on DoIP）

### 5.5.4 上载固件镜像

将编译好的固件二进制加载到每个 Participant 的虚拟存储器中：

```python
for p in participants.values():
    with open(p.firmware_path, "rb") as f:
        firmware_bin = f.read()
    p.load_firmware(firmware_bin)
```

对于 .elf 格式，可以使用 pyelftools 解析段并映射到 Participant 的虚拟地址空间。

### 5.5.5 运行 SIL 测试场景

根据配置的测试场景驱动仿真：

```python
for scenario in config["test_scenarios"]:
    # 注入输入信号
    for sig, val in scenario.get("inject", {}).items():
        participants["ecu_brake"].write_signal(sig, val)

    # 运行仿真（等待期望信号或超时）
    result = adapter.run_simulation(config)

    # 断言期望信号
    for sig, expected_val in scenario.get("expect", {}).items():
        timeout_ms = scenario["expect"].get("timeout_ms", 100)
        actual = participants["ecu_brake"].read_signal(sig, timeout_ms=timeout_ms)
        assert actual == expected_val, f"{sig}: expected {expected_val}, got {actual}"
```

### 5.5.6 收集仿真结果

SIL Kit 可返回以下数据：

| 数据类别 | 来源 | 用途 |
|----------|------|------|
| Participant 状态 | ILifecycleService | 确认各 ECU 正常/异常 |
| 信号轨迹 | IDataSubscriber | CAN/LIN 信号趋势，用于后续分析 |
| 仿真时钟 vs 真实时间 | ISystemMonitor | 性能指标（Realtime Factor） |
| 错误日志 | Participant 内部日志 | 固件异常、断言失败、看门狗触发 |
| 故障注入耦合 | 自定义 Signal Handler | 验证覆盖场景 |

```python
report = adapter.generate_report(all_results)
# report 结构见下节
```

### 5.5.7 停止 SIL Kit Manager

```python
adapter.shutdown()  # 停止所有 Participant，断开 Registry 连接
```

使用 `try/finally` 确保即使仿真崩溃也能执行 cleanup：

```python
try:
    adapter.connect(...)
    # ... run simulation ...
finally:
    adapter.shutdown()
```

---

## 报告格式

Step 5.5 输出到 Pipeline 上下文的报告格式：

```json
{
  "step": "sil_kit_simulation",
  "status": "passed",
  "summary": {
    "total_participants": 2,
    "total_simulation_time_ns": 45000000000,
    "simulation_time_s": 45.0,
    "scenarios_passed": 5,
    "scenarios_failed": 0
  },
  "participants": [
    {
      "name": "ecu_brake",
      "simulation": "pipeline-run-001",
      "firmware": "build/brake_controller.elf",
      "status": "RUNNING",
      "log_count": 12,
      "error_count": 0
    },
    {
      "name": "ecu_motor",
      "simulation": "pipeline-run-001",
      "firmware": "build/motor_driver.elf",
      "status": "RUNNING",
      "log_count": 8,
      "error_count": 1,
      "errors": ["WDT timeout at simulation time 12.3s"]
    }
  ],
  "scenarios": [
    {
      "name": "emergency_brake",
      "status": "passed",
      "duration_ms": 45.2
    },
    {
      "name": "motor_overcurrent",
      "status": "failed",
      "duration_ms": 12.1,
      "errors": ["Expected LIN_error_flag=1, got 0"]
    }
  ],
  "reports": [
    {
      "participant": "ecu_brake",
      "state": "STOPPED",
      "warnings": [],
      "errors": []
    }
  ]
}
```

---

## 配置选项

```yaml
sil_simulation:
  enabled: true                         # 是否跳过此 Step
  registry_uri: "silkit://localhost:8500"
  timeout_s: 60
  participants:
    <name>: <firmware_path>

  # 信号映射: 用户友好的信号名 → SIL Kit 信号 ID
  signal_map:
    CAN_brake_pedal:   "CAN::0x100::brake_pedal_position"
    CAN_wheel_speed:   "CAN::0x200::wheel_speed_front_left"
    LIN_motor_current: "LIN::0x01::motor_current"
    LIN_error_flag:    "LIN::0x01::error_flag"

  # 故障注入: 在仿真期间注入特定信号
  fault_injection:
    can_bus_off: false
    sensor_noise_level: 0.05

  # 性能指标阈值
  performance:
    min_realtime_factor: 0.5            # 低于此值标记警告
    max_simulation_time_ns: 120000000000  # 仿真时间上限 120s
```

---

## 错误处理

| 阶段 | 可能错误 | 处理方式 |
|------|----------|----------|
| Manager 启动 | 端口占用、Registry 不可达 | 重试 3 次，失败则标记 Step 为 SKIPPED |
| Participant 创建 | 名称冲突、固件路径无效 | 跳过该 Participant，标记 FAILED |
| 信号注入 | 信号名未定义 | 跳过该信号注入，记录 WARNING |
| 仿真超时 | 超过 timeout_s | 触发 graceful stop，收集部分结果 |
| Participant 崩溃 | Segmentation fault / 无限循环 | 记录 CRASHED 状态，尝试重启 1 次 |

---

## 最佳实践

1. **保持轻量** — SIL 仿真不是 HIL，重点是验证固件逻辑而非硬件时序
2. **故障注入** — 利用 SIL Kit 的信号层注入总线错误、传感器噪声，提高测试覆盖率
3. **回归测试** — 将 SIL 测试场景纳入 CI 回归集，每次提交自动运行
4. **并行仿真** — 多个不相关的 ECU 群组可以并行运行仿真，加速 Pipeline
5. **日志收集** — 每个 Participant 的 stdout/stderr 都应捕获到 Pipeline 日志
