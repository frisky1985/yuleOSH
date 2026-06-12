# yuleOSH SIL Kit 集成方案

## 什么是 SIL Kit？

**SIL Kit**（Software-in-the-Loop Kit）是 Vector Informatik 与 Synopsys 于 2025年3月宣布合作后开源的**车辆级数字孪生库**，采用 **MIT License**。

它允许用户在纯软件环境中创建虚拟 ECU（vECU）进行软件在环仿真，无需真实硬件即可验证 ECU 固件行为，打通从 Model-in-the-Loop 到 Hardware-in-the-Loop 之间的开发断层。

### SIL Kit 核心组件

| 组件 | 职责 | 说明 |
|------|------|------|
| **SIL Kit Manager** | 仿真生命周期管理 | 负责创建/销毁仿真、管理 Participant 注册、协调仿真同步、收集仿真元数据 |
| **VAsio** | 跨进程通信层 | 基于 ASIO 的高性能异步 IPC 框架，支持本地进程间通信与远程节点连接，提供 Pub/Sub、RPC 等通信模式 |
| **Participant** | 仿真节点 | 一个仿真中独立的计算实体，每个 Participant 可以模拟一个 ECU、一个传感器、一个执行器或一个诊断模块 |
| **Registry** | 服务发现 | 轻量级注册中心，Participant 通过 Registry URI 发现彼此并建立通信 |

### 为什么要集成 SIL Kit？

- **避免被 Vector 生态封堵**：Vector 的 vVIRTUALtarget / CANoe 是闭源的商业生态，SIL Kit 是开放标准；拥有自己的 SIL Kit 集成层意味着 yuleOSH 可独立演进
- **低成本启用 Digital Twin**：无需购买昂贵的 HIL 台架，即可在 CI Pipeline 中运行 ECU 仿真
- **加速"车辆级虚拟化验证"**：结合 yuleOSH 的 Pipeline 编排能力，可以实现"代码提交 → 固件编译 → SIL 仿真 → 回归报告"全自动化

---

## 集成架构

```
┌──────────────────────────────────────────────────────────┐
│                    yuleOSH Pipeline                        │
│  [Build] → [Flash] → [Test] → [SIL Step] → [Report]     │
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────┐
│                  SIL Kit Adapter Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ TestCase     │→ │ Simulation   │→ │ Result         │  │
│  │ Converter    │  │ Orchestrator │  │ Report Builder │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────┐
│               SIL Kit Runtime Environment                 │
│                                                           │
│  ┌──────────────┐  ┌─────────────────────────────────┐  │
│  │ SIL Kit      │  │  Participant A (ECU #1)         │  │
│  │ Manager      │  │  └─ Virtual CPU + CAN signals   │  │
│  │ (Simulation  │  │                                  │  │
│  │  Lifecycle)  │  │  Participant B (ECU #2)         │  │
│  │              │  │  └─ Virtual CANopen / LIN bus   │  │
│  └──────────────┘  │                                  │
│                     │  Participant C (Diagnostics)    │  │
│                     │  └─ UDS / DoIP virtual server   │  │
│                     └─────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 分层职责

1. **yuleOSH Pipeline 层** — 编排 CI/CD 流程，在固件编译后插入 SIL 仿真 Step，收集报告
2. **SIL Kit Adapter 层** — 将 yuleOSH 的测试用例转换为 SIL Kit 可理解的配置，启动仿真，解析原始结果，生成结构化报告
3. **SIL Kit Runtime 层** — 实际运行 SIL Kit Manager + Participant 集群，执行仿真

---

## 集成方案

### 方案一：嵌入型（首选）

yuleOSH 直接启动 SIL Kit Manager 进程，在 Pipeline Step 中创建 Participant 并驱动仿真。

```
Pipeline Step 调用:
  1. sil_adapter.start_manager()
  2. participants = sil_adapter.create_participants(config)
  3. sil_adapter.run_test_scenario(scenario)
  4. report = sil_adapter.collect_results(participants)
  5. sil_adapter.stop_manager()
```

**优点**：架构简洁，无额外中间件，延迟最低  
**缺点**：SIL Kit 进程与 Pipeline Worker 生命周期耦合

### 方案二：代理型（高可用）

yuleOSH 通过 gRPC 代理连接到一个长期运行的 SIL Kit Manager。

```
Pipeline Step 调用:
  1. grpc_client.connect(registry_uri)   # 连接到远端 SIL Kit Registry
  2. participant = grpc_client.spawn_participant("ECU_01", firmware.elf)
  3. grpc_client.run_simulation(timeout=30)
  4. report = grpc_client.fetch_results()
```

**优点**：Manager 可与 Pipeline Worker 解耦，支持大集群并发仿真  
**缺点**：增加 gRPC 代理维护成本

### 方案三：混合型（推荐终点状态）

短期使用嵌入型快速集成，中期迁移到代理型。

---

## 实施步骤

### Step 1: 下载/编译 SIL Kit

```bash
# 克隆仓库
git clone https://github.com/vectorgrp/sil-kit.git
cd sil-kit

# C++ 编译（需要 CMake ≥ 3.16）
mkdir build && cd build
cmake .. -DSILKIT_ENABLE_DEFAULT_PLUGINS=ON
cmake --build . --parallel $(nproc)
```

封装为 `sil-kit-bootstrap.sh` 脚本，由 yuleOSH 的构建系统统一管理。

### Step 2: 创建 yuleOSH SIL Kit Participant

在 `src/sil/adapter.py` 中封装 Participant 创建逻辑：

- `SILKitAdapter.create_participant(name: str, simulation_name: str)`
  - 通过 SIL Kit C API 创建 Participant
  - 注册 CAN/LIN/DoIP 虚拟信号
  - 返回 Participant 句柄

### Step 3: Pipeline Step — 运行 SIL 仿真

在 yuleOSH Pipeline 中插入 `Step 5.5: SIL 仿真验证`：

1. 检查固件 .elf / .hex 已编译
2. 启动 SIL Kit Manager（或连接已有 Registry）
3. 为每个目标 ECU 创建 Participant
4. 上载固件到虚拟 ECU
5. 驱动仿真运行（心跳 / 输入信号）
6. 超时或用户中断时自动清理

### Step 4: 收集仿真报告

SIL Kit 原生的 `ILifecycleService` 和 `ISystemMonitor` 可以返回：

- 各 Participant 运行状态（stopped / paused / running）
- 仿真的实时性指标（simulation time vs real time）
- 信号轨迹（CAN/LIN message log）
- 错误/故障注入结果

yuleOSH Adapter 将这些结构化数据转换为 Pipeline 报告格式。

---

## 数据流

```
yuleOSH Pipeline
    │
    │  pipeline_context["test_cases"]
    ▼
SILKitAdapter.convert_testcases()
    │
    │  SilTestConfig (list of simulation scenarios)
    ▼
SILKitAdapter.start_simulation(config)
    │
    │  SIL Kit Manager started
    │  Participant(s) created with firmware loaded
    │  Simulation life cycle started
    ▼
SILKitAdapter.wait_for_results(timeout)
    │
    │  Raw bytes / protobuf messages from SIL Kit
    ▼
SILKitAdapter.parse_results(raw)
    │
    │  SimReport (structured dict)
    ▼
SILKitAdapter.generate_report(results)
    │
    │  Final pipeline report dict
    ▼
yuleOSH Report Aggregator
```

---

## 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| SIL Kit Manager 启动失败 | 重试 3 次，每次等待 2s；失败则标记 Step 为 SKIPPED，输出 Manager 日志供诊断 |
| Participant 注册超时 | 断开当前仿真，尝试重新注册；超时上限 10s |
| 仿真运行超时 | 触发 graceful stop，收集已有的部分结果 |
| Participant 崩溃 | 自动重启 Participant，注入致命错误日志到报告 |
| 信号数据不一致 | 丢弃异常帧，在报告中标记警告 |

---

## 安全注意事项

- SIL Kit 本身不提供进程隔离沙箱；多 Participant 在同一进程空间可能有安全隐患
- 生产环境建议使用 Docker 容器隔离每个 Participant
- Manager 的 `Registry URI` 不应暴露到公网，建议绑定 localhost 或容器内虚拟网络
