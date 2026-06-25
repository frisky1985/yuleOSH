# yuleOSH Fault Injection Pipeline — 技术方案

> **版本：** v1.0
> **日期：** 2026-06-20
> **状态：** 草案，待小马审查
> **来源：** A66-T HardFault Exception Injection Automated Test Runner（Cortex-M4F / CAN UDS / FreeRTOS）

---

## 目录

1. [设计原则](#1-设计原则)
2. [总体架构](#2-总体架构)
3. [Part 1: 通信层抽象（接口设计）](#3-part-1-通信层抽象接口设计)
4. [Part 2: Pipeline Stage 定义](#4-part-2-pipeline-stage-定义)
5. [Part 3: 测试用例定义格式（YAML Schema）](#5-part-3-测试用例定义格式yaml-schema)
6. [Part 4: 数据模型](#6-part-4-数据模型)
7. [Part 5: CI 模块集成](#7-part-5-ci-模块集成)
8. [Part 6: 实施路线](#8-part-6-实施路线)
9. [与已有模块集成](#9-与已有模块集成)
10. [附录：A66-T 测试用例到 Schema 映射](#10-附录a66-t-测试用例到-schema-映射)
11. [附录：目录修订历史](#11-附录目录修订历史)
12. [§13 任务级故障注入（Layer 2）](#13-任务级故障注入layer-2)
    - [13.1 设计目标](#131-设计目标)
    - [13.2 架构设计](#132-架构设计)
    - [13.3 API 设计（C Header 供嵌入）](#133-api-设计c-header-供嵌入)
    - [13.4 通信层适配](#134-通信层适配)
    - [13.5 与现有 Pipeline 的集成](#135-与现有-pipeline-的集成)
    - [13.6 YAML 用例集扩展](#136-yaml-用例集扩展)
    - [13.7 数据模型扩展](#137-数据模型扩展)
    - [13.8 实施路线追加](#138-实施路线追加)

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **通信层即插即用** | CAN/UDS、DoIP、JTAG、模拟器四种 target 接口一致，切换只需改配置 |
| **注入验证解耦** | 每个 test case 是 `(inject_spec, verify_spec)` 元组，可独立扩展注入方法和验证策略 |
| **Pipeline 一等公民** | `fault_injection` 是 yuleOSH pipeline 的原生 stage，与 `build`/`unit_test`/`integration_test` 同级 |
| **结果可追溯** | 每次注入结果写入 evidence 模块，支持 FMEA/LL 双向追溯 |
| **Fail-fast + 幂等** | 注入失败可重跑，cooldown/超时机制避免总线锁死 |
| **与被测目标解耦** | 不假设 MCU 架构、RTOS、总线类型，由 target 实现层封装差异 |

---

## 2. 总体架构

### 2.1 架构概览

```
yuleOSH Pipeline
┌─────────────────────────────────────────────────────────────┐
│  ┌──────┐  ┌──────────┐  ┌────────────────┐  ┌───────────┐ │
│  │build │→ │unit_test │→ │ fault_injection│→ │integration│ │
│  └──────┘  └──────────┘  └───────┬────────┘  └───────────┘ │
└──────────────────────────────────┼──────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
         ┌──────────────────┐          ┌──────────────────┐
         │  FI Engine       │          │  FI CLI / CI      │
         │  (core loop)     │          │  (yule ci fi ...) │
         └────────┬─────────┘          └──────────────────┘
                  │
     ┌────────────┼────────────┬────────────────┐
     ▼            ▼            ▼                ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐
│CAN/UDS   │ │ DoIP     │ │ JTAG/SWD │ │ Simulator        │
│Target    │ │ Target   │ │ Target   │ │ Target           │
│(socketcan│ │ (ethernet)│ │ (openocd)│ │ (Unicorn/QEMU)   │
│ /vector) │ │          │ │          │ │                  │
└──────────┘ └──────────┘ └──────────┘ └──────────────────┘
                  │
                  ▼
        ┌──────────────────┐
        │ Evidence Module  │
        │ (结果 → 追溯矩阵) │
        └──────────────────┘
```

### 2.2 核心流程

```
┌────────────────────────────────────────────────────────────┐
│                    FI Engine Loop                           │
│                                                             │
│  For each test_case in cases:                               │
│    │                                                         │
│    ├─ [Init Phase]                                          │
│    │   └─ target.Connect()                                  │
│    │                                                         │
│    ├─ [Inject Phase]                                        │
│    │   ├─ target.SendInject(test_case.inject)               │
│    │   └─ 记录注入时间戳                                      │
│    │                                                         │
│    ├─ [Wait Phase]                                          │
│    │   ├─ target.WaitForTarget(timeout)                     │
│    │   ├─ cooldown_sleep(config.cooldown_s)                 │
│    │   └─ 记录恢复时间/复位次数                                │
│    │                                                         │
│    ├─ [Verify Phase]                                        │
│    │   ├─ record = target.ReadFaultRecord()                 │
│    │   ├─ result = verify(record, test_case.verify)         │
│    │   └─ 记录 verify 详情                                   │
│    │                                                         │
│    ├─ [Report Phase]                                        │
│    │   ├─ 写入 InjectResult                                 │
│    │   ├─ 推送到 evidence 模块                               │
│    │   └─ 累计 fail_count                                    │
│    │                                                         │
│    └─ [Throttle & Bypass]                                   │
│        ├─ test_case.skip_if 评估 → 跳过                      │
│        ├─ max_failures 检测 → 提前终止                        │
│        └─ cooldown 间隔                                      │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Part 1: 通信层抽象（接口设计）

### 3.1 核心接口

```go
// pkg/fault-inject/target/target.go

// FaultInjectTarget 定义与目标系统的通信契约。
// 每个实现封装一个具体的通信协议 + 硬件接口。
//
// 生命周期:
//   Connect → (SendInject | ReadFaultRecord)* → Disconnect
//
// 并发安全:
//   不同的 test case 不在同一个 Connect 生命周期内交叉执行，
//   但实现层应支持多次 SendInject+WaitForTarget+ReadFaultRecord 循环。
type FaultInjectTarget interface {
    // Connect 建立与目标系统的通信链路。
    // - CAN/UDS: 打开 socket/binding
    // - DoIP: TCP 连接 + 路由激活
    // - JTAG: openocd/telnet 连接
    // - Simulator: 启动/挂载模拟器实例
    Connect(ctx context.Context) error

    // SendInject 向目标发送注入命令。
    // cfg 包含注入方法（DID 写 / 寄存器写 / 内存篡改）和数据载荷。
    // 实现层负责将通用 InjectConfig 翻译为协议帧。
    SendInject(ctx context.Context, cfg InjectConfig) error

    // WaitForTarget 等待目标复位后重新上线。
    // 返回 true 表示在 timeout 内检测到目标上线。
    // - CAN/UDS: 周期性发送 TesterPresent 直到收到响应
    // - DoIP: 周期性发送 DoIP vehicle announcement request
    // - JTAG: 轮询调试寄存器检测 CPU halt 恢复
    // - Simulator: 检测模拟器重启完成
    WaitForTarget(ctx context.Context, timeout time.Duration) bool

    // ReadFaultRecord 从目标读取故障记录。
    // 返回结构化的 FaultRecord，包含 faultType/PC/CFSR/HFSR 等。
    ReadFaultRecord(ctx context.Context) (*FaultRecord, error)

    // Disconnect 断开与目标的通信，释放资源。
    Disconnect(ctx context.Context) error
}
```

### 3.2 内置实现

#### 3.2.1 CAN/UDS Target — `can_uds_target`

继承 A66-T 的 CAN + UDS（ISO 14229）通信模式。

```go
type CANUDSTargetConfig struct {
    Interface      string `yaml:"interface"`       // "socketcan" | "vector"
    Channel        string `yaml:"channel"`          // "vcan0" | "can0"
    Bitrate        int    `yaml:"bitrate"`          // 500000
    CanFD          bool   `yaml:"can_fd"`
    UDSTxID        uint32 `yaml:"uds_tx_id"`        // 0x7E0 (物理寻址)
    UDSRxID        uint32 `yaml:"uds_rx_id"`        // 0x7E8
    TesterPresentIntervalMs int `yaml:"tp_interval_ms"` // 500ms
}

type canUDSClient struct {
    cfg        CANUDSTargetConfig
    conn       SocketcanConn  // 或 vector.Channel
    udsClient  *UDSClient     // DID $2E/$22 封装
    ecuOnline  bool
}

// SendInject: UDS $2E ({did}, {data})
func (c *canUDSClient) SendInject(ctx context.Context, cfg InjectConfig) error {
    req := &UDSRequest{
        Service: UDS_SERVICE_WRITE_BY_ID,  // $2E
        DID:     cfg.MethodDID,
        Data:    cfg.Payload,
    }
    resp, err := c.udsClient.Execute(ctx, req)
    if err != nil {
        return fmt.Errorf("udssrv $2E: %w", err)
    }
    if resp.Code != UDS_RC_POSITIVE {
        return fmt.Errorf("udssrv $2E nack 0x%02X", resp.Code)
    }
    return nil
}

// WaitForTarget: TesterPresent 轮询
func (c *canUDSClient) WaitForTarget(ctx context.Context, timeout time.Duration) bool {
    deadline := time.Now().Add(timeout)
    for time.Now().Before(deadline) {
        select {
        case <-ctx.Done():
            return false
        default:
            if c.pingUDS(ctx) {
                c.ecuOnline = true
                return true
            }
            time.Sleep(100 * time.Millisecond)
        }
    }
    return false
}

// ReadFaultRecord: UDS $22 ({did})
func (c *canUDSClient) ReadFaultRecord(ctx context.Context) (*FaultRecord, error) {
    req := &UDSRequest{
        Service: UDS_SERVICE_READ_BY_ID,  // $22
        DID:     DefaultFaultRecordDID,
    }
    resp, err := c.udsClient.Execute(ctx, req)
    if err != nil {
        return nil, err
    }
    return ParseFaultRecordBytes(resp.Data), nil
}

func ParseFaultRecordBytes(data []byte) *FaultRecord {
    return &FaultRecord{
        Magic:     binary.LittleEndian.Uint32(data[0:4]),
        FaultType: data[4],
        PC:        binary.LittleEndian.Uint32(data[5:9]),
        CFSR:      binary.LittleEndian.Uint32(data[9:13]),
        HFSR:      binary.LittleEndian.Uint32(data[13:17]),
    }
}
```

#### 3.2.2 DoIP Target — `doip_target`

针对以太网 + DoIP（ISO 13400）的现代汽车架构。

```go
type DoIPTargetConfig struct {
    Address       string `yaml:"address"`        // "192.168.1.100"
    Port          int    `yaml:"port"`            // 13400
    LogicalAddr   uint16 `yaml:"logical_address"` // 0x0E80
    SourceAddr    uint16 `yaml:"source_address"`  // 0x0E00
    UDSTxID       uint32 `yaml:"uds_tx_id"`       // 0xDA
    UDSRxID       uint32 `yaml:"uds_rx_id"`       // 0xDB
}

type doipClient struct {
    cfg        DoIPTargetConfig
    tcpConn    net.Conn
    udsClient  *UDSClient  // 复用在 DoIP 隧道上的 UDS
}
```

#### 3.2.3 JTAG/SWD Target — `jtag_target`

通过调试接口直接注入故障（OpenOCD / JLink / pyOCD）。

```go
type JTAGTargetConfig struct {
    Adapter     string `yaml:"adapter"`      // "openocd" | "jlink" | "pyocd"
    Interface   string `yaml:"interface"`    // "ftdi" | "jtag" | "swd"
    ConfigFile  string `yaml:"config_file"`  // openocd cfg file
    TclPort     int    `yaml:"tcl_port"`     // 6666
    TelnetPort  int    `yaml:"telnet_port"`  // 4444
    GdbPort     int    `yaml:"gdb_port"`     // 3333
    CpuArch     string `yaml:"cpu_arch"`     // "cortex-m4"

    // JTAG 注入策略
    InjectMethod string `yaml:"inject_method"` // "register_tamper" | "memory_write" | "breakpoint_set"
}

// SendInject: 通过 GDB/OpenOCD 命令直接写寄存器或内存
func (c *jtagClient) SendInject(ctx context.Context, cfg InjectConfig) error {
    switch c.cfg.InjectMethod {
    case "register_tamper":
        // 写 PC / LR / SP 等寄存器
        return c.gdb.WriteRegister(cfg.RegisterName, cfg.RegisterValue)
    case "memory_write":
        // 直接篡改内存地址
        return c.gdb.WriteMemory(cfg.MemoryAddr, cfg.Payload)
    case "breakpoint_set":
        return c.gdb.SetBreakpoint(cfg.BreakpointAddr)
    default:
        return fmt.Errorf("unknown JTAG inject method: %s", c.cfg.InjectMethod)
    }
}
```

#### 3.2.4 Simulator Target — `simulator_target`

基于模拟器（Unicorn / QEMU）的纯软件注入。

```go
type SimulatorTargetConfig struct {
    Engine     string `yaml:"engine"`         // "unicorn" | "qemu"
    Firmware   string `yaml:"firmware"`       // .elf 或 .bin 路径
    CpuModel   string `yaml:"cpu_model"`      // "cortex-m4"
    RamSize    int    `yaml:"ram_size"`       // 0x10000
    RomAddr    uint32 `yaml:"rom_addr"`       // 0x08000000
    RamAddr    uint32 `yaml:"ram_addr"`       // 0x20000000
}

// SendInject: 在模拟器执行前注册 hook，模拟故障
func (c *simulatorClient) SendInject(ctx context.Context, cfg InjectConfig) error {
    switch cfg.Method {
    case "memory_overwrite":
        // 在 firmware load 后篡改指定地址
        return c.unicorn.MemWrite(cfg.MemoryAddr, cfg.Payload)
    case "register_corrupt":
        return c.unicorn.RegWrite(cfg.RegisterName, cfg.RegisterValue)
    case "fault_hook":
        // 注册 UC_HOOK_CODE，在特定 PC 触发故障
        return c.unicorn.HookAdd(cfg.BreakpointAddr, func(uc *unicorn.Unicorn) {
            // 模拟 HardFault 入口
            uc.RegWrite(unicorn.ARM_REG_PC, HardFaultVectorAddr)
        })
    default:
        return fmt.Errorf("unknown simulator inject method: %s", cfg.Method)
    }
}

// WaitForTarget: 模拟器没有复位等待概念，等价于重启模拟器
func (c *simulatorClient) WaitForTarget(ctx context.Context, timeout time.Duration) bool {
    // 重启模拟器实例
    muc, err := c.restartSimulator()
    if err != nil {
        return false
    }
    c.unicorn = muc
    return true
}
```

### 3.3 注册与工厂模式

```go
// pkg/fault-inject/target/registry.go

type TargetFactory func(config json.RawMessage) (FaultInjectTarget, error)

var targetRegistry = map[string]TargetFactory{
    "can_uds":     NewCANUDSTarget,
    "doip":        NewDoIPTarget,
    "jtag":        NewJTAGTarget,
    "simulator":   NewSimulatorTarget,
}

// RegisterTarget 允许外部模块注册自定义 target（如用户自定义的 UART 注入器）
func RegisterTarget(name string, factory TargetFactory) {
    targetRegistry[name] = factory
}

func NewTarget(typeName string, config json.RawMessage) (FaultInjectTarget, error) {
    factory, ok := targetRegistry[typeName]
    if !ok {
        return nil, fmt.Errorf("unknown target type: %s", typeName)
    }
    return factory(config)
}
```

---

## 4. Part 2: Pipeline Stage 定义

### 4.1 Pipeline 配置

```yaml
# pipeline.yml — fault_injection stage 完整配置

stages:
  - id: build
    config:
      target: "fw.elf"

  - id: unit_test
    config:
      suites: ["tests/unit/..."]

  - id: fault_injection
    config:
      # ——— 目标选择 ———
      target:
        type: can_uds
        interface: socketcan
        channel: vcan0
        bitrate: 500000
        uds_tx_id: 0x7E0
        uds_rx_id: 0x7E8

      # ——— 测试用例 ———
      test_cases:
        - "fi/cases/a66-t/basic.yaml"
        - "fi/cases/a66-t/mpu.yaml"

      # ——— 运行时参数 ———
      max_failures:       1       # 超过此数则整个 stage fail
      cooldown_s:         3.0     # 测试间冷却时间
      inject_timeout_s:   15.0    # ECU 复位后等待超时
      verify_timeout_s:   10.0    # 读取故障记录超时
      retry_on_fail:      0       # 失败重试次数

      # ——— 报告与集成 ———
      report_path:        "reports/fault-injection.json"
      evidence_push:      true    # 自动推送到 evidence 模块
      fail_on_uncovered:  false   # 是否因未覆盖的 FMEA 条目而失败

    depends_on:
      - unit_test   # fault_injection 在 unit_test 之后执行

  - id: integration_test
```

### 4.2 Pipeline Stage Go 骨架

```go
// internal/pipeline/fault_injection/stage.go

type FaultInjectionStage struct {
    engine    *fiengine.Engine
    reporter  *fireporter.Reporter
    config    StageConfig
}

type StageConfig struct {
    Target              TargetConfig      `yaml:"target"`
    TestCasePaths       []string          `yaml:"test_cases"`
    MaxFailures         int               `yaml:"max_failures"`
    CooldownSeconds     float64           `yaml:"cooldown_s"`
    InjectTimeoutSeconds float64          `yaml:"inject_timeout_s"`
    VerifyTimeoutSeconds float64          `yaml:"verify_timeout_s"`
    RetryOnFail         int               `yaml:"retry_on_fail"`
    ReportPath          string            `yaml:"report_path"`
    EvidencePush        bool              `yaml:"evidence_push"`
    FailOnUncovered     bool              `yaml:"fail_on_uncovered"`
}

func (s *FaultInjectionStage) Name() string {
    return "fault_injection"
}

func (s *FaultInjectionStage) Run(ctx *pipeline.Context) error {
    ctx.Log.Info("fault_injection stage started")

    // 1. 加载所有测试用例
    cases, err := fiengine.LoadTestCases(s.config.TestCasePaths...)
    if err != nil {
        return fmt.Errorf("load test cases: %w", err)
    }
    ctx.Log.Info("loaded test cases", zap.Int("count", len(cases)))

    // 2. 运行故障注入引擎
    results, err := s.engine.Run(ctx.Context, &fiengine.RunConfig{
        Cases:               cases,
        MaxFailures:         s.config.MaxFailures,
        CooldownDuration:    time.Duration(s.config.CooldownSeconds * float64(time.Second)),
        InjectTimeout:       time.Duration(s.config.InjectTimeoutSeconds * float64(time.Second)),
        VerifyTimeout:       time.Duration(s.config.VerifyTimeoutSeconds * float64(time.Second)),
        RetryOnFail:         s.config.RetryOnFail,
    })
    if err != nil {
        return fmt.Errorf("fault injection run: %w", err)
    }

    // 3. 生成报告
    if err := s.reporter.Save(results, s.config.ReportPath); err != nil {
        return fmt.Errorf("save report: %w", err)
    }

    // 4. 推送证据
    if s.config.EvidencePush {
        if err := s.pushEvidence(ctx, results); err != nil {
            ctx.Log.Warn("push evidence failed", zap.Error(err))
        }
    }

    // 5. 检查覆盖率（可选）
    if s.config.FailOnUncovered {
        if err := s.checkUncovered(ctx, results); err != nil {
            return fmt.Errorf("uncovered fmea items: %w", err)
        }
    }

    ctx.Log.Info("fault_injection stage completed",
        zap.Int("total", len(results)),
        zap.Int("passed", countPassed(results)),
        zap.Int("failed", countFailed(results)),
        zap.Int("skipped", countSkipped(results)),
    )
    return nil
}
```

### 4.3 FI Engine 核心

```go
// pkg/fault-inject/engine/engine.go

type Engine struct {
    targetFactory target.TargetFactory
}

type RunConfig struct {
    Cases              []TestCase
    MaxFailures        int
    CooldownDuration   time.Duration
    InjectTimeout      time.Duration
    VerifyTimeout      time.Duration
    RetryOnFail        int
}

func (e *Engine) Run(ctx context.Context, cfg *RunConfig) ([]TestCaseResult, error) {
    target, err := e.createTarget(cfg.Cases[0].TargetType)
    if err != nil {
        return nil, fmt.Errorf("create target: %w", err)
    }

    if err := target.Connect(ctx); err != nil {
        return nil, fmt.Errorf("connect target: %w", err)
    }
    defer target.Disconnect(ctx)

    var results []TestCaseResult
    failures := 0

    for _, tc := range cfg.Cases {
        // SKIP 评估
        if shouldSkip(tc) {
            results = append(results, TestCaseResult{
                TestCaseID: tc.ID,
                Status:     StatusSkipped,
                Reason:     tc.SkipReason,
            })
            continue
        }

        // 最大失败数检测
        if failures >= cfg.MaxFailures {
            results = append(results, TestCaseResult{
                TestCaseID: tc.ID,
                Status:     StatusBlocked,
                Reason:     fmt.Sprintf("max_failures (%d) reached", cfg.MaxFailures),
            })
            continue
        }

        // 执行单用例
        result := e.runSingle(ctx, target, tc, cfg)
        if result.Status == StatusFail {
            failures++
        }
        results = append(results, result)

        // Cooldown
        time.Sleep(cfg.CooldownDuration)
    }

    return results, nil
}

func (e *Engine) runSingle(ctx context.Context, target target.FaultInjectTarget,
    tc TestCase, cfg *RunConfig) TestCaseResult {

    result := TestCaseResult{
        TestCaseID: tc.ID,
        Name:       tc.Name,
        Status:     StatusFail,
    }

    // 1. 注入
    injectStart := time.Now()
    if err := target.SendInject(ctx, tc.Inject); err != nil {
        result.Error = fmt.Sprintf("inject failed: %v", err)
        return result
    }
    result.InjectDuration = time.Since(injectStart)

    // 2. 等待复位 + 上线
    waitStart := time.Now()
    online := target.WaitForTarget(ctx, cfg.InjectTimeout)
    if !online {
        result.Error = fmt.Sprintf("target not online after %v", cfg.InjectTimeout)
        return result
    }
    result.WaitDuration = time.Since(waitStart)

    // 3. 读取故障记录
    record, err := target.ReadFaultRecord(ctx)
    if err != nil {
        result.Error = fmt.Sprintf("read fault record failed: %v", err)
        return result
    }
    result.FaultRecord = record

    // 4. 验证
    result.Verifications = verifyTestCase(tc, record)

    // 5. 总体判定
    allPassed := true
    for _, v := range result.Verifications {
        if !v.Passed {
            allPassed = false
            break
        }
    }
    if allPassed {
        result.Status = StatusPass
    }

    return result
}
```

---

## 5. Part 3: 测试用例定义格式（YAML Schema）

### 5.1 完整 Schema

```yaml
# yuleOSH Fault Injection — Test Case YAML Schema
# Schema 版本: v1.0
#
# 一个 YAML 文件可以包含多个同类 target 的测试用例。
# 文件组织建议：fi/cases/{project-name}/{feature}.yaml

# ——— 全局元数据（可选） ———
meta:
  schema_version: "1.0"
  project: "yuleosh/ecu-fw"
  target_type: can_uds        # 默认 target 类型，case 可覆盖
  author: "stefan"
  created: "2026-06-20"
  source: "A66-T automated test runner"

# ——— 测试用例列表 ———
test_cases:
  # ── Case 1: 空指针解引用 ──
  - id: "FI-NULLPTR-001"
    name: "NullPointer — dereference null pointer"
    description: >
      Write an all-zero pointer to a function call site,
      causing the CPU to attempt instruction fetch from address 0x00000000.
      Expected: BusFault (CFSR PRECISERR | IBUSERR).
    target_type: can_uds       # 可覆盖全局 target_type

    # ——— 注入定义 ———
    inject:
      method: did_write        # UDS DID 写注入
      did: 0xF190              # A66-T 约定的注入 DID
      payload: [0x01]          # test case ID 编码

    # ——— 验证定义 ———
    verify:
      check_magic: true        # 验证 faultRecord.magic == 0xFA017FA0
      expected_fault_types: [1, 3]  # HardFault, BusFault
      cfsr_check:
        mask: 0x00000600       # 检查的 CFSR 位
        logic: "nonzero"       # nonzero | zero | exact
      hfsr_check: {}           # 可选 HFSR 检查

    # ——— 运行时控制 ———
    timeout_s: 15.0
    cooldown_s: 3.0
    retry_count: 0
    skip_if: ""                # 条件跳过（JQ-like 表达式）

  # ── Case 2: 除零 ──
  - id: "FI-DIVBYZERO-001"
    name: "DivideByZero"
    inject:
      method: did_write
      did: 0xF190
      payload: [0x03]
    verify:
      check_magic: true
      expected_fault_types: [1, 4]  # HardFault, UsageFault
      cfsr_check:
        mask: 0x02000000       # DIVBYZERO
        logic: nonzero
    skip_if: "!div_by_zero_trap_enabled"

  # ── Case 3: JTAG 寄存器写 ──
  - id: "FI-JTAG-SP-CORRUPT-001"
    name: "StackPointer Corruption via JTAG"
    target_type: jtag
    inject:
      method: register_tamper   # JTAG 寄存器写
      register_name: "sp"      # Stack Pointer
      register_value: 0x20000000  # 篡改为无效栈指针
    verify:
      check_magic: true
      expected_fault_types: [1]    # HardFault
      cfsr_check:
        mask: 0x00000200          # STKERR
        logic: nonzero

  # ── Case 4: 模拟器内存损坏 ──
  - id: "FI-SIM-BSS-CORRUPT-001"
    name: "Global Variable Corruption in Simulator"
    target_type: simulator
    inject:
      method: memory_overwrite
      memory_addr: 0x20001000
      payload: [0xDE, 0xAD, 0xBE, 0xEF]
    verify:
      check_magic: true
      expected_fault_types: [1, 2, 3]
      cfsr_check:
        mask: 0x00000300
        logic: nonzero

  # ── Case 5: CAN 超时注入（非 A66-T 风格，新场景示例） ──
  - id: "FI-CAN-TIMEOUT-001"
    name: "CAN communication timeout → safe state"
    target_type: can_uds
    inject:
      method: bus_off           # 自定义注入方法
      bus_off_duration_s: 5.0
    verify:
      check_magic: false        # 不检查 fault record，观察行为
      behavior_check:           # 行为级验证
        safe_state_entered: true
        limp_home_active: true
```

### 5.2 Schema 字段约束

| 字段路径 | 必填 | 类型 | 约束 |
|---------|------|------|------|
| `test_cases[].id` | ✅ | string | 全局唯一，建议 `FI-{FEATURE}-{N}` |
| `test_cases[].name` | ✅ | string | 简短描述，≤80字符 |
| `test_cases[].description` | | string | 详细说明 |
| `test_cases[].target_type` | | string | 省略时继承全局 meta.target_type |
| `test_cases[].inject.method` | ✅ | string | 枚举：`did_write` / `register_tamper` / `memory_overwrite` / `bus_off` |
| `test_cases[].inject.did` | 条件 | uint16 | method=did_write 时必填 |
| `test_cases[].inject.payload` | 条件 | []byte | method=did_write 时必填 |
| `test_cases[].verify.check_magic` | | bool | 默认 true |
| `test_cases[].verify.expected_fault_types` | | []int | 1-5，参考 A66-T 类型 |
| `test_cases[].verify.cfsr_check.mask` | | uint32 | 0 表示不检查 |
| `test_cases[].verify.cfsr_check.logic` | | string | `nonzero` / `zero` / `exact` |
| `test_cases[].verify.behavior_check` | | object | 行为级验证（非故障记录验证） |
| `test_cases[].timeout_s` | | float | 默认 15.0 |
| `test_cases[].cooldown_s` | | float | 默认继承全局 cooldown_s |
| `test_cases[].skip_if` | | string | 空字符串表示永不跳过 |

### 5.3 A66-T 全部 9 个用例 YAML 版本

```yaml
# fi/cases/yuleosh/a66-t-compat.yaml
# A66-T 9 种故障注入测试用例的 yuleOSH 通用格式版本
meta:
  schema_version: "1.0"
  project: "yuleosh/ecu-fw"
  target_type: can_uds
  source: "A66-T automated test runner (Z20K148M Cortex-M4F)"

test_cases:
  - id: "FI-A66T-001"
    name: "NullPointer"
    inject:  { method: did_write, did: 0xF190, payload: [0x01] }
    verify:  { check_magic: true, expected_fault_types: [1, 3], cfsr_check: { mask: 0x00000600, logic: nonzero } }

  - id: "FI-A66T-002"
    name: "InvalidFunc"
    inject:  { method: did_write, did: 0xF190, payload: [0x02] }
    verify:  { check_magic: true, expected_fault_types: [1, 4], cfsr_check: { mask: 0x00020000, logic: nonzero } }

  - id: "FI-A66T-003"
    name: "DivByZero"
    inject:  { method: did_write, did: 0xF190, payload: [0x03] }
    verify:  { check_magic: true, expected_fault_types: [1, 4], cfsr_check: { mask: 0x02000000, logic: nonzero } }
    skip_if: "!div_by_zero_trap_enabled"

  - id: "FI-A66T-004"
    name: "Unaligned"
    inject:  { method: did_write, did: 0xF190, payload: [0x04] }
    verify:  { check_magic: true, expected_fault_types: [1, 4], cfsr_check: { mask: 0x01000000, logic: nonzero } }

  - id: "FI-A66T-005"
    name: "StackOverflow"
    inject:  { method: did_write, did: 0xF190, payload: [0x05] }
    verify:  { check_magic: true, expected_fault_types: [5], cfsr_check: { mask: 0x00000000, logic: zero } }

  - id: "FI-A66T-006"
    name: "MPUViolation"
    inject:  { method: did_write, did: 0xF190, payload: [0x06] }
    verify:  { check_magic: true, expected_fault_types: [2], cfsr_check: { mask: 0x00000003, logic: nonzero } }
    skip_if: "!mpu_enabled"

  - id: "FI-A66T-007"
    name: "UndefInstr"
    inject:  { method: did_write, did: 0xF190, payload: [0x07] }
    verify:  { check_magic: true, expected_fault_types: [1, 4], cfsr_check: { mask: 0x00010000, logic: nonzero } }

  - id: "FI-A66T-008"
    name: "DirectSCB"
    inject:  { method: did_write, did: 0xF190, payload: [0x08] }
    verify:  { check_magic: true, expected_fault_types: [1], cfsr_check: { mask: 0x00000000, logic: zero } }

  - id: "FI-A66T-009"
    name: "BusAccess"
    inject:  { method: did_write, did: 0xF190, payload: [0x09] }
    verify:  { check_magic: true, expected_fault_types: [1, 3], cfsr_check: { mask: 0x00000300, logic: nonzero } }
```

---

## 6. Part 4: 数据模型

### 6.1 Go 结构体定义

```go
// pkg/fault-inject/domain/types.go

// ─── FaultInjectConfig ───
// 描述一次注入的命令参数。不同 target 类型解析不同的字段组合。

type InjectConfig struct {
    // Target 无关部分
    Method     string      `yaml:"method" json:"method"`
    // CAN/UDS DID 写
    MethodDID  uint16      `yaml:"did,omitempty" json:"did,omitempty"`
    Payload    []byte      `yaml:"payload,omitempty" json:"payload,omitempty"`
    // JTAG 寄存器写
    RegisterName string    `yaml:"register_name,omitempty" json:"register_name,omitempty"`
    RegisterValue uint32   `yaml:"register_value,omitempty" json:"register_value,omitempty"`
    // 内存篡改
    MemoryAddr  uint32     `yaml:"memory_addr,omitempty" json:"memory_addr,omitempty"`
    MemorySize  uint32     `yaml:"memory_size,omitempty" json:"memory_size,omitempty"`
    // 断点
    BreakpointAddr uint32  `yaml:"breakpoint_addr,omitempty" json:"breakpoint_addr,omitempty"`
    // 总线行为
    BusOffDurationMs int   `yaml:"bus_off_duration_ms,omitempty" json:"bus_off_duration_ms,omitempty"`
}


// ─── VerifyConfig ───
// 描述对注入后的故障记录/行为的验证条件。

type VerifyConfig struct {
    CheckMagic          bool               `yaml:"check_magic" json:"check_magic"`
    ExpectedFaultTypes  []int              `yaml:"expected_fault_types,omitempty" json:"expected_fault_types,omitempty"`
    CFSRCheck           *CFSRCheckConfig   `yaml:"cfsr_check,omitempty" json:"cfsr_check,omitempty"`
    HFSRCheck           *HFSRCheckConfig   `yaml:"hfsr_check,omitempty" json:"hfsr_check,omitempty"`
    BehaviorCheck       *BehaviorCheckConfig `yaml:"behavior_check,omitempty" json:"behavior_check,omitempty"`
    PCRange             *PCRangeConfig     `yaml:"pc_range,omitempty" json:"pc_range,omitempty"`
}

type CFSRCheckConfig struct {
    Mask  uint32 `yaml:"mask" json:"mask"`
    Logic string `yaml:"logic" json:"logic"` // "nonzero" | "zero" | "exact"
}

type HFSRCheckConfig struct {
    Mask  uint32 `yaml:"mask" json:"mask"`
    Logic string `yaml:"logic" json:"logic"`
}

type BehaviorCheckConfig struct {
    // 行为级验证：观察 CAN 报文、UART 输出、GPIO 电平
    SafeStateEntered  *bool    `yaml:"safe_state_entered,omitempty" json:"safe_state_entered,omitempty"`
    LimpHomeActive    *bool    `yaml:"limp_home_active,omitempty" json:"limp_home_active,omitempty"`
    WatchdogReset     *bool    `yaml:"watchdog_reset,omitempty" json:"watchdog_reset,omitempty"`
    CustomChecks      []string `yaml:"custom_checks,omitempty" json:"custom_checks,omitempty"`
}

type PCRangeConfig struct {
    Low  uint32 `yaml:"low" json:"low"`
    High uint32 `yaml:"high" json:"high"`
}


// ─── FaultInjectTestCase ───
// 完整的测试用例数据模型。

type FaultInjectTestCase struct {
    ID          string          `yaml:"id" json:"id"`
    Name        string          `yaml:"name" json:"name"`
    Description string          `yaml:"description,omitempty" json:"description,omitempty"`
    TargetType  string          `yaml:"target_type,omitempty" json:"target_type,omitempty"`
    Inject      InjectConfig    `yaml:"inject" json:"inject"`
    Verify      VerifyConfig    `yaml:"verify" json:"verify"`
    TimeoutS    float64         `yaml:"timeout_s,omitempty" json:"timeout_s,omitempty"`
    CooldownS   float64         `yaml:"cooldown_s,omitempty" json:"cooldown_s,omitempty"`
    RetryCount  int             `yaml:"retry_count,omitempty" json:"retry_count,omitempty"`
    SkipIf      string          `yaml:"skip_if,omitempty" json:"skip_if,omitempty"`
    SkipReason  string          `yaml:"-" json:"-"`  // 运行时计算
}


// ─── FaultRecord ───
// 从目标读取的故障记录。参考 A66-T faultRecord 结构。

type FaultRecord struct {
    Magic     uint32 `json:"magic"`      // 0xFA017FA0
    FaultType uint8  `json:"fault_type"` // 1=HardFault, 2=MemManage, 3=BusFault, 4=UsageFault, 5=StackOverflow
    PC        uint32 `json:"pc"`         // 故障发生时的程序计数器
    CFSR      uint32 `json:"cfsr"`       // Configurable Fault Status Register
    HFSR      uint32 `json:"hfsr"`       // HardFault Status Register
    // 扩展字段（非 Cortex-M 特有或高级注入）
    MMFSR     *uint8  `json:"mmfsr,omitempty"`
    BFSR      *uint8  `json:"bfsr,omitempty"`
    UFSR      *uint16 `json:"ufsr,omitempty"`
    LR        *uint32 `json:"lr,omitempty"`    // 故障时的 Link Register
    Extra     []byte  `json:"extra,omitempty"` // Target 自定义附加数据
}


// ─── InjectResult ───
// 单个测试用例的执行结果。

type TestCaseResult struct {
    TestCaseID      string               `json:"test_case_id"`
    Name            string               `json:"name"`
    Status          TestCaseStatus       `json:"status"`
    Error           string               `json:"error,omitempty"`
    FaultRecord     *FaultRecord         `json:"fault_record,omitempty"`
    Verifications   []VerificationResult `json:"verifications"`
    InjectDuration  time.Duration        `json:"inject_duration_ns"`
    WaitDuration    time.Duration        `json:"wait_duration_ns"`
    StartedAt       time.Time            `json:"started_at"`
    CompletedAt     time.Time            `json:"completed_at"`
}

type TestCaseStatus string
const (
    StatusPass    TestCaseStatus = "PASS"
    StatusFail    TestCaseStatus = "FAIL"
    StatusSkipped TestCaseStatus = "SKIPPED"
    StatusBlocked TestCaseStatus = "BLOCKED"
    StatusError   TestCaseStatus = "ERROR"
)

type VerificationResult struct {
    Name    string `json:"name"`
    Passed  bool   `json:"passed"`
    Actual  string `json:"actual,omitempty"`
    Expect  string `json:"expected,omitempty"`
    Details string `json:"details,omitempty"`
}


// ─── InjectReport ───
// 完整测试运行报告。

type InjectReport struct {
    Meta          InjectReportMeta  `json:"meta"`
    TargetConfig  json.RawMessage   `json:"target_config"`
    Results       []TestCaseResult  `json:"results"`
    Summary       ReportSummary     `json:"summary"`
}

type InjectReportMeta struct {
    SchemaVersion string    `json:"schema_version"`
    RunID         string    `json:"run_id"`         // 唯一运行标识
    StartedAt     time.Time `json:"started_at"`
    CompletedAt   time.Time `json:"completed_at"`
    PipelineID    string    `json:"pipeline_id,omitempty"`
    GitCommit     string    `json:"git_commit,omitempty"`
    Branch        string    `json:"branch,omitempty"`
}

type ReportSummary struct {
    Total    int     `json:"total"`
    Passed   int     `json:"passed"`
    Failed   int     `json:"failed"`
    Skipped  int     `json:"skipped"`
    Blocked  int     `json:"blocked"`
    Errors   int     `json:"errors"`
    Duration string  `json:"duration"`
    PassRate float64 `json:"pass_rate"`
}
```

### 6.2 可选 DB 表

当需要持久化故障注入结果以支持追溯矩阵和覆盖率度量时。

```sql
-- fault_injection 相关表（位于 yuleosh 数据库的 ci schema 或独立 schema）

-- 1. 测试运行批次
CREATE TABLE IF NOT EXISTS ci.fi_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL UNIQUE,
    pipeline_id     TEXT,
    target_type     TEXT NOT NULL,
    target_config   JSONB,
    schema_version  TEXT NOT NULL DEFAULT '1.0',
    git_commit      TEXT,
    branch          TEXT,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    total_cases     INT NOT NULL DEFAULT 0,
    passed          INT NOT NULL DEFAULT 0,
    failed          INT NOT NULL DEFAULT 0,
    skipped         INT NOT NULL DEFAULT 0,
    pass_rate       REAL,
    duration_ms     BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fi_runs_pipeline ON ci.fi_runs(pipeline_id);
CREATE INDEX idx_fi_runs_branch ON ci.fi_runs(branch);
CREATE INDEX idx_fi_runs_started ON ci.fi_runs(started_at DESC);

-- 2. 单条测试结果
CREATE TABLE IF NOT EXISTS ci.fi_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL REFERENCES ci.fi_runs(run_id) ON DELETE CASCADE,
    test_case_id    TEXT NOT NULL,
    test_case_name  TEXT NOT NULL,
    status          TEXT NOT NULL,       -- PASS / FAIL / SKIPPED / BLOCKED / ERROR
    error_message   TEXT,

    -- 故障记录
    fault_magic     INT,
    fault_type      SMALLINT,
    fault_pc        BIGINT,
    fault_cfsr      BIGINT,
    fault_hfsr      BIGINT,

    -- 时序
    inject_duration_ms  BIGINT,
    wait_duration_ms    BIGINT,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,

    -- 原始故障记录 JSON（完整保留）
    fault_record_raw    JSONB,

    -- 验证结果 JSON
    verifications       JSONB,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fi_results_run ON ci.fi_results(run_id);
CREATE INDEX idx_fi_results_case ON ci.fi_results(test_case_id);
CREATE INDEX idx_fi_results_status ON ci.fi_results(status);
CREATE INDEX idx_fi_results_fault_type ON ci.fi_results(fault_type);

-- 3. FMEA → FI 追溯映射（关联 knowledge 模块的 fmea_items）
CREATE TABLE IF NOT EXISTS ci.fi_fmea_map (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_case_id    TEXT NOT NULL,
    fmea_item_id    UUID NOT NULL,  -- 关联 knowledge.fmea_items.id
    fmea_failure_mode TEXT NOT NULL,
    coverage_type   SMALLINT NOT NULL DEFAULT 0,
                    -- 0:direct（直接覆盖）, 1:derived（衍生覆盖）, 2:partial（部分覆盖）
    last_run_at     TIMESTAMPTZ,
    last_result     TEXT,           -- PASS / FAIL / NOT_RUN
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(test_case_id, fmea_item_id)
);

CREATE INDEX idx_fi_fmea_map_fmea ON ci.fi_fmea_map(fmea_item_id);
CREATE INDEX idx_fi_fmea_map_case ON ci.fi_fmea_map(test_case_id);
```

### 6.3 故障类型枚举

```go
// FaultType 参考 ARM Cortex-M 异常类型 + A66-T 扩展
const (
    FaultTypeHardFault     = 1  // 硬故障
    FaultTypeMemManage     = 2  // MPU 管理故障
    FaultTypeBusFault      = 3  // 总线故障
    FaultTypeUsageFault    = 4  // 使用故障
    FaultTypeStackOverflow = 5  // 栈溢出（yuleOSH 自定义）
)

var faultTypeNames = map[uint8]string{
    1: "HardFault",
    2: "MemManage",
    3: "BusFault",
    4: "UsageFault",
    5: "StackOverflow",
}

// CFSR (Configurable Fault Status Register) 位掩码
const (
    CFSR_IACCVIOL  = 1 << 0   // 指令访问违规
    CFSR_DACCVIOL  = 1 << 1   // 数据访问违规
    CFSR_MUNSTKERR = 1 << 3   // 异常入栈时 MPU 违规
    CFSR_MSTKERR   = 1 << 4   // 异常出栈时 MPU 违规
    CFSR_MLSPERR   = 1 << 5   // 浮点 lazy 保存 MPU 违规
    CFSR_IBUSERR   = 1 << 8   // 指令总线错误
    CFSR_PRECISERR = 1 << 9   // 精确数据总线错误
    CFSR_IMPRECISERR = 1 << 10 // 非精确数据总线错误
    CFSR_UNSTKERR  = 1 << 11  // 异常入栈时总线错误
    CFSR_STKERR    = 1 << 12  // 异常出栈时总线错误
    CFSR_LSPERR    = 1 << 13  // 浮点 lazy 保存总线错误
    CFSR_UNDEFINSTR = 1 << 16 // 未定义指令
    CFSR_INVSTATE  = 1 << 17  // 无效状态（EPSR 损坏）
    CFSR_INVPC     = 1 << 18  // 无效 PC
    CFSR_NOCP      = 1 << 19  // 无协处理器
    CFSR_UNALIGNED = 1 << 24  // 非对齐访问
    CFSR_DIVBYZERO = 1 << 25  // 除零
)
```

---

## 7. Part 5: CI 模块集成

### 7.1 CLI 子命令

```go
// internal/ci/fault_injection.go

// yule ci fi 子命令定义
// 使用示例:
//   yule ci fi --target can_uds --cases fi/cases/a66-t.yaml
//   yule ci fi --target jtag --cases fi/cases/stm32.yaml --report report.json

func RegisterFaultInjectCMD(parent *cobra.Command) {
    cmd := &cobra.Command{
        Use:   "fi",
        Short: "Run fault injection tests",
        Long:  `Execute fault injection tests against a specified target`,
    }

    // 子命令 1: 运行测试
    runCmd := &cobra.Command{
        Use:   "run",
        Short: "Run fault injection test cases",
        RunE:  runFaultInject,
    }
    runCmd.Flags().String("target", "can_uds", "Target type: can_uds, doip, jtag, simulator")
    runCmd.Flags().StringP("cases", "c", "fi/cases/a66-t.yaml", "Test case YAML path(s), comma-separated")
    runCmd.Flags().String("target-config", "", "Target configuration JSON (or inline yaml)")
    runCmd.Flags().StringP("report", "r", "reports/fault-injection.json", "Report output path")
    runCmd.Flags().Int("max-failures", 1, "Maximum allowed failures before abort")
    runCmd.Flags().Float64("cooldown", 3.0, "Cooldown between tests (seconds)")
    runCmd.Flags().Float64("timeout", 15.0, "Inject wait timeout (seconds)")
    runCmd.Flags().Bool("evidence-push", true, "Push results to evidence module")

    // 子命令 2: 列出可用 target
    listTargets := &cobra.Command{
        Use:   "list-targets",
        Short: "List available target implementations",
        RunE:  listTargetsCmd,
    }

    // 子命令 3: 验证测试用例 YAML
    validateCases := &cobra.Command{
        Use:   "validate",
        Short: "Validate test case YAML schema",
        RunE:  validateCasesCmd,
    }
    validateCases.Flags().StringP("cases", "c", "", "Test case YAML path(s), comma-separated")

    cmd.AddCommand(runCmd, listTargets, validateCases)
    parent.AddCommand(cmd)
}

func runFaultInject(cmd *cobra.Command, args []string) error {
    targetType, _ := cmd.Flags().GetString("target")
    casesCSV, _  := cmd.Flags().GetString("cases")
    reportPath, _ := cmd.Flags().GetString("report")
    maxFails, _   := cmd.Flags().GetInt("max-failures")
    cooldown, _   := cmd.Flags().GetFloat64("cooldown")
    timeout, _    := cmd.Flags().GetFloat64("timeout")

    cases := strings.Split(casesCSV, ",")

    engine := fiengine.New()
    reporter := fireporter.New()

    // 加载用例
    testCases, err := fiengine.LoadTestCases(cases...)
    if err != nil {
        return err
    }

    // 运行
    results, err := engine.Run(cmd.Context(), &fiengine.RunConfig{
        Cases:             testCases,
        MaxFailures:       maxFails,
        CooldownDuration:  time.Duration(cooldown * float64(time.Second)),
        InjectTimeout:     time.Duration(timeout * float64(time.Second)),
    })
    if err != nil {
        return err
    }

    // 保存报告
    return reporter.Save(results, reportPath)
}
```

### 7.2 Pipeline Hooks 集成

与知识管理模块类似的 hook 注册模式：

```go
// internal/ci/ci.go（已有 ci 模块扩展）

func (c *CM) RegisterFaultInjectionHooks() {
    fiChecker := fault_injection.NewFaultInjectionChecker(c.logger)

    // Pre-commit: 校验 YAML 格式
    c.RegisterHook("pre-commit", &Hook{
        Priority: HookPriorityMedium,
        Execute: func(ctx *HookContext) error {
            fiFiles := filterFiles(ctx.ChangedFiles, "fi/cases/")
            if len(fiFiles) == 0 {
                return nil
            }
            result := fiChecker.ValidateFICases(fiFiles)
            return ctx.HandleResult(result)
        },
    })

    // Merge gate: FMEA ↔ FI coverage check
    c.RegisterHook("merge-gate", &Hook{
        Priority: HookPriorityHigh,
        Execute: func(ctx *HookContext) error {
            result := fiChecker.CheckCoverageGate(ctx.Branch, ctx.PRID)
            return ctx.HandleResult(result)
        },
    })
}
```

### 7.3 与 evidence 模块集成

```go
// internal/ci/fault_injection_evidence.go

// 每次 FI 运行完成后，自动推送结果到 evidence 模块

func pushFaultInjectionEvidence(ctx context.Context, results []TestCaseResult, runMeta *InjectReportMeta) error {
    evSvc := evidence.NewService()

    for _, r := range results {
        ev := &evidence.Evidence{
            Type:        evidence.TypeValidation,
            EntityID:    r.TestCaseID,
            EntityType:  "fault_injection",
            Title:       fmt.Sprintf("FI: %s — %s", r.TestCaseID, r.Status),
            Status:      mapToEvidenceStatus(r.Status),
            Content: map[string]interface{}{
                "run_id":       runMeta.RunID,
                "test_case_id": r.TestCaseID,
                "status":       r.Status,
                "fault_type":   r.FaultRecord,
                "error":        r.Error,
                "verifications": r.Verifications,
                "duration_ns":  r.InjectDuration + r.WaitDuration,
            },
            Tags:       []string{"fault_injection", r.TestCaseID, runMeta.PipelineID},
            PipelineID: runMeta.PipelineID,
            RunID:      runMeta.RunID,
            Timestamp:  time.Now(),
        }
        if err := evSvc.Create(ctx, ev); err != nil {
            return err
        }
    }
    return nil
}
```

---

## 8. Part 6: 实施路线

### 8.1 Phase 1 — 地基（CAN/UDS + Pipeline Stage + 基础报告）

**目标：** A66-T 9 个用例在 CAN/UDS 目标上可运行，结果纳入 Pipeline，输出 JSON 报告。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| FI-01 | Target 接口 + factory 骨架 | 2 | — |
| FI-02 | CAN/UDS target 实现（socketcan） | 3 | FI-01 |
| FI-03 | CAN/UDS 底层：socketcan binding + UDS $2E/$22 协议栈 | 3 | FI-02 |
| FI-04 | FI Engine 核心：LoadCases + Run 循环 + Inject/Wait/Verify 三阶段 | 4 | FI-01 |
| FI-05 | Verify 验证引擎（magic / faultType / CFSR / HFSR） | 3 | FI-04 |
| FI-06 | Test Case YAML 解析 + Schema 校验 | 2 | — |
| FI-07 | Pipeline Stage 注册（fault_injection as stage） | 2 | FI-04 + pipeline 模块 |
| FI-08 | CLI `yule ci fi run` 子命令 | 2 | FI-04 + ci 模块 |
| FI-09 | JSON 报告输出 + Reporter | 1 | FI-04 |
| FI-10 | FI 结果 → evidence 模块推送 | 2 | FI-09 + evidence 模块 |
| FI-11 | 预置 A66-T 兼容测试用例 YAML | 1 | FI-06 |
| FI-12 | CI Pre-commit hook（YAML format check） | 1 | FI-06 + ci hooks |
| FI-13 | 文档 + 使用指南 | 2 | — |
| FI-14 | 测试 + 验收 | 3 | FI-01~FI-13 |
| | **Phase 1 合计** | **31** | |

**Phase 1 交付状态：**
- ✅ Target 接口 + CAN/UDS 实现
- ✅ FI Engine 完整运行循环
- ✅ Verify 引擎（A66-T 兼容）
- ✅ YAML Schema 解析 + 校验
- ✅ Pipeline Stage 集成
- ✅ CLI 子命令
- ✅ JSON 报告
- ✅ Evidence 推送
- ✅ 9 个 A66-T 兼容测试用例
- ❌ DoIP Target
- ❌ JTAG Target
- ❌ Simulator Target
- ❌ 并发注入
- ❌ FMEA→FI 自动生成

### 8.2 Phase 2 — 扩展（DoIP + JTAG + 并发注入）

**目标：** 支持多种硬件接口，提升测试速度。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| FI-15 | DoIP target 实现 | 4 | FI-01 + DoIP 协议栈 |
| FI-16 | JTAG/SWD target 实现（OpenOCD + GDB bridge） | 5 | FI-01 + gdb 客户端 |
| FI-17 | 并联 Target 并发执行（多 ECU 同时注入） | 3 | FI-04 |
| FI-18 | 行为级验证扩展（BehaviorCheck — CAN 报文 / GPIO / UART 观察） | 3 | FI-05 |
| FI-19 | DB 持久化表（fi_runs + fi_results + fi_fmea_map） | 2 | store 模块 |
| FI-20 | FI 结果 → knowledge 模块关联（FMEA 追溯） | 3 | FI-19 + knowledge |
| FI-21 | CI Merge gate：FMEA↔FI coverage gap check | 2 | FI-20 + merge gate |
| FI-22 | 置信度衰减：FI 失败触发关联 FMEA/LL 置信度下降 | 2 | FI-20 + confidence |
| FI-23 | Vector CAN 接口支持（可选） | 3 | FI-02 |
| | **Phase 2 合计** | **27** | |

**Phase 2 交付状态（增量）：**
- ✅ DoIP Target
- ✅ JTAG/SWD Target
- ✅ 并发注入
- ✅ 行为级验证
- ✅ DB 持久化
- ✅ FMEA→FI 追溯
- ✅ Merge gate coverage check
- ❌ Simulator Target
- ❌ 自动用例生成

### 8.3 Phase 3 — 智能化（模拟器注入 + 自动用例生成）

**目标：** 纯软件仿真，从 FMEA 自动生成测试用例。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| FI-24 | Simulator target（Unicorn）实现 | 5 | FI-01 + Unicorn bindings |
| FI-25 | Simulator target（QEMU）实现 | 4 | FI-01 |
| FI-26 | 从 FMEA 自动生成 FI 测试用例（failure_mode → inject_config） | 5 | FI-06 + knowledge.fmea |
| FI-27 | 自动测试用例 PR 提交（FMEA 更新 → 自动生成新 FI cases → PR） | 3 | FI-26 + ci hooks |
| FI-28 | FI 覆盖率仪表盘（FMEA coverage / code coverage） | 4 | FI-19 + FI-20 |
| FI-29 | 回归自动重跑（FMEA 更新时自动重跑关联 FI 用例） | 3 | FI-27 + pipeline |
| | **Phase 3 合计** | **24** | |

**Phase 3 交付状态（增量）：**
- ✅ Simulator Target
- ✅ FMEA → FI 自动生成
- ✅ 覆盖率仪表盘
- ✅ 回归自动重跑
- ✅ 全自动闭环

### 8.4 里程碑总览

```
Phase 1 (31人·天) ──── Phase 2 (27人·天) ──── Phase 3 (24人·天)
     │                        │                        │
     ├─ CAN/UDS               ├─ DoIP                  ├─ Simulator
     ├─ FI Engine             ├─ JTAG/SWD              ├─ FMEA→FI AutoGen
     ├─ Verify Engine         ├─ 并发注入               ├─ 覆盖率仪表盘
     ├─ Pipeline Stage        ├─ DB 持久化              └─ 全自动闭环
     ├─ CLI + Report          ├─ FMEA 追溯
     ├─ Evidence 推送         └─ Merge gate
     └─ A66-T 兼容用例
```

---

## 9. 与已有模块集成

### 9.1 集成总览

| yuleOSH 模块 | 集成方式 | 方向 |
|-------------|----------|------|
| **pipeline** | 新增 `internal/pipeline/fault_injection/` | FI → pipeline |
| **ci** | 注册 FI 子命令 + hook | FI → ci |
| **target** | 新增 `pkg/fault-inject/target/` 子包 | 独立 |
| **engine** | 新增 `pkg/fault-inject/engine/` | 独立 |
| **evidence** | FI 结果自动推送到 evidence 模块 | FI → evidence |
| **knowledge** | FI → FMEA 追溯（fi_fmea_map 表） | FI ↔ knowledge |
| **store** | 新增 DB 表 `ci.fi_runs` / `ci.fi_results` / `ci.fi_fmea_map` | FI → store |
| **spec** | FI 结果可作为 spec 审查时的验证证据 | FI → spec |

### 9.2 Package 结构

```
pkg/
└── fault-inject/
    ├── domain/
    │   └── types.go               # 所有数据模型
    ├── target/
    │   ├── target.go              # FaultInjectTarget 接口
    │   ├── registry.go            # 工厂注册
    │   ├── can_uds.go             # CAN/UDS 实现
    │   ├── doip.go                # DoIP 实现
    │   ├── jtag.go                # JTAG/SWD 实现
    │   └── simulator.go           # 模拟器实现
    ├── engine/
    │   ├── engine.go              # 引擎核心
    │   ├── loader.go              # YAML 用例加载
    │   ├── loader_test.go
    │   └── verify.go              # 验证引擎
    └── reporter/
        ├── reporter.go            # JSON 报告生成
        └── reporter_test.go

internal/
└── pipeline/
    └── fault_injection/
        └── stage.go               # Pipeline Stage 实现

internal/
└── ci/
    └── fault_injection.go         # CLI 子命令

internal/
└── store/
    └── fault_injection/
        ├── store.go               # Store 接口
        ├── fi_run_repo.go         # fi_runs CRUD
        └── migration.go           # DDL
```

### 9.3 与 knowledge/FMEA 配合

```
FMEA as Code (YAML)
      │
      ▼
┌────────────────┐     FI AutoGen (Phase 3)    ┌────────────────┐
│  FMEA Items    │ ────────────────────────────→│  FI Test Cases │
│  (failure_mode)│                               │  (inject_spec) │
└───────┬────────┘                               └───────┬────────┘
        │                                                 │
        │  FI Run                                         │ FI Run
        ▼                                                 ▼
┌──────────────────────────┐                    ┌────────────────┐
│  fi_fmea_map (追溯表)     │                    │  fi_results    │
│  test_case_id ↔ fmea_id  │                    │  (PASS/FAIL)   │
└────────────┬─────────────┘                    └───────┬────────┘
             │                                          │
             ▼                                          ▼
       ┌──────────────────┐                     ┌──────────────────┐
       │ confidence 衰减   │                     │ evidence 模块    │
       │ (FI fail → FMEA) │                     │ FI 结果入证据链   │
       └──────────────────┘                     └──────────────────┘
```

### 9.4 配置示例：全链路集成

```yaml
# yuleosh 项目根目录的 .yuleosh.yml（或 pipeline.yml 同级）

fault_injection:
  enabled: true
  default_target:
    type: can_uds
    config:
      interface: socketcan
      channel: vcan0
      bitrate: 500000
      uds_tx_id: 0x7E0
      uds_rx_id: 0x7E8

  test_suites:
    - name: "A66-T Basic Faults"
      path: "fi/cases/yuleosh/a66-t-compat.yaml"
      max_failures: 1

    - name: "Safety Critical - Memory Protect"
      path: "fi/cases/safety/memory-protect.yaml"
      max_failures: 0

  integration:
    evidence_push: true
    fmea_coverage_check: true
    decline_confidence_on_fail: true
```

---

## 10. 附录：A66-T 测试用例到 Schema 映射

### 10.1 A66-T faultRecord 结构 → FaultRecord

```
A66-T faultRecord (C struct)         yuleOSH FaultRecord (Go)

uint32_t magic;          ─────────→ Magic:     uint32  (0xFA017FA0)
uint8_t  faultType;      ─────────→ FaultType: uint8
uint32_t pc;             ─────────→ PC:        uint32
uint32_t cfsr;           ─────────→ CFSR:      uint32
uint32_t hfsr;           ─────────→ HFSR:      uint32
```

### 10.2 PASS 判定映射

```
A66-T 判定逻辑                        yuleOSH VerifyConfig

if magic != 0xFA017FA0: FAIL   →   VerifyConfig.CheckMagic = true
if faultType not in expected: FAIL → VerifyConfig.ExpectedFaultTypes
if (cfsr & mask) == 0: FAIL    →   VerifyConfig.CFSRCheck.Mask + Logic(nonzero)
```

### 10.3 测试控制参数映射

```
A66-T 参数                           yuleOSH 配置

--cooldown 3                        → RunConfig.CooldownDuration = 3s
--max-failures 1                    → RunConfig.MaxFailures = 1
CAN interface                       → CANUDSTargetConfig.Interface
CAN channel                         → CANUDSTargetConfig.Channel
CAN vs Vector                       → CANUDSTargetConfig.Interface
DID 0xF190                          → InjectConfig.MethodDID = 0xF190
TP 轮询                              → CANUDSTargetConfig.TesterPresentIntervalMs
SKIP (MPU 未启用)                    → TestCase.SkipIf = "!mpu_enabled"
```

### 10.4 9 个用例快速索引

| A66-T # | yuleOSH ID | 注入 DID / data | 期望 faultType | CFSR mask | 可跳过 |
|:-------:|------------|:----------------:|:--------------:|:---------:|:------:|
| 1 | FI-A66T-001 | 0xF190 [01] | 1,3 | 0x00000600 | 否 |
| 2 | FI-A66T-002 | 0xF190 [02] | 1,4 | 0x00020000 | 否 |
| 3 | FI-A66T-003 | 0xF190 [03] | 1,4 | 0x02000000 | 是 |
| 4 | FI-A66T-004 | 0xF190 [04] | 1,4 | 0x01000000 | 否 |
| 5 | FI-A66T-005 | 0xF190 [05] | 5 | 0x00000000 | 否 |
| 6 | FI-A66T-006 | 0xF190 [06] | 2 | 0x00000003 | 是 |
| 7 | FI-A66T-007 | 0xF190 [07] | 1,4 | 0x00010000 | 否 |
| 8 | FI-A66T-008 | 0xF190 [08] | 1 | 0x00000000 | 否 |
| 9 | FI-A66T-009 | 0xF190 [09] | 1,3 | 0x00000300 | 否 |

---

> **文档状态：** v1.0 — 首次定稿
>
> **后续步骤：**
> 1. 小马审查架构 + 接口定义 + YAML Schema + Layer 2 方案
> 2. 分歧点由小明裁决（字段命名风格、skip_if 表达式语法）
> 3. 锁定后进入 Phase 1 编码

---

## 11. [附录] 目录修订历史

| 版本 | 日期 | 变更 |
|:----:|:----:|:------|
| v1.0 | 2026-06-20 | 初版 — Layer 1 系统级注入完整方案 |
| v1.0 | 2026-06-20 | 追加 §13 — Layer 2 任务级注入方案 |

---

# §13 任务级故障注入（Layer 2）

> **参考来源：** TaskFaultInject 源码（A66-T 归档.zip）
> **核心设计模式：** FreeRTOS Task Notification + 环形缓冲区 + 宏 API + 零复位
> **适用阶段：** 开发期、CI 回归、HIL 预热验证

## 13.1 设计目标

Layer 2（任务级）与 Layer 1（系统级）形成互补，覆盖错误处理路径的验证盲区：

| 维度 | Layer 1 系统级 | Layer 2 任务级 |
|:-----|:---------------|:---------------|
| 故障本质 | 真实 CPU 异常（硬故障） | 模拟错误条件（NULL句柄/超时/队列满） |
| 注入机制 | 执行错误汇编代码段 | FreeRTOS Task Notification（32-bit 软中断） |
| 系统影响 | ECU 复位（15-30s） | 完全无影响（~2s） |
| 测试范围 | 9 种 CPU 异常 | 7 种运行时模拟故障 |
| 验证重点 | FaultHandler 保存/恢复链路 | 任务级错误处理路径是否正确执行 |
| 8任务×4故障耗时 | ~10 分钟 | ~64 秒 |
| 适用阶段 | HIL/CAT-1~4 | 开发期/CI/回归/预热 |

### 设计五原则

1. **零侵入内核** — 不修改 FreeRTOS 内核，仅利用 Task Notification 现有机制
2. **按任务注册** — 每任务独立注入通道，非全局广播，精确控制调度
3. **两行宏包围** — `TASK_FAULT_CHECK()` / `TASK_FAULT_END_CHECK()` 括住业务循环
4. **错误路径单点注入** — `TASK_FAULT_IS_ACTIVE()` + `TASK_FAULT_REPORT()` 最小化业务代码改动
5. **STD_OFF → 全 no-op** — 生产环境全部 inline 消失，linker 自动优化

## 13.2 架构设计

### 13.2.1 整体数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│                        yuleOSH Pipeline (Host)                       │
│                                                                     │
│  FI Engine (mode=task)                                              │
│    ├── Load YAML test cases (TaskFaultInject schema)                │
│    ├── target.SendInject() → UDS $2E DID 0xF193                    │
│    ├── WaitForTarget() → 等待 2s（无需复位检测，仅等待结果就绪）      │
│    └── target.ReadFaultResult() → UDS $22 DID 0xF192               │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ CAN / DoIP / JTAG
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           ECU Target                                │
│                                                                     │
│  CAN $2E 0xF193 ──→ TaskFault_Inject(taskHandle, faultType)        │
│                          │                                          │
│                          ▼                                          │
│              ┌─────────────────────────┐                            │
│              │ FreeRTOS Task           │                            │
│              │ Notification (xTaskNotify)│                          │
│              │ 32-bit value: taskIndex │ f = faultType < 8          │
│              └─────────┬───────────────┘                            │
│                        │                                            │
│                        ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Target Task Loop                                            │   │
│  │                                                              │   │
│  │  for (;;) {                                                  │   │
│  │      TASK_FAULT_CHECK();          // 收 Notification → 设标志 │   │
│  │                                                              │   │
│  │      // 业务逻辑 + 故障感知分支                               │   │
│  │      if (TASK_FAULT_IS_ACTIVE(NULL_HANDLE)) {                │   │
│  │          handle = NULL;           // 强制模拟 NULL 句柄        │   │
│  │      }                                                       │   │
│  │      if (NULL == handle) {                                   │   │
│  │          TASK_FAULT_REPORT(PASSED);  // 错误处理路径验证通过   │   │
│  │          continue;                                           │   │
│  │      }                                                       │   │
│  │                                                              │   │
│  │      TASK_FAULT_END_CHECK();       // 未报告 → 自动 FAILED    │   │
│  │  }                                                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                        │                                            │
│                        ▼                                            │
│              ┌─────────────────────────┐                            │
│              │ Result Queue            │                            │
│              │ (环形缓冲，16条)          │                            │
│              └─────────┬───────────────┘                            │
│                        │                                            │
│                        ▼                                            │
│              CAN $22 0xF192 ──→ Read result bytes                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 13.2.2 架构组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `TaskFault_Inject()` | ECU C 代码 | 接收注入命令，通过 `xTaskNotify()` 发送到目标任务 |
| `TASK_FAULT_CHECK()` | 任务循环开头 | 从 Notification 提取故障信息，设置 32-bit 故障标志位 |
| `TASK_FAULT_IS_ACTIVE(type)` | 业务逻辑中 | 检查指定的模拟故障类型是否被激活（位测试） |
| `TASK_FAULT_REPORT(result)` | 错误路径 | 将测试结果写入环形缓冲区 + 清除故障标志 |
| `TASK_FAULT_END_CHECK()` | 任务循环结尾 | 若循环结束仍未报告 → 自动写入 FAILED 结果 |
| Result Queue | 全局环形缓冲 | 最多 16 条记录，每条含 taskIndex + faultType + result + timestamp |
| UDS $22 0xF192 | CAN/DoIP 服务 | 主机读取结果缓冲区（支持批量读，返回所有待取记录） |

## 13.3 API 设计（C Header 供嵌入）

### 13.3.1 配置头文件

```c
// yuleosh_fault_inject_task_cfg.h
#ifndef YULEOSH_FAULT_INJECT_TASK_CFG_H
#define YULEOSH_FAULT_INJECT_TASK_CFG_H

/* ================================================================
 * yuleOSH Task-Level Fault Injection — 编译配置
 *
 * 编译开关: YULEOSH_TASK_FI_ENABLE
 * UDS DID:  0xF193 (写注入) / 0xF192 (读结果)
 * 结果缓冲区: 16 条记录
 * 默认超时: 5000ms
 *
 * 包含可读可写：该头文件被目标 ECU 代码包含，
 * 也作为 YAML schema 和 pipeline 配置的参考。
 * ================================================================ */

/* ——— 编译开关 ——— */
// 全局使能：定义此宏开启任务级故障注入
// #define YULEOSH_TASK_FI_ENABLE

// 单个模拟故障类型独立开关（Layer 1 风格的个体控制）
#define YULEOSH_TASK_FI_SIM_NULL_HANDLE     1u
#define YULEOSH_TASK_FI_SIM_INVALID_PARAM   1u
#define YULEOSH_TASK_FI_SIM_TIMEOUT         1u
#define YULEOSH_TASK_FI_SIM_QUEUE_FULL      1u
#define YULEOSH_TASK_FI_SIM_BUFFER_OVF      1u
#define YULEOSH_TASK_FI_SIM_RESOURCE_LOST   1u
#define YULEOSH_TASK_FI_SIM_STATE_CORRUPT   1u

// 真正的栈消耗测试（危险！默认 OFF，仅调试环境）
#define YULEOSH_TASK_FI_REAL_STACK_DEPLETE  0u

/* ——— 缓冲区与超时 ——— */
#define YULEOSH_TASK_FI_RESULT_QUEUE_SIZE   16u
#define YULEOSH_TASK_FI_DEFAULT_TIMEOUT_MS  5000u

/* ——— UDS DID ——— */
#define YULEOSH_TASK_FI_INJECT_DID          0xF193u
#define YULEOSH_TASK_FI_RESULT_DID          0xF192u

/* ——— SecurityAccess ——— */
// 可选的 UDS SecurityAccess 级别（需 ECU 支持 $27 服务）
// 0 = 不启用安全认证; 1 = 需要 seed/key
#define YULEOSH_TASK_FI_SECURITY_LEVEL      0u

#endif /* YULEOSH_FAULT_INJECT_TASK_CFG_H */
```

### 13.3.2 公共 API 头文件

```c
// yuleosh_fault_inject_task.h
#ifndef YULEOSH_FAULT_INJECT_TASK_H
#define YULEOSH_FAULT_INJECT_TASK_H

#include <stdint.h>
#include "yuleosh_fault_inject_task_cfg.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ================================================================
 * yuleOSH Task-Level Fault Injection API
 *
 * 所有 API 定义在 STD_OFF（YULEOSH_TASK_FI_ENABLE 未定义）时
 * 会被内联为空函数/空宏，linker 自动优化移除。
 * ================================================================ */

/* ——— 枚举 ——— */

/** 模拟故障类型 */
typedef enum {
    TASK_FAULT_SIM_NULL_HANDLE     = 0x01u,  /**< 关键句柄为 NULL */
    TASK_FAULT_SIM_INVALID_PARAM   = 0x02u,  /**< 参数越界/无效 */
    TASK_FAULT_SIM_TIMEOUT         = 0x03u,  /**< 超时/错过截止时间 */
    TASK_FAULT_SIM_QUEUE_FULL      = 0x04u,  /**< 消息队列已满 */
    TASK_FAULT_SIM_BUFFER_OVF      = 0x05u,  /**< 缓冲区溢出 */
    TASK_FAULT_SIM_RESOURCE_LOST   = 0x06u,  /**< 外设丢失 */
    TASK_FAULT_SIM_STATE_CORRUPT   = 0x07u,  /**< 状态机损坏 */
    TASK_FAULT_REAL_STACK_DEPLETE  = 0x10u,  /**< 真正栈消耗（危险！） */
} TaskFault_SimType;

/** 测试结果 */
typedef enum {
    TASK_FAULT_RESULT_NONE    = 0x00u,  /**< 未开始/未报告 */
    TASK_FAULT_RESULT_PASSED  = 0x01u,  /**< 错误处理路径通过 */
    TASK_FAULT_RESULT_FAILED  = 0x02u,  /**< 未找到错误处理 */
    TASK_FAULT_RESULT_TIMEOUT = 0x03u,  /**< 超时未响应 */
} TaskFault_Result;

/* ——— 结果记录（环形缓冲区条目） ——— */
typedef struct {
    uint8_t  taskIndex;       /**< 注册时分配的索引 [0-7] */
    uint8_t  faultType;       /**< TaskFault_SimType */
    uint8_t  result;          /**< TaskFault_Result */
    uint8_t  reserved;
    uint32_t timestampMs;     /**< 注入时的系统滴答 (ms) */
} TaskFault_ResultRecord;

/* ——— 初始化与注销 ——— */

/**
 * TaskFault_Init
 *
 * 初始化任务故障注入模块。
 * - 清空结果环形缓冲
 * - 重置所有任务注册表项
 * - 注册 UDS $2E 0xF193 / $22 0xF192 处理器
 *
 * 必须在 FreeRTOS scheduler 启动后调用一次。
 */
void TaskFault_Init(void);

/**
 * TaskFault_RegisterTask
 *
 * 注册一个任务以接受故障注入。
 *
 * @param handle   TaskHandle_t（来自 xTaskCreate/xTaskGetCurrentTaskHandle）
 * @param name     可读的任务名（最大 16 字符，用于调试日志）
 * @return         uint8_t  分配的索引 [0-7]，0xFF 表示注册表满
 *
 * 注册表最大 8 项。通常每个任务在启动循环前注册自身：
 *   TaskFault_RegisterTask(xTaskGetCurrentTaskHandle(), "RteHigh");
 */
uint8_t TaskFault_RegisterTask(void *handle, const char *name);

/* ——— 注入接口（主机侧调用） ——— */

/**
 * TaskFault_Inject
 *
 * 向指定任务注入一个模拟故障。
 * 内部通过 FreeRTOS xTaskNotify() 发送通知。
 *
 * @param taskIndex  目标任务在注册表中的索引 [0-7]
 * @param faultType  故障类型 (TaskFault_SimType)
 * @return           bool  true=发送成功, false=目标未注册或通知满
 *
 * 编码规则：通知值高 24 bit = taskIndex, 低 8 bit = faultType
 *   uint32_t notifyValue = ((uint32_t)taskIndex << 24u) | (uint32_t)faultType;
 */
uint8_t TaskFault_Inject(uint8_t taskIndex, uint8_t faultType);

/* ——— 结果读取（主机侧） ——— */

/**
 * TaskFault_ReadResult
 *
 * 从环形缓冲区读取一条结果记录（FIFO）。
 *
 * @param record  输出参数，存放一条结果
 * @return         uint8_t  0=无记录可读，1=成功读取
 *
 * 读取的记录从缓冲区移除。若需批量读，循环调用直到返回 0。
 */
uint8_t TaskFault_ReadResult(TaskFault_ResultRecord *record);

/**
 * TaskFault_GetResultCount
 *
 * 获取当前缓冲区中待读取的结果数量。
 */
uint8_t TaskFault_GetResultCount(void);

/**
 * TaskFault_GetTaskName
 *
 * 根据索引获取注册的任务名。
 *
 * @param taskIndex  注册索引 [0-7]
 * @return           const char*  任务名指针，0xFF 索引返回 NULL
 */
const char* TaskFault_GetTaskName(uint8_t taskIndex);

/* ——— 任务侧宏 API（用户任务代码中调用） ——— */

/**
 * TASK_FAULT_CHECK()
 *
 * 在任务循环开头调用：
 * - 检查是否有 FreeRTOS Task Notification 等待
 * - 若收到 → 解析 taskIndex + faultType → 设置 32-bit 活跃故障位图
 * - 复位本轮结果状态为 NONE
 * - 记录注入时间戳
 *
 * 典型用法（在每个任务循环的入口处）：
 *   for (;;) {
 *       TASK_FAULT_CHECK();
 *       ... 业务逻辑 ...
 *       TASK_FAULT_END_CHECK();
 *   }
 */
#define TASK_FAULT_CHECK()

/**
 * TASK_FAULT_IS_ACTIVE(type)
 *
 * 检查指定类型的模拟故障当前是否被激活。
 * 在业务逻辑中用于决定是否强制进入错误路径。
 *
 * @param type  故障类型枚举值 (TaskFault_SimType)
 * @return      布尔值：1=该故障激活中，0=未激活
 *
 * 典型用法（在关键句柄获取后）：
 *   void *handle = Rte_IRead_RPort_SomeData();
 *   if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_NULL_HANDLE)) {
 *       handle = NULL;
 *   }
 *   if (NULL == handle) {
 *       TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
 *       return;
 *   }
 */
#define TASK_FAULT_IS_ACTIVE(type)

/**
 * TASK_FAULT_REPORT(result)
 *
 * 报告测试结果：
 * - 将 (taskIndex, faultType, result, timestamp) 写入环形缓冲区
 * - 清除当前活跃故障位图
 * - 清零通知值（防止重复处理）
 *
 * @param result  TASK_FAULT_RESULT_PASSED 或 TASK_FAULT_RESULT_FAILED
 */
#define TASK_FAULT_REPORT(result)

/**
 * TASK_FAULT_END_CHECK()
 *
 * 在任务循环的结尾调用：
 * - 检查本轮是否有活跃故障但未报告
 * - 若有 → 自动写入 TASK_FAULT_RESULT_FAILED（说明任务绕过了错误路径）
 * - 清除活跃故障位图
 */
#define TASK_FAULT_END_CHECK()

/* ——— STD_OFF 实现（生产环境 no-op） ——— */

#ifndef YULEOSH_TASK_FI_ENABLE

// 所有函数退化为内联空函数
static inline void TaskFault_Init(void) {}
static inline uint8_t TaskFault_RegisterTask(void *handle, const char *name) { return 0xFFu; }
static inline uint8_t TaskFault_Inject(uint8_t taskIndex, uint8_t faultType) { return 0u; }
static inline uint8_t TaskFault_ReadResult(TaskFault_ResultRecord *record) { return 0u; }
static inline uint8_t TaskFault_GetResultCount(void) { return 0u; }
static inline const char* TaskFault_GetTaskName(uint8_t taskIndex) { return NULL; }

// 所有宏退化为空
#undef TASK_FAULT_CHECK
#undef TASK_FAULT_IS_ACTIVE
#undef TASK_FAULT_REPORT
#undef TASK_FAULT_END_CHECK

#define TASK_FAULT_CHECK()              ((void)0)
#define TASK_FAULT_IS_ACTIVE(type)      ((uint8_t)0u)
#define TASK_FAULT_REPORT(result)       ((void)0)
#define TASK_FAULT_END_CHECK()          ((void)0)

#endif /* YULEOSH_TASK_FI_ENABLE */

#ifdef __cplusplus
}
#endif

#endif /* YULEOSH_FAULT_INJECT_TASK_H */
```

### 13.3.3 任务侧埋点模式

```c
// 典型用法示例：RteHigh 任务

void RteHigh_Task(void *params) {
    // Phase 1: 注册任务
    uint8_t taskIdx = TaskFault_RegisterTask(xTaskGetCurrentTaskHandle(), "RteHigh");
    (void)taskIdx;  // 调试时可用索引

    for (;;) {
        // Phase 2: 检查注入
        TASK_FAULT_CHECK();

        // Phase 3: 业务逻辑
        void *handle = Rte_IRead_RPort_Signal();

        // Phase 4: 故障感知分支
        if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_NULL_HANDLE)) {
            handle = NULL;  // 强制模拟 NULL 句柄
        }
        if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_INVALID_PARAM)) {
            handle = (void*)0xDEADBEEF;  // 强制模拟无效指针
        }

        // Phase 5: 错误处理路径
        StatusType ret;
        if (NULL == handle) {
            ret = Rte_ReportError(RTE_E_NULL_POINTER);
            if (RTE_E_OK == ret) {
                TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
                continue;
            }
        }

        // Phase 6: 正常处理 + 循环结束检查
        ProcessSignal(handle);
        TASK_FAULT_END_CHECK();
    }
}
```

### 13.3.4 实现层关键逻辑（伪代码参考）

```c
// TaskFault_Inject — 通过 FreeRTOS Task Notification 发送
uint8_t TaskFault_Inject(uint8_t taskIndex, uint8_t faultType) {
    if (taskIndex >= g_taskFault_registeredCount) {
        return 0u;  // 无效索引
    }
    TaskHandle_t handle = g_taskFault_registry[taskIndex].handle;
    if (NULL == handle) {
        return 0u;
    }
    // 编码：高 24 bit = taskIndex, 低 8 bit = faultType
    uint32_t notifyValue = ((uint32_t)taskIndex << 24u) | (uint32_t)faultType;
    // 使用 eSetValueWithoutOverwrite — 只接受第一个通知（防冲）
    BaseType_t ret = xTaskNotify((TaskHandle_t)handle,
                                 notifyValue,
                                 eSetValueWithoutOverwrite);
    return (pdPASS == ret) ? 1u : 0u;
}

// TASK_FAULT_CHECK 展开逻辑（简化）：
// 1. ulTaskNotifyTake(pdTRUE, 0) 检查是否有待处理的通知值
// 2. 若有，解析 taskIndex 和 faultType，设置 g_activeFaultFlags
// 3. 清除 g_activeFaultFlags 中之前周期的残留
// 4. 记录注入开始时间戳

// TASK_FAULT_IS_ACTIVE(type) 展开逻辑：
// 1. 检查 g_activeFaultFlags 对应位是否置位
// 2. 返回 1/0

// TASK_FAULT_REPORT(result) 展开逻辑：
// 1. 构造 TaskFault_ResultRecord
// 2. 写入环形缓冲区（head 指针递增，mod QUEUE_SIZE）
// 3. 清除 g_activeFaultFlags
// 4. 清除通知值（xTaskNotifyStateClear）

// TASK_FAULT_END_CHECK 展开逻辑：
// 1. 检查 g_activeFaultFlags 非零
// 2. 若非零 → 自动构造 FAILED 结果记录写入缓冲
// 3. 清除 g_activeFaultFlags
```

## 13.4 通信层适配

### 13.4.1 新增 TaskNotification Target Adapter

在现有 `pkg/fault-inject/target/` 中新增适配器，封装任务级注入的通信模式。

```go
// pkg/fault-inject/target/task_notification.go

package target

import (
    "context"
    "encoding/binary"
    "time"
)

// TaskNotificationTargetConfig 任务级注入通信配置
type TaskNotificationTargetConfig struct {
    // 底层通信通道复用现有 UDS/DoIP/JTAG
    Underlying TargetType `yaml:"underlying"`        // "can_uds" | "doip" | "jtag" | "simulator"

    // 注入 DID（UDS 模式下）
    InjectDID  uint16     `yaml:"inject_did"`        // 默认 0xF193
    ResultDID  uint16     `yaml:"result_did"`        // 默认 0xF192

    // 注入协议帧格式
    // 注入：{faultType(uint32), taskIndex(uint32)} — 8 字节
    // 结果：{taskIndex(uint8), faultType(uint8), result(uint8), reserved(uint8), timestamp(uint32)} — 8 字节/条

    // 等待策略：任务级注入无需等待复位
    // 注入后等待 result_ready_timeout_ms 即可读结果
    ResultReadyTimeoutMs int `yaml:"result_ready_timeout_ms"` // 默认 2000

    // 结果轮询间隔
    ResultPollIntervalMs int `yaml:"result_poll_interval_ms"` // 默认 100
}

// taskNotificationTarget 包装一个底层 target，提供任务级注入 API
type taskNotificationTarget struct {
    underlying FaultInjectTarget  // 复用的底层通信 channel（CAN/DoIP/JTAG）
    cfg        TaskNotificationTargetConfig
}

func NewTaskNotificationTarget(underlying FaultInjectTarget, cfg TaskNotificationTargetConfig) FaultInjectTarget {
    return &taskNotificationTarget{
        underlying: underlying,
        cfg:        cfg,
    }
}

// SendInject 通过底层 target 发送任务级注入命令
func (t *taskNotificationTarget) SendInject(ctx context.Context, cfg InjectConfig) error {
    // 构造注入载荷：{faultType(uint32), taskIndex(uint32)}
    payload := make([]byte, 8)
    binary.LittleEndian.PutUint32(payload[0:4], cfg.TaskFaultType)
    binary.LittleEndian.PutUint32(payload[4:8], cfg.TaskIndex)

    injectCfg := InjectConfig{
        Method:    cfg.Method,  // "did_write"
        MethodDID: t.cfg.InjectDID,
        Payload:   payload,
    }

    return t.underlying.SendInject(ctx, injectCfg)
}

// WaitForTarget 任务级注入的特殊等待逻辑
// 无需等待复位，只需等待结果就绪即可
func (t *taskNotificationTarget) WaitForTarget(ctx context.Context, timeout time.Duration) bool {
    // 无复位等待——底层链路应该保持活跃
    // 这里只做链路健康检查
    if pinger, ok := t.underlying.(interface{ Ping(context.Context) bool }); ok {
        return pinger.Ping(ctx)
    }
    return true  // 默认认为链路在线
}

// WaitForResultReady 等待结果就绪（TASK_FAULT_END_CHECK 被执行）
func (t *taskNotificationTarget) WaitForResultReady(ctx context.Context) bool {
    timeoutMs := t.cfg.ResultReadyTimeoutMs
    if timeoutMs <= 0 {
        timeoutMs = 2000  // 默认 2s
    }
    deadline := time.Now().Add(time.Duration(timeoutMs) * time.Millisecond)
    for time.Now().Before(deadline) {
        select {
        case <-ctx.Done():
            return false
        default:
            // 检查是否有结果可读
            count, err := t.readResultCount(ctx)
            if err == nil && count > 0 {
                return true
            }
            time.Sleep(time.Duration(t.cfg.ResultPollIntervalMs) * time.Millisecond)
        }
    }
    return false
}

// ReadFaultRecord 读取任务级故障注入结果
func (t *taskNotificationTarget) ReadFaultRecord(ctx context.Context) (*FaultRecord, error) {
    // 对于任务级，ReadFaultRecord 返回一个聚合结果
    // 转为通用的 FaultRecord 格式以复用现有验证引擎
    records, err := t.readAllResults(ctx)
    if err != nil {
        return nil, err
    }
    if len(records) == 0 {
        return nil, nil
    }

    // 将任务级结果编码为 FaultRecord 格式
    data := make([]byte, 0, len(records)*8)
    for _, r := range records {
        data = append(data, r...)
    }

    return &FaultRecord{
        Magic:     0xFA027FA0,  // Layer 2 魔数（区别于 Layer 1 的 0xFA017FA0）
        FaultType: 0,           // 不适用
        PC:        0,
        CFSR:      0,
        Extra:     data,        // 原始任务级结果数据
    }, nil
}
```

### 13.4.2 InjectConfig 扩展

```go
// 在 domain/types.go 中扩展

type InjectConfig struct {
    // ... 原有字段不变

    // ——— 任务级注入新增字段 ———
    TaskIndex    uint32 `yaml:"task_index,omitempty" json:"task_index,omitempty"`
    TaskFaultType uint32 `yaml:"task_fault_type,omitempty" json:"task_fault_type,omitempty"`

    // ——— 任务注册（初始化阶段使用） ———
    TaskRegistration []TaskRegistration `yaml:"register_task,omitempty" json:"register_task,omitempty"`
}

type TaskRegistration struct {
    TaskName string `yaml:"task" json:"task"`
    Index    uint32 `yaml:"index" json:"index"`
}
```

### 13.4.3 UDS 远程触发协议

```
CAN $2E 0xF193 (WriteDataByIdentifier) — 注入触发
  Data: {faultType(uint32 LE), taskIndex(uint32 LE)}
  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
  │ FT0 │ FT1 │ FT2 │ FT3 │ TI0 │ TI1 │ TI2 │ TI3 │
  ├─────┴─────┴─────┴─────┼─────┴─────┴─────┴─────┤
  │   faultType (uint32)  │    taskIndex (uint32)  │
  └───────────────────────┴───────────────────────┘

CAN $22 0xF192 (ReadDataByIdentifier) — 读结果
  Response Data: 变长 — {recordCount(uint8)} + records[]
  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
  │ cnt  │ TI   │ FT   │ RES  │ RSRV │ TM0  │ TM1  │ TM2  │ TM3  │
  ├──────┼──────┴──────┴──────┴──────┴──────┴──────┴──────┤
  │      │           record 0 (8 bytes)                    │
  ├──────┼─────────────────────────────────────────────────┤
  │      │           record 1 (8 bytes)                    │
  └──────┴─────────────────────────────────────────────────┘

故障类型编码（枚举值 1-7）：
  0x01 = NULL_HANDLE       — 模拟关键句柄为 NULL
  0x02 = INVALID_PARAM     — 模拟参数越界/无效
  0x03 = TIMEOUT           — 模拟超时
  0x04 = QUEUE_FULL        — 模拟消息队列满
  0x05 = BUFFER_OVF        — 模拟缓冲区溢出
  0x06 = RESOURCE_LOST     — 模拟外设丢失
  0x07 = STATE_CORRUPT     — 模拟状态机损坏
```

### 13.4.4 RTOS 无关抽象

对于非 FreeRTOS 环境，将 Task Notification 替换为等价机制：

| RTOS | 等价机制 | 备注 |
|------|---------|------|
| FreeRTOS | `xTaskNotify()` / `ulTaskNotifyTake()` | 原生支持，1 周期延迟 |
| Zephyr | `k_sem_give()` / `k_sem_take()` | 每任务占一个信号量（Semaphore） |
| RT-Thread | `rt_event_send()` / `rt_event_recv()` | 使用事件集（Event Set） |
| 裸机 | 全局变量 + `__sev()`/`__wfe()` | 最简实现，每个任务一个 volatile flag |
| AUTOSAR OS | `SetEvent()` / `WaitEvent()` | 符合 OSEK 标准 |

```c
// 适配器层设计（yuleosh_task_fault_inject_rtos.h）
#ifndef YULEOSH_TASK_FI_RTOS_ADAPTER_H
#define YULEOSH_TASK_FI_RTOS_ADAPTER_H

// 通过宏抽象 RTOS 差异
#if defined(YULEOSH_RTOS_FREERTOS)
    #include "FreeRTOS.h"
    #include "task.h"
    #define TASK_FI_NOTIFY(task, value)  xTaskNotify(task, value, eSetValueWithoutOverwrite)
    #define TASK_FI_NOTIFY_TAKE()        ulTaskNotifyTake(pdTRUE, 0)
    #define TASK_FI_NOTIFY_CLEAR()       xTaskNotifyStateClear(NULL)
#elif defined(YULEOSH_RTOS_ZEPHYR)
    // Zephyr 信号量封装
    #define TASK_FI_NOTIFY(task, value)  k_sem_give(task)  /* 需扩展传值 */
    #define TASK_FI_NOTIFY_TAKE()        k_sem_take(&g_taskFi_sem, K_NO_WAIT)
#elif defined(YULEOSH_RTOS_RTT)
    #define TASK_FI_NOTIFY(task, value)  rt_event_send(task, value)
    #define TASK_FI_NOTIFY_TAKE()        rt_event_recv(g_taskFi_event, 0xFFFFFFFF, \
                                                       RT_EVENT_FLAG_OR | RT_EVENT_FLAG_CLEAR, \
                                                       RT_WAITING_NO, &g_taskFi_eventValue)
#else
    #error "TASK_FI_NOTIFY: unsupported RTOS, define YULEOSH_TASK_FI_RTOS_ADAPTER_USER or port"
#endif

#endif /* YULEOSH_TASK_FI_RTOS_ADAPTER_H */
```

## 13.5 与现有 Pipeline 的集成

### 13.5.1 Stage 配置模式扩展

在现有 `fault_injection` stage 中扩展 `mode` 参数，支持 Layer 1 + Layer 2 混合执行。

```yaml
# pipeline.yml — fault_injection stage 扩展后的完整配置

stages:
  - id: fault_injection
    config:
      # ——— 运行模式 ———
      # mode: system  → Layer 1（系统级·复位注入，15-30s/case）
      # mode: task    → Layer 2（任务级·Notification注入，~2s/case）
      # mode: mixed   → 先 task 后 system（64s task → 10 min system）
      mode: task

      # ——— 目标选择（复用现有 target 配置） ———
      target:
        type: task_notification         # 新模式
        underlying:
          type: can_uds
          interface: socketcan
          channel: vcan0
        inject_did: 0xF193
        result_did: 0xF192

      # ——— 任务注册 ———
      register_task:
        - { task: "RteHigh", index: 0 }
        - { task: "RteLow",  index: 1 }
        - { task: "ComM",    index: 2 }
        - { task: "BswM",    index: 3 }

      # ——— 测试用例（YAML 文件或内联） ———
      test_cases:
        - "fi/cases/yuleosh/task-inject-basic.yaml"
        - "fi/cases/yuleosh/task-inject-rte.yaml"

      # ——— 运行时参数 ———
      max_failures:       2
      inject_timeout_s:   5.0      # 任务级超时较短
      cooldown_s:         0.5      # 任务级无需长冷却
      retry_on_fail:      0
      wait_for_result_ms: 2000     # 任务级注入后等待结果就绪的毫秒数

      # ——— 报告与集成 ———
      report_path:        "reports/fault-injection-task.json"
```

### 13.5.2 混合模式（Mixed Mode）—— 先 task 后 system

```yaml
stages:
  - id: fault_injection
    config:
      mode: mixed
      # 第一阶段：任务级注入（64s，不复位）
      task_phase:
        register_task:
          - { task: "RteHigh", index: 0 }
          - { task: "RteLow",  index: 1 }
        test_cases:
          - "fi/cases/yuleosh/task-inject-basic.yaml"

      # 第二阶段：系统级注入（10min，复位）
      system_phase:
        target:
          type: can_uds
          channel: vcan0
        test_cases:
          - "fi/cases/yuleosh/a66-t-compat.yaml"

      # ——— 整体控制 ———
      max_failures: 2
      report_path: "reports/fault-injection-mixed.json"
```

### 13.5.3 Pipeline Stage 代码扩展

```go
// internal/pipeline/fault_injection/stage.go — 扩展

type FaultInjectionStage struct {
    engine    *fiengine.Engine
    reporter  *fireporter.Reporter
    config    StageConfig
}

type StageConfig struct {
    // ——— 新增：运行模式 ———
    Mode string `yaml:"mode"`          // "system" | "task" | "mixed"

    // ——— 新增：任务级注入配置 ———
    RegisterTask    []TaskRegistration `yaml:"register_task,omitempty"`
    WaitForResultMs int                `yaml:"wait_for_result_ms,omitempty"`

    // ——— 新增：混合模式双阶段配置 ———
    TaskPhase   *TaskPhaseConfig   `yaml:"task_phase,omitempty"`
    SystemPhase *SystemPhaseConfig `yaml:"system_phase,omitempty"`

    // ... 原有字段
}

func (s *FaultInjectionStage) Run(ctx *pipeline.Context) error {
    ctx.Log.Info("fault_injection stage started", zap.String("mode", s.config.Mode))

    var allResults []TestCaseResult

    switch s.config.Mode {
    case "task":
        results, err := s.runTaskPhase(ctx)
        if err != nil {
            return err
        }
        allResults = results

    case "system":
        results, err := s.runSystemPhase(ctx)
        if err != nil {
            return err
        }
        allResults = results

    case "mixed":
        // 先跑任务级（快）
        taskResults, err := s.runTaskPhase(ctx)
        if err != nil {
            return err
        }
        allResults = append(allResults, taskResults...)

        // 再生产系统级（慢）
        systemResults, err := s.runSystemPhase(ctx)
        if err != nil {
            return err
        }
        allResults = append(allResults, systemResults...)
    }

    // 统一报告生成
    return s.reporter.Save(allResults, s.config.ReportPath)
}

// runTaskPhase 执行任务级注入序列
func (s *FaultInjectionStage) runTaskPhase(ctx *pipeline.Context) ([]TestCaseResult, error) {
    // 1. 构造 task_notification target，复用底层通信
    // 2. 发送任务注册命令（$2E 0xF193 注册序列）
    // 3. 循环执行每个用例的 Inject → WaitForResult → ReadResult
    // 4. 验证结果（PASSED/FAILED）
    return results, nil
}
```

## 13.6 YAML 用例集扩展

### 13.6.1 任务级注入 YAML Schema

```yaml
# fi/cases/yuleosh/task-inject-basic.yaml
# yuleOSH Layer 2 — Task Fault Injection 测试用例
meta:
  schema_version: "2.0"
  project: "yuleosh/ecu-fw"
  layer: task  # 标识为任务级注入
  target_type: task_notification
  source: "A66-T TaskFaultInject (FreeRTOS Task Notification)"

# ——— 任务注册（在注入前完成） ———
register_task:
  - { task: "RteHigh", index: 0 }
  - { task: "RteLow",  index: 1 }
  - { task: "ComM",    index: 2 }
  - { task: "BswM",    index: 3 }
  - { task: "EcuM",    index: 4 }
  - { task: "CanTp",   index: 5 }
  - { task: "NvM",     index: 6 }
  - { task: "Det",     index: 7 }

test_cases:
  # ── TC1: RteHigh NULL_HANDLE ──
  - id: "FI-TASK-001"
    name: "RteHigh — simulate NULL handle"
    description: >
      Inject NULL_HANDLE fault into RteHigh task.
      Task should detect null pointer and report error via Rte_ReportError.
      Expected: PASSED (error path executed correctly).
    layer: task
    task_index: 0
    fault_type: 1                    # TASK_FAULT_SIM_NULL_HANDLE
    expected_result: "passed"        # TASK_FAULT_RESULT_PASSED
    result_ready_timeout_ms: 2000

  # ── TC2: RteHigh INVALID_PARAM ──
  - id: "FI-TASK-002"
    name: "RteHigh — simulate invalid parameter"
    layer: task
    task_index: 0
    fault_type: 2                    # TASK_FAULT_SIM_INVALID_PARAM
    expected_result: "passed"
    result_ready_timeout_ms: 2000

  # ── TC3: RteHigh TIMEOUT ──
  - id: "FI-TASK-003"
    name: "RteHigh — simulate timeout"
    layer: task
    task_index: 0
    fault_type: 3                    # TASK_FAULT_SIM_TIMEOUT
    expected_result: "passed"

  # ── TC4: RteLow TIMEOUT ──
  - id: "FI-TASK-004"
    name: "RteLow — simulate timeout"
    layer: task
    task_index: 1
    fault_type: 3
    expected_result: "passed"

  # ── TC5: RteHigh QUEUE_FULL ──
  - id: "FI-TASK-005"
    name: "RteHigh — simulate queue full"
    layer: task
    task_index: 0
    fault_type: 4                    # TASK_FAULT_SIM_QUEUE_FULL
    expected_result: "passed"

  # ── TC6: ComM BUFFER_OVF ──
  - id: "FI-TASK-006"
    name: "ComM — simulate buffer overflow"
    layer: task
    task_index: 2
    fault_type: 5                    # TASK_FAULT_SIM_BUFFER_OVF
    expected_result: "passed"

  # ── TC7: BswM RESOURCE_LOST ──
  - id: "FI-TASK-007"
    name: "BswM — simulate resource lost"
    layer: task
    task_index: 3
    fault_type: 6                    # TASK_FAULT_SIM_RESOURCE_LOST
    expected_result: "passed"

  # ── TC8: Det STATE_CORRUPT ──
  - id: "FI-TASK-008"
    name: "Det — simulate state corrupt"
    layer: task
    task_index: 7
    fault_type: 7                    # TASK_FAULT_SIM_STATE_CORRUPT
    expected_result: "passed"
```

### 13.6.2 内联简洁格式（适合快速调试）

```yaml
# pipeline.yml 内联用例
stages:
  - id: fault_injection
    config:
      mode: task
      target:
        type: task_notification
        underlying:
          type: can_uds
          channel: vcan0
      register_task:
        - { task: "RteHigh", index: 0 }
        - { task: "RteLow",  index: 1 }
      test_cases:
        - id: 1
          task: "RteHigh"
          fault: "null_handle"
          expected: "passed"
        - id: 2
          task: "RteHigh"
          fault: "invalid_param"
          expected: "passed"
        - id: 3
          task: "RteLow"
          fault: "timeout"
          expected: "passed"
        - id: 4
          task: "RteLow"
          fault: "queue_full"
          expected: "passed"
```

### 13.6.3 PI 集成用例（8 任务 × 7 故障）

```yaml
# fi/cases/yuleosh/task-inject-pi.yaml
# PI 阶段全覆盖：8 个注册任务 × 7 种模拟故障 = 56 个用例
# 预估耗时：56 × 2s ≈ 112s (≈ 2 分钟)
meta:
  schema_version: "2.0"
  project: "yuleosh/ecu-fw"
  layer: task
  target_type: task_notification
  description: "PI regression gate — 8 tasks x 7 fault types = 56 cases"

register_task:
  - { task: "RteHigh", index: 0 }
  - { task: "RteLow",  index: 1 }
  - { task: "ComM",    index: 2 }
  - { task: "BswM",    index: 3 }
  - { task: "EcuM",    index: 4 }
  - { task: "CanTp",   index: 5 }
  - { task: "NvM",     index: 6 }
  - { task: "Det",     index: 7 }

test_cases:
  # 每个任务 × 7 种故障
  # 故障编号 1-7 分别对应 NULL_HANDLE / INVALID_PARAM / TIMEOUT /
  #           QUEUE_FULL / BUFFER_OVF / RESOURCE_LOST / STATE_CORRUPT
  #
  # 格式：{id, task_index, fault_type, expected_result}
  # 以下为完整 56 用例的压缩表示（实际使用时由脚本生成或展开）

  # --- RteHigh (idx=0) ---
  - {id: "FI-PI-001", task_index: 0, fault_type: 1, expected: "passed"}
  - {id: "FI-PI-002", task_index: 0, fault_type: 2, expected: "passed"}
  - {id: "FI-PI-003", task_index: 0, fault_type: 3, expected: "passed"}
  - {id: "FI-PI-004", task_index: 0, fault_type: 4, expected: "passed"}
  - {id: "FI-PI-005", task_index: 0, fault_type: 5, expected: "passed"}
  - {id: "FI-PI-006", task_index: 0, fault_type: 6, expected: "passed"}
  - {id: "FI-PI-007", task_index: 0, fault_type: 7, expected: "passed"}

  # --- RteLow (idx=1) ---
  - {id: "FI-PI-008", task_index: 1, fault_type: 1, expected: "passed"}
  - {id: "FI-PI-009", task_index: 1, fault_type: 2, expected: "passed"}
  # ... (实际 YAML 包含全部 56 条)
```

## 13.7 数据模型扩展

### 13.7.1 新增枚举 & 结构体

```go
// pkg/fault-inject/domain/types.go — 追加

// 任务级注入的故障类型
type TaskFaultType uint8

const (
    TaskFaultNullHandle   TaskFaultType = 1  // NULL 句柄
    TaskFaultInvalidParam TaskFaultType = 2  // 无效参数
    TaskFaultTimeout      TaskFaultType = 3  // 超时
    TaskFaultQueueFull    TaskFaultType = 4  // 队列满
    TaskFaultBufferOvf    TaskFaultType = 5  // 缓存溢出
    TaskFaultResourceLost TaskFaultType = 6  // 外设丢失
    TaskFaultStateCorrupt TaskFaultType = 7  // 状态机损坏
    TaskFaultStackDepl    TaskFaultType = 16 // 真正栈消耗（危险！）
)

var taskFaultTypeNames = map[uint8]string{
    1:  "NULL_HANDLE",
    2:  "INVALID_PARAM",
    3:  "TIMEOUT",
    4:  "QUEUE_FULL",
    5:  "BUFFER_OVF",
    6:  "RESOURCE_LOST",
    7:  "STATE_CORRUPT",
    16: "STACK_DEPLETE",
}

// 任务级测试结果
type TaskFaultResult uint8

const (
    TaskFaultResultNone    TaskFaultResult = 0  // 未开始
    TaskFaultResultPassed  TaskFaultResult = 1  // 通过（错误处理正确执行）
    TaskFaultResultFailed  TaskFaultResult = 2  // 失败（未进入错误路径）
    TaskFaultResultTimeout TaskFaultResult = 3  // 超时
)

// 任务级结果记录
type TaskFaultResultRecord struct {
    TaskIndex   uint8           `json:"task_index"`
    FaultType   TaskFaultType   `json:"fault_type"`
    Result      TaskFaultResult `json:"result"`
    Reserved    uint8           `json:"reserved,omitempty"`
    TimestampMs uint32          `json:"timestamp_ms"`
}

// 任务注册表
type TaskRegistration struct {
    TaskName string `yaml:"task" json:"task"`
    Index    uint32 `yaml:"index" json:"index"`
}

// Layer 2 专用的 FaultRecord 魔数
const TaskFaultMagic = 0xFA027FA0  // 区别于 Layer 1 的 0xFA017FA0
```

### 13.7.2 DB 表扩展

```sql
-- 任务级测试结果表
CREATE TABLE IF NOT EXISTS ci.fi_task_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          TEXT NOT NULL REFERENCES ci.fi_runs(run_id) ON DELETE CASCADE,
    test_case_id    TEXT NOT NULL,
    test_case_name  TEXT NOT NULL,
    status          TEXT NOT NULL,       -- PASS / FAIL / TIMEOUT

    -- 任务级特有字段
    task_index      SMALLINT NOT NULL,
    task_name       TEXT NOT NULL,
    fault_type      SMALLINT NOT NULL,   -- 1-7 (TaskFaultType)
    fault_type_name TEXT,
    actual_result   SMALLINT,            -- 0-3 (TaskFaultResult)
    result_ready_ms BIGINT,              -- 结果就绪耗时

    -- 元数据
    inject_completed_at  TIMESTAMPTZ,
    result_read_at       TIMESTAMPTZ,
    error_message        TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fi_task_results_run ON ci.fi_task_results(run_id);
CREATE INDEX idx_fi_task_results_task ON ci.fi_task_results(task_name, fault_type);
```

## 13.8 实施路线追加

### Phase 1 追加 — 任务级 API 定义 + 基本实现

**目标：** 提供可嵌入 C 头文件 + 任务侧埋点指南 + 通过 UDS 远程触发单用例。

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| FI-T01 | TaskFaultInject C API 头文件（yuleosh_fault_inject_task.h + cfg） | 2 | — |
| FI-T02 | TaskFaultInject.c 核心实现（Init/Register/Inject + Notification） | 3 | FI-T01 |
| FI-T03 | 环形结果缓冲区实现 + 结果读取 API | 2 | FI-T01 |
| FI-T04 | 宏展开：TASK_FAULT_CHECK / END_CHECK / IS_ACTIVE / REPORT | 2 | FI-T01 |
| FI-T05 | FreeRTOS Task Notification 适配 + RTOS 抽象层头文件 | 1 | FI-T01 |
| FI-T06 | UDS $2E/$22 服务端注册（DID 0xF193 / 0xF192） | 2 | FI-T02 + UDS 栈 |
| FI-T07 | STD_OFF no-op 保护（生产环境零开销） | 1 | FI-T01 |
| FI-T08 | yuleOSH Pipeline Target 适配器（task_notification 包装器） | 2 | FI-01 + FI-T06 |
| FI-T09 | YAML Schema 扩展 + 验证（layer: task, task_index, fault_type） | 1 | FI-06 |
| FI-T10 | Pipeline Stage mode 参数支持（"task"/"mixed"） | 2 | FI-07 |
| FI-T11 | 任务级结果验证引擎（expected_result 比对） | 1 | FI-05 + FI-T03 |
| FI-T12 | 8 任务 × 7 故障 PI 用例 YAML | 1 | FI-T09 |
| FI-T13 | 文档 + 埋点指南 + 测试 | 3 | — |
| | **Phase 1 增量合计** | **23** | |

### Phase 2 追加 — UDS 远程触发 + 结果查询 + JTAG 直接注入

| 编号 | 工作项 | 人·天 | 依赖 |
|------|--------|:-----:|------|
| FI-T14 | 多用例批量执行引擎（register → inject × N → readAll） | 3 | FI-T10 |
| FI-T15 | JTAG 直接注入（绕过 UDS，通过调试器写 Notification 寄存器） | 3 | FI-16 + FI-T02 |
| FI-T16 | 结果 DB 持久化（fi_task_results 表） | 1 | FI-19 |
| FI-T17 | 混合模式（mixed mode）Stage 实现 | 2 | FI-T10 + FI-07 |
| FI-T18 | SecurityAccess $27 保护（可选） | 2 | FI-T06 |
| FI-T19 | 任务级 FMEA 追溯映射（task-level failure modes） | 2 | FI-20 |
| FI-T20 | CI Dashboard 集成（Layer 2 覆盖率卡片） | 2 | FI-16 |
| | **Phase 2 增量合计** | **15** | |

### 工作量汇总

| 阶段 | 原始（Layer 1 仅） | 追加 Layer 2 | 总计 |
|:----:|:------------------:|:------------:|:----:|
| Phase 1 | 31 人·天 | +23 人·天 | 54 人·天 |
| Phase 2 | 27 人·天 | +15 人·天 | 42 人·天 |
| Phase 3 | 24 人·天 | +0 人·天 | 24 人·天 |
| **总计** | **82 人·天** | **+38 人·天** | **120 人·天** |

### 两阶段对应关系

```
Phase 1 (基础)
  ├─ Layer 1: CAN/UDS + FI Engine + Verify + Pipeline + CLI
  │    (31 人·天)
  └─ Layer 2: C API 头文件 + 实现 + UDS 适配 + Pipeline mode + YAML
       (23 人·天, 新增)

Phase 2 (扩展)
  ├─ Layer 1: DoIP + JTAG + 并发 + DB + FMEA → 追溯
  │    (27 人·天)
  └─ Layer 2: 批量引擎 + JTAG 直注 + 混合模式 + DB + SecurityAccess
       (15 人·天, 新增)

Phase 3 (智能化)
  └─ 模拟器 + FMEA AutoGen + 覆盖率仪表盘 + 全自动闭环
       (24 人·天, Layer 1 & 2 共享)
```

### Layer 2 关键交付物清单

| 交付物 | 类型 | Phase |
|--------|------|:----:|
| `inc/yuleosh_fault_inject_task_cfg.h` | C 头文件 | P1 |
| `inc/yuleosh_fault_inject_task.h` | C 头文件（API + 宏 + no-op） | P1 |
| `inc/yuleosh_task_fault_inject_rtos.h` | C 头文件（RTOS 抽象层） | P1 |
| `src/yuleosh_fault_inject_task.c` | C 实现（~350 行） | P1 |
| `pkg/fault-inject/target/task_notification.go` | Go Target 适配器 | P1 |
| `fi/cases/yuleosh/task-inject-basic.yaml` | YAML 用例（8 任务 × 7 故障） | P1 |
| `internal/pipeline/fault_injection/modes.go` | Go Stage 多模式支持 | P1 |
| `doc/guides/task-fault-injection.md` | 埋点指南 + 集成手册 | P1 |

---

> **更新说明：** §13 根据 TaskFaultInject 源码（A66-T 归档.zip）设计，补充了 yuleOSH 的 Layer 2 任务级注入方案。
> 核心思想：不复位、不侵入内核、两行宏包围、生产环境零开销。
>
> **依赖关系：**
> - §13 C API 可独立于 Layer 1 的 Go pipeline 先落地
> - Pipeline 集成（§13.5）依赖现有的 fi.Engine 和 target 接口
> - 混合模式（§13.5.2）需要两个 Phase 都完成后再集成
