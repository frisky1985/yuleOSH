# A66-T Fault Injection — 学习笔记（v4）

**来源 1：** A66-T_fault_inject_test_runner.py — 测试执行器（Python）
**来源 2：** A66-T_HardFault_Exception_Injection_Scheme.md — 完整设计方案
**来源 3：** FaultInject.zip — 系统级故障注入 C 源码（3 文件）
**来源 4：** 归档.zip — 任务级故障注入 C 源码（TaskFaultInject + 集成指南）

---

## 核心架构：两层故障注入

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 2: TaskFaultInject（任务级·模拟注入）                          │
│                                                                     │
│  UDS DID: 0xF193                通道: FreeRTOS Task Notification    │
│  故障类型: NULL句柄 / 无效参数 / 超时 / 队列满 / 缓存溢出 / ...      │
│  效果: 不会复位！2秒/测试, 32个测试~64秒                            │
│  验证: 被测任务的错误处理路径是否被正确执行                            │
│  编译开关: A66T_TASK_FAULT_INJECT_ENABLE                            │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: FaultInject（系统级·真实CPU异常注入）                       │
│                                                                     │
│  UDS DID: 0xF190                通道: CAN UDS $2E/$22              │
│  故障类型: NullPointer / DivByZero / Unaligned / BusAccess / ...   │
│  效果: 触发硬故障 → ECU复位 → 15-30秒/测试                           │
│  验证: faultType+CFSR掩码+PC+Magic 完整性                           │
│  编译开关: A66T_FAULT_INJECTION_TEST_ENABLE                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: FaultInject（系统级·CPU异常注入）

### 关键文件
| 文件 | 行数 | 内容 |
|:-----|:-----|:-----|
| FaultInject_Cfg.h | ~80 | 编译开关 + 9个测试用例独立开关 + UDS DID 0xF190 |
| FaultInject.h | ~120 | API: Init/Run/CheckResult/GetResult/GetTestName + 生产环境 inline no-op |
| FaultInject.c | ~350 | 9种注入实现 + ECC保护(EIRU_CR) + 复位后验证 |

### 核心流程
```
FaultInject_Run(type)
  ├── 保存测试元数据到 NoInit RAM (.share_ram @ 0x1FFE0000)
  │   └── magic=0xF175F175, testId, status=PENDING
  ├── 禁用 ECC 响应 (EIRU_CR=0x0F) — 防递归故障
  ├── 使能 SHCSR 故障 handler
  └── 执行注入（不返回！）→ CPU异常 → handler保存记录 → Mcu_PerformReset()

复位后 → FaultInject_CheckResult()
  ├── 检查 magic == 0xF175F175
  ├── 检查 NoInit FaultRecord.magic == 0xFA017FA0
  └── 验证 faultType ∈ [1-5]

Python Test Runner 远程验证:
  CAN $2E F190 → 等待复位 → CAN $22 F191 读故障记录 → faultType+CFSR+PC 完整验证
```

### 安全机制
- **ECC 保护**：访问 SRAM0 前关 EIRU_CR（0x4000B000 |= 0x0F），防止递归 BusFault
- **STD_OFF → inline no-op**：生产环境全空函数，linker 会优化移除
- **SecurityAccess ($27)**：CAN 远程注入需通过安全认证
- **个体编译开关**：9 个测试可独立开关（MPU测试默认 STD_OFF）

---

## Layer 2: TaskFaultInject（任务级·模拟故障注入）

### 关键文件
| 文件 | 行数 | 内容 |
|:-----|:-----|:-----|
| TaskFaultInject_Cfg.h | ~60 | 编译开关 + 7个模拟故障开关 + 结果缓冲区大小(16) + 超时(5s) + UDS DID 0xF193 |
| TaskFaultInject.h | ~330 | API: Init/RegisterTask/Inject + 任务侧宏 |
| TaskFaultInject.c | ~350 | FreeRTOS Task Notification 实现 |

### 与 Layer 1 的本质区别
| 维度 | Layer 1 系统级 | Layer 2 任务级 |
|:-----|:---------------|:---------------|
| 故障本质 | 真实 CPU 异常 | 模拟错误条件 |
| 注入机制 | 执行错误代码 | FreeRTOS Task Notification（32-bit） |
| 系统影响 | ECU 复位 | 完全不影响 |
| 测试时间 | 15-30s/测试 | ~2s/测试 |
| 验证重点 | FaultHandler 保存+恢复 | 错误处理路径是否正确执行 |
| 适用阶段 | HIL/CAT-1~4 | 开发期/CI/回归 |
| 8任务×4故障 | ~10分钟 | ~64秒 |

### 集成模式
```c
// 1. 注册任务 (一次性)
TaskFault_RegisterTask(xTaskGetCurrentTaskHandle(), "RteHigh");

// 2. 循环检查 (每个 loop 开头 + 结尾)
for (;;) {
    TASK_FAULT_CHECK();   // 收 FreeRTOS Notification → 设置故障标志
    
    // 3. 业务逻辑中植入故障感知分支
    void *handle = GetHandle();
    if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_NULL_HANDLE)) {
        handle = NULL;  // 强制模拟 NULL 句柄
    }
    if (NULL == handle) {
        TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);  // 错误路径走对了
        return;
    }
    
    TASK_FAULT_END_CHECK();  // 未报告 → 自动 FAILED
}
```

### 7 种模拟故障类型
| # | 类型 | 模拟场景 |
|:-:|:-----|:---------|
| 0x01 | SIM_NULL_HANDLE | 关键句柄为 NULL |
| 0x02 | SIM_INVALID_PARAM | 参数越界/无效 |
| 0x03 | SIM_TIMEOUT | 超时/错过截止时间 |
| 0x04 | SIM_QUEUE_FULL | 消息队列已满 |
| 0x05 | SIM_BUFFER_OVF | 缓冲区溢出 |
| 0x06 | SIM_RESOURCE_LOST | 外设丢失 |
| 0x07 | SIM_STATE_CORRUPT | 状态机损坏 |
| 0x10 | REAL_STACK_DEPLETE | 真正的栈消耗（危险！默认 OFF） |

### 远程触发 (UDS)
```
CAN $2E F193 {faultType(uint32), taskIndex(uint32)}
→ TaskFault_Inject(targetTask, faultType) → FreeRTOS Notification
→ 目标任务下一个循环收到通知 → 模拟故障 → 报结果
→ CAN $22 F192 读结果
```

---

## 对 yuleOSH Pipeline 的启示（更新）

### 必须支持两层注入

yuleOSH 的 Fault Injection Pipeline Stage 必须设计两层：

```
yuleOSH Pipeline Fault Injection Stage
  │
  ├── Layer 1: hardware_injection（系统级，全复位）
  │   ├── 目标: CAN/UDS / DoIP / JTAG
  │   ├── 用例: 类似 A66-T 的 9 种 CPU 异常注入
  │   ├── 耗时: 15-30s/测试
  │   └── 验证: faultType+CFSR+PC+Magic
  │
  └── Layer 2: task_injection（任务级，不停机）
      ├── 目标: 通过调试接口/UDS注入模拟错误
      ├── 用例: NULL处理/参数越界/超时/队列满/缓存溢出
      ├── 耗时: ~2s/测试
      └── 验证: 错误处理路径是否正确执行
```

### TaskFaultInject 的设计模式值得 yuleOSH 吸收

1. **FreeRTOS Task Notification 作为注入通道** — 最快最低开销的 IPC
2. **每任务独立注册** — 非全局，可精确控制调度
3. **TASK_FAULT_CHECK() + TASK_FAULT_END_CHECK() 包围循环** — 生命周期管理
4. **环形结果缓冲区** — 16 条记录，不丢失不溢出
5. **业务代码 0 侵入** — 唯一改动是在错误处理分支加 `TASK_FAULT_REPORT()`
6. **宏全变 no-op** — `STD_OFF` 时代码全部消失

### yuleOSH 的 "TaskFaultInject" 应该怎么做
- 提供 embeddable C 头文件（类似 A66-T 的 TaskFaultInject.h）
- 用户只需在任务循环加两行宏 + 错误路径加一行宏
- Pipeline 通过调试口/JTAG 触发任务级注入
- 无需复位，适合作为 CI 日常关卡
